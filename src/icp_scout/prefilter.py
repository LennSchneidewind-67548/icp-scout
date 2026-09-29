"""WP1. Cheap rule-based pre-score over the whole market, no LLM.

Decides which companies get researched by the agent. Every exclusion keeps its
reason, so the funnel (market -> segment -> shortlist -> top 50) is reportable.

The pre-score uses the rubric's own weights so it approximates the final score:
size (1 inside the band, 0.5 near it), product mix (share of product lines the
RGE domains prove; 0.5 when unknown), tech (an own website that isn't a
directory), growth (a member with several open establishments, or created in
the last 24 months).
"""

from datetime import date

from icp_scout.config import IcpConfig
from icp_scout.group import Group, website_host

UNKNOWN_MIX = 0.5
GROWTH_MONTHS = 24


def size_flags(mid: float, unknown: int, headcount_min: int, headcount_max: int) -> dict:
    """In segment when the midpoint sum is in the band; near_band within half its width."""
    half = (headcount_max - headcount_min) / 2
    known = not (mid == 0 and unknown > 0)
    inside = known and headcount_min <= mid <= headcount_max
    near = known and not inside and headcount_min - half <= mid <= headcount_max + half
    return {"in_segment": inside, "near_band": near}


def product_lines(domains: set[str], icp: IcpConfig) -> list[str]:
    lines = icp.market.product_lines or {d: [d] for d in icp.market.rge_domains}
    return [line for line, proof in lines.items() if domains & set(proof)]


def signals(group: Group, icp: IcpConfig, directories: set[str], today: date) -> dict:
    flags = size_flags(
        group.headcount["headcount_mid"], group.headcount["headcount_unknown"],
        icp.segment.headcount_min, icp.segment.headcount_max,
    )  # fmt: skip
    domains = set().union(*(c.domains for c in group.members))
    n_lines = len(icp.market.product_lines or icp.market.rge_domains)
    if domains:
        mix = len(product_lines(domains, icp)) / n_lines
    else:
        mix = UNKNOWN_MIX  # register source: the agent finds out (WP2)
    has_site = own_website(group, directories) is not None
    cutoff = months_before(today, GROWTH_MONTHS).isoformat()
    growing = any(
        (c.establishments_open or 0) > 1 or (c.created or "") >= cutoff for c in group.members
    )
    return {
        "size_fit": 1.0 if flags["in_segment"] else 0.5 if flags["near_band"] else 0.0,
        "product_mix": mix,
        "growth": 1.0 if growing else 0.0,
        "tech_maturity": 1.0 if has_site else 0.0,
    }


def pre_score(values: dict[str, float], icp: IcpConfig) -> float:
    """Weighted mean over the rubric signals the pre-score knows, in [0, 1]."""
    weights = {s.id: s.weight for s in icp.signals if s.id in values}
    total = sum(weights.values())
    return sum(values[k] * w for k, w in weights.items()) / total if total else 0.0


def own_website(group: Group, directories: set[str]) -> str | None:
    """The largest member's first website that isn't a directory page."""
    for c in sorted(group.members, key=lambda c: c is not group.lead):
        for url in c.websites:
            host = website_host(url)
            if host and host not in directories:
                return url
    return None


def shortlist(rows: list[dict], size: int, headcount_max: int) -> None:
    """Mark the top `size` pre-scored candidates; give every other row its reason."""
    candidates = [r for r in rows if r["in_segment"] or r["near_band"]]
    candidates.sort(key=lambda r: (-r["pre_score"], -r["headcount_mid"], r["group_id"]))
    for rank, row in enumerate(candidates, 1):
        row["shortlisted"] = rank <= size
        if rank > size:
            where = "in segment" if row["in_segment"] else "near band"
            row["exclusion_reason"] = f"{where}, pre-score below the shortlist cut"
    for row in rows:
        row.setdefault("shortlisted", False)
        if not (row["in_segment"] or row["near_band"]):
            row["exclusion_reason"] = size_reason(row, headcount_max)


def size_reason(row: dict, headcount_max: int) -> str:
    if row["headcount_mid"] == 0 and row["headcount_unknown"]:
        return "headcount unknown"
    return "above the segment" if row["headcount_mid"] > headcount_max else "below the segment"


def months_before(day: date, months: int) -> date:
    y, m = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(y, m + 1, min(day.day, 28))
