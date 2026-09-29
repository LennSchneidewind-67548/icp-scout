"""WP1. `icp-scout source`: registry pull -> register join -> second source -> groups ->
pre-filter -> shortlist. Writes data/companies.parquet, data/market.parquet and
data/funnel.json.
"""

import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd

from icp_scout import group, prefilter
from icp_scout.config import IcpConfig
from icp_scout.funnel import Funnel
from icp_scout.http import CachedClient
from icp_scout.sources import rge, sirene
from icp_scout.sources.sirene import Company


def run(
    icp: IcpConfig,
    data_dir: str | Path = "data",
    *,
    limit: int | None = None,
    offline: bool = False,
    refresh: bool = False,
    today: date | None = None,
    transport: httpx.BaseTransport | None = None,
    rate_per_s: float = 5.0,
    log=lambda msg: print(msg, file=sys.stderr),
) -> Funnel:
    data_dir = Path(data_dir)
    today = today or datetime.now(UTC).date()
    client_args = {
        "offline": offline,
        "refresh": refresh,
        "rate_per_s": rate_per_s,
        "transport": transport,
    }
    rge_client = CachedClient("rge", data_dir / "cache", **client_args)
    reg_client = CachedClient("register", data_dir / "cache", **client_args)
    funnel = Funnel(meta={"today": today.isoformat(), "limit": limit})
    seg = icp.segment

    # 1. RGE registry: target qualifications, active only, grouped by SIRET then SIREN.
    log("RGE registry ...")
    funnel.add(
        "rge_rows",
        "RGE registry rows",
        rge.total_rows(rge_client),
        "every certified qualification, one row each",
    )
    rows = rge.fetch_rows(rge_client, icp.market.rge_domains)
    funnel.add(
        "target_rows", "Target qualifications", len(rows), "domain is one of market.rge_domains"
    )
    rows = [r for r in rows if rge.is_active(r, today)]
    funnel.add(
        "active_rows",
        "Active target qualifications",
        len(rows),
        f"dropped {funnel.stages[-1].count - len(rows):,} expired before {today}",
    )
    sites = rge.group_by_siret(rows)
    funnel.add(
        "sirets",
        "Certified establishments (SIRET)",
        len(sites),
        "qualifications merged per establishment",
    )
    by_siren: dict[str, list[rge.RgeSite]] = defaultdict(list)
    for site in sites.values():
        by_siren[site.siren].append(site)
    funnel.add(
        "sirens", "Certified companies (SIREN)", len(by_siren), "establishments merged per company"
    )
    # Directories are counted over the whole registry pull, before --limit.
    directories = group.directory_hosts(
        {s: [site.website for site in ss if site.website] for s, ss in by_siren.items()}
    )
    sirens = sorted(by_siren)
    if limit is not None and limit < len(sirens):
        sirens = sirens[:limit]
        funnel.add("limited", "Limited sample", len(sirens), f"--limit {limit}")

    # 2. Register join: firmographics per SIREN; closed or unknown companies drop out.
    log(f"Register join: {len(sirens):,} companies ...")
    companies: list[Company] = []
    for i, siren in enumerate(sirens, 1):
        result = sirene.lookup(reg_client, siren)
        if result is None:
            c = Company(
                siren=siren,
                name="",
                source="rge",
                via="rge",
                active=False,
                exclusion_reason="not found in the register",
            )
        else:
            c = sirene.from_register(result, source="rge", via="rge")
            if not c.active:
                c.exclusion_reason = "closed"
        sirene.attach_rge(c, by_siren[siren])
        companies.append(c)
        if i % 500 == 0:
            log(f"  {i:,} / {len(sirens):,} ({reg_client.calls:,} calls)")
    active = [c for c in companies if c.active]
    closed = sum(c.exclusion_reason == "closed" for c in companies)
    funnel.add(
        "active_companies",
        "Active certified companies",
        len(active),
        f"dropped {closed:,} closed, {len(companies) - len(active) - closed:,} "
        "not found in the register",
        closed=closed,
        not_found=len(companies) - len(active) - closed,
    )

    # 3. Second source: installers without RGE, from the register.
    second = icp.market.second_source
    if second and second.naf_codes:
        log("Register search (second source) ...")
        matches, stats = sirene.register_search(reg_client, second, limit)
        known = {c.siren for c in companies}
        new = [
            sirene.from_register(m, source="register", via="naf_search")
            for m in matches
            if m["siren"] not in known
        ]
        companies += new
        active += new
        funnel.add(
            "register_source",
            "+ register source",
            len(active),
            f"+{len(new):,} with NAF {', '.join(second.naf_codes)}, band >= "
            f"{second.min_headcount_band} and an energy word in the name, not in RGE",
            kind="add",
            added=len(new),
            searched=stats["searched"],
            name_match=stats["name_match"],
            already_rge=len(matches) - len(new),
            truncated_bands=stats["truncated_bands"],
        )

    # 3b. Companies named in the config (e.g. reference customers neither source finds).
    known = {c.siren for c in companies}
    extra = [s for s in icp.market.extra_sirens if s not in known]
    if icp.market.extra_sirens:
        added = []
        for siren in extra:
            result = sirene.lookup(reg_client, siren)
            if result is None:
                log(f"  extra SIREN {siren} not found in the register")
                continue
            c = sirene.from_register(result, source="register", via="config")
            if not c.active:
                c.exclusion_reason = "closed"
            companies.append(c)
            if c.active:
                active.append(c)
                added.append(c)
        funnel.add(
            "config_source",
            "+ named in the config",
            len(active),
            f"+{len(added):,} of {len(icp.market.extra_sirens):,} market.extra_sirens "
            f"({len(icp.market.extra_sirens) - len(extra):,} already found)",
            kind="add",
            added=len(added),
        )

    # 4. Groups: other companies of the same managers, then the roll-up.
    cap = group.EXPANSION_MAX_CALLS if limit is None else min(group.EXPANSION_MAX_CALLS, limit)
    log("Manager expansion ...")
    found, stats = group.expand_by_manager(reg_client, active, seg.headcount_min, cap)
    companies += found
    active += found
    funnel.add(
        "manager_expansion",
        "+ same-manager companies",
        len(active),
        f"+{len(found):,} other companies of managers of 10+ staff firms below "
        f"{seg.headcount_min} ({stats['lookups']:,} lookups)",
        kind="add",
        added=len(found),
        **stats,
    )
    keys = group.assign_groups(active, directories)
    groups = group.build_groups(active, keys)
    rolled = sum(len(g.members) > 1 for g in groups)
    funnel.add(
        "groups",
        "Groups",
        len(groups),
        f"{len(active):,} companies rolled up; {rolled:,} groups have several members",
        kind="merge",
        multi_member=rolled,
    )

    # 5. Segment and pre-filter.
    market = [group_row(g, icp, directories, today) for g in groups]
    prefilter.shortlist(market, icp.prefilter.shortlist_size, seg.headcount_max)
    inside = sum(r["in_segment"] for r in market)
    near = sum(r["near_band"] for r in market)
    reasons = pd.Series(
        [r["exclusion_reason"] for r in market if not (r["in_segment"] or r["near_band"])]
    )
    funnel.add(
        "segment",
        "In or near the segment",
        inside + near,
        f"{inside:,} with {seg.headcount_min}-{seg.headcount_max} staff (sum of band "
        f"midpoints), {near:,} near it",
        in_segment=inside,
        near_band=near,
        **{k.replace(" ", "_"): int(v) for k, v in reasons.value_counts().items()},
    )
    shortlisted = sum(r["shortlisted"] for r in market)
    funnel.add(
        "shortlist",
        "Shortlist",
        shortlisted,
        f"top {icp.prefilter.shortlist_size} by rule-based pre-score",
    )

    write_outputs(data_dir, companies, market, funnel)
    log(f"Done: {rge_client.calls + reg_client.calls:,} HTTP calls.")
    return funnel


def group_row(g: group.Group, icp: IcpConfig, directories: set[str], today: date) -> dict:
    lead = g.lead
    values = prefilter.signals(g, icp, directories, today)
    flags = prefilter.size_flags(
        g.headcount["headcount_mid"], g.headcount["headcount_unknown"],
        icp.segment.headcount_min, icp.segment.headcount_max,
    )  # fmt: skip
    domains = set().union(*(c.domains for c in g.members))
    revenues = [c.revenue for c in g.members if c.revenue is not None]
    created = [c.created for c in g.members if c.created]
    return {
        "group_id": g.group_id,
        "name": lead.name,
        "members": [c.siren for c in g.members],
        "member_names": [c.name for c in g.members],
        "link_keys": g.keys,
        "link_reason": g.link_reason,
        "domains": sorted(domains),
        "product_lines": prefilter.product_lines(domains, icp),
        "website": prefilter.own_website(g, directories),
        "department": lead.department,
        "region": lead.region,
        "lat": lead.lat,
        "lon": lead.lon,
        **g.headcount,
        "revenue": sum(revenues) if revenues else None,
        "created": min(created) if created else None,
        "source": g.source,
        **{f"pre_{k}": v for k, v in values.items()},
        "pre_score": round(prefilter.pre_score(values, icp), 4),
        **flags,
        "shortlisted": False,
        "exclusion_reason": None,
    }


def write_outputs(data_dir: Path, companies: list[Company], market: list[dict], funnel: Funnel):
    data_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in companies:
        row = vars(c).copy()
        row["domains"] = sorted(c.domains)
        row["managers"] = json.dumps(c.managers, ensure_ascii=False)
        rows.append(row)
    pd.DataFrame(rows).to_parquet(data_dir / "companies.parquet", index=False)
    pd.DataFrame(market).to_parquet(data_dir / "market.parquet", index=False)
    funnel.write(data_dir / "funnel.json")
