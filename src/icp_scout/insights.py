"""WP4. `icp-scout insights`: the findings behind the deck, from the pipeline's own files.

One pure function per finding, `(Inputs, IcpConfig) -> Finding`: a table, a
headline number and an Altair chart. No model calls. The chart is saved as
Vega-Lite JSON, so the app (WP5, `st.altair_chart`) and the deck (WP7,
vega-embed) draw the same spec.

Two populations, never mixed without saying so: the market (every group, open
data only) and the researched set (the groups the agent read; picked by the
pre-score, so its patterns describe the shortlist, not the market). Every
finding names its population. References are calibration, not leads: findings
on the researched set leave them out unless they mark them.

n is small (about 175 researched) and the tiers come from our own rubric:
counts, shares and medians only, no significance claims.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import altair as alt
import pandas as pd

from icp_scout.config import IcpConfig
from icp_scout.group import website_host
from icp_scout.sources.sirene import band_mid

MARKET = "market"
RESEARCHED = "researched"

# INSEE region codes (public). Other countries show the code.
REGIONS_FR = {
    "01": "Guadeloupe", "02": "Martinique", "03": "Guyane", "04": "La Réunion",
    "06": "Mayotte", "11": "Île-de-France", "24": "Centre-Val de Loire",
    "27": "Bourgogne-Franche-Comté", "28": "Normandie", "32": "Hauts-de-France",
    "44": "Grand Est", "52": "Pays de la Loire", "53": "Bretagne",
    "75": "Nouvelle-Aquitaine", "76": "Occitanie", "84": "Auvergne-Rhône-Alpes",
    "93": "Provence-Alpes-Côte d'Azur", "94": "Corse",
}  # fmt: skip

# Headcount bands for the size findings (agent headcount, staff).
HEADCOUNT_BINS = [0, 30, 60, 100, 200, 300, float("inf")]
HEADCOUNT_LABELS = ["<30", "30-59", "60-99", "100-199", "200-299", "300+"]
# Product-mix categories shown before the rest fold into "other".
MAX_MIX = 5


@dataclass
class Inputs:
    market: pd.DataFrame
    signals: pd.DataFrame
    scored: pd.DataFrame
    companies: pd.DataFrame
    funnel: dict


@dataclass
class Finding:
    id: str
    title: str
    population: str
    headline: str
    data: pd.DataFrame
    chart: alt.TopLevelMixin | None = None
    # Further tables, written as <id>_<name>.csv.
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)


def load(data_dir: str | Path) -> Inputs:
    data_dir = Path(data_dir)
    names = ["market", "signals", "scored", "companies"]
    for name in names:
        if not (data_dir / f"{name}.parquet").exists():
            raise FileNotFoundError(f"{data_dir / name}.parquet not found: run the pipeline first")
    frames = {n: pd.read_parquet(data_dir / f"{n}.parquet") for n in names}
    funnel = json.loads((data_dir / "funnel.json").read_text(encoding="utf-8"))
    return Inputs(**frames, funnel=funnel)


def researched(d: Inputs) -> pd.DataFrame:
    """Scored groups with their market columns."""
    cols = ["group_id", "region", "product_lines", "members", "website", "headcount_mid",
            "pre_tech_maturity", "in_segment"]  # fmt: skip
    return d.scored.merge(d.market[cols], on="group_id", how="left")


def leads(d: Inputs) -> pd.DataFrame:
    r = researched(d)
    return r[~r["is_reference"]].reset_index(drop=True)


def pct(x: float) -> str:
    return f"{x:.0%}"


# F1. The funnel, and what the roll-up adds.

FUNNEL_STAGES = ["rge_rows", "target_rows", "active_companies", "groups"]


def f1_funnel(d: Inputs, icp: IcpConfig) -> Finding:
    stages = {s["id"]: s for s in d.funnel["stages"]}
    rows = [
        {"stage": stages[i]["label"], "count": stages[i]["count"], "population": MARKET}
        for i in FUNNEL_STAGES
        if i in stages
    ]
    seg = icp.segment
    m = d.market
    rows += [
        {"stage": f"In segment ({seg.headcount_min}-{seg.headcount_max} staff)",
         "count": int(m["in_segment"].sum()), "population": MARKET},
        {"stage": "Researched by the agent", "count": len(d.scored), "population": RESEARCHED},
        {"stage": "SDR queue", "count": int(d.scored["queue_rank"].notna().sum()),
         "population": RESEARCHED},
    ]  # fmt: skip
    table = pd.DataFrame(rows)
    table["order"] = range(len(table))

    rollup = rolled_in(d, icp)
    added = stages.get("manager_expansion", {}).get("detail", {}).get("added", 0)
    in_seg = int(m["in_segment"].sum())
    scored = d.scored.set_index("group_id")
    in_queue = rollup["group_id"].map(scored["queue_rank"]).notna().sum()
    headline = (
        f"{table['count'].iloc[0]:,} registry rows -> {in_seg:,} groups in segment -> "
        f"{table['count'].iloc[-1]} in the queue. The roll-up alone puts {len(rollup)} "
        f"groups ({pct(len(rollup) / in_seg)} of the segment) in the size band, "
        f"{in_queue} of them in the queue; the manager search added {added:,} companies."
    )
    return Finding(
        "f1_funnel", "From registry rows to the SDR queue", MARKET, headline, table,
        funnel_chart(table), {"rolled_in": rollup},
    )  # fmt: skip


def rolled_in(d: Inputs, icp: IcpConfig) -> pd.DataFrame:
    """In-segment groups of several companies whose largest company alone has fewer
    staff than the segment's floor: in the segment only because of the roll-up."""
    c = d.companies[d.companies["active"]]
    biggest = c.assign(mid=c["band"].map(band_mid)).groupby("group_id")["mid"].max()
    m = d.market[d.market["in_segment"] & (d.market["members"].map(len) > 1)]
    m = m.assign(largest_company=m["group_id"].map(biggest))
    out = m[~(m["largest_company"] >= icp.segment.headcount_min)]
    tiers = d.scored.set_index("group_id")["tier"]
    return out.assign(tier=out["group_id"].map(tiers))[
        ["group_id", "name", "members", "link_reason", "largest_company", "headcount_mid",
         "shortlisted", "tier"]
    ].reset_index(drop=True)  # fmt: skip


# F2. Open data finds the segment but can't rank it.


def f2_prescore(d: Inputs, icp: IcpConfig) -> Finding:
    r = researched(d)
    table = r[["group_id", "name", "pre_score", "score", "tier", "is_reference", "queue_rank"]]
    table = table.assign(pre_score=table["pre_score"].round(3))
    lead = table[~table["is_reference"]]
    rho = lead["pre_score"].rank().corr(lead["score"].rank())
    by_level = (
        lead.groupby("pre_score")
        .agg(groups=("score", "size"), median_score=("score", "median"),
             tier_a=("tier", lambda t: round((t == "A").mean(), 2)))
        .reset_index()
        .sort_values("pre_score", ascending=False)
    )  # fmt: skip
    size = int(d.scored["queue_rank"].notna().sum())
    top_pre = set(lead.nlargest(size, "pre_score", keep="first")["group_id"])
    queue = set(lead[lead["queue_rank"].notna()]["group_id"])
    pre_rank = d.market["pre_score"].rank(ascending=False, method="min")
    refs = d.market["group_id"].isin(table[table["is_reference"]]["group_id"])
    ref_ranks = ", ".join(f"#{int(x):,}" for x in sorted(pre_rank[refs]))
    headline = (
        f"Rank correlation pre-score vs agent score: {rho:.2f}. In the shortlist the "
        f"pre-score takes {lead['pre_score'].nunique()} values; tier A share by level: "
        + ", ".join(f"{p:g} -> {pct(a)}" for p, a in zip(by_level["pre_score"],
                                                         by_level["tier_a"], strict=True))
        + f". {len(top_pre & queue)} of the top {size} by pre-score are in the queue."
        + (f" References sit at pre-score rank {ref_ranks} in the market." if ref_ranks else "")
    )  # fmt: skip
    return Finding(
        "f2_prescore", "The pre-score finds the segment, not the best leads", RESEARCHED,
        headline, table, prescore_chart(table), {"by_level": by_level},
    )  # fmt: skip


# F3. What separates the tiers, led by what the weights don't force.


def f3_tiers(d: Inputs, icp: IcpConfig) -> Finding:
    lead = leads(d)
    ids = [s.id for s in icp.signals]
    lead = lead.assign(
        headcount_band=pd.cut(lead["headcount"], HEADCOUNT_BINS, right=False,
                              labels=HEADCOUNT_LABELS)
    )  # fmt: skip
    # Signals whose value doesn't come from size: the size curve sets only size_fit.
    free = [s for s in ids if s != icp.segment.size_signal]
    table = (
        lead.groupby("headcount_band", observed=True)
        .agg(groups=("group_id", "size"), **{s: (s, "mean") for s in free},
             tier_a=("tier", lambda t: (t == "A").mean()))
        .round(2)
        .reset_index()
    )  # fmt: skip
    tiers = (
        lead.groupby("tier")
        .agg(groups=("group_id", "size"), **{s: (s, "mean") for s in ids},
             median_headcount=("headcount", "median"),
             companies_per_group=("members", lambda x: x.map(len).mean()))
        .round(2)
        .reset_index()
    )  # fmt: skip
    growth = table.set_index("headcount_band")["growth"] if "growth" in free else None
    lo, hi = icp.segment.sweet_spot or (icp.segment.headcount_min, icp.segment.headcount_max)
    a_tier = tiers.set_index("tier")
    parts = []
    if growth is not None and len(growth) > 1:
        parts.append("Hiring rises with real headcount: growth "
                     + ", ".join(f"{b} staff {v:.2f}" for b, v in growth.items()))  # fmt: skip
    if {"A", "B"} <= set(a_tier.index):
        parts.append(
            f"tier A median {a_tier.loc['A', 'median_headcount']:.0f} staff vs "
            f"{a_tier.loc['B', 'median_headcount']:.0f} in B"
        )
    in_low = int((lead["headcount"] < lo).sum())
    parts.append(f"{in_low} of {len(lead)} researched leads are below the {lo}-{hi} sweet spot")
    return Finding(
        "f3_tiers", "Bigger groups hire more, and hiring is what separates A from B",
        RESEARCHED, "; ".join(parts) + ".", table, signals_by_size_chart(table, free),
        {"by_tier": tiers},
    )  # fmt: skip


# F4 (appendix). Registry size vs the agent's headcount.


def f4_size_appendix(d: Inputs, icp: IcpConfig) -> Finding:
    lead = leads(d)
    seg = icp.segment
    table = lead[["group_id", "name", "headcount_mid", "headcount", "headcount_source"]]
    table = table.assign(ratio=(table["headcount"] / table["headcount_mid"]).round(2))
    outside = (lead["headcount"] < seg.headcount_min) | (lead["headcount"] > seg.headcount_max)
    headline = (
        f"Median agent/registry headcount ratio {table['ratio'].median():.2f}; "
        f"{int((table['ratio'] > 1.5).sum())} groups above 1.5x, "
        f"{int((table['ratio'] < 1 / 1.5).sum())} below 1/1.5x; {int(outside.sum())} of "
        f"{len(table)} fall outside {seg.headcount_min}-{seg.headcount_max}. Caveat: the "
        "regrade falls back to the registry midpoint when the evidence states no number."
    )
    return Finding("f4_size", "Registry size vs agent headcount (appendix)", RESEARCHED,
                   headline, table)  # fmt: skip


# F5. Regions.


def region_name(code: str | None, icp: IcpConfig) -> str:
    if icp.market.country == "FR":
        return REGIONS_FR.get(code or "", code or "unknown")
    return code or "unknown"


def f5_regions(d: Inputs, icp: IcpConfig) -> Finding:
    m = d.market
    lead = leads(d)
    counts = {
        "market": m["region"].value_counts(),
        "in_segment": m[m["in_segment"]]["region"].value_counts(),
        "researched": lead["region"].value_counts(),
        "tier_a": lead[lead["tier"] == "A"]["region"].value_counts(),
        "queue": lead[lead["queue_rank"].notna()]["region"].value_counts(),
    }
    table = pd.DataFrame(counts).fillna(0).astype(int)
    table = table[table["in_segment"] > 0].sort_values(["in_segment", "queue"], ascending=False)
    table["tier_a_rate"] = (
        table["tier_a"] / table["researched"].where(table["researched"] > 0)
    ).round(2)
    table = table.rename_axis("region").reset_index()
    table.insert(1, "region_name", table["region"].map(lambda c: region_name(c, icp)))
    queue = table["queue"].sum()
    top = table.sort_values("queue", ascending=False).head(3)
    headline = (
        f"{len(table)} regions have in-segment groups. The queue concentrates: "
        + ", ".join(f"{r.region_name} {r.queue}" for r in top.itertuples())
        + f" of {queue} places ({pct(top['queue'].sum() / queue)}). Tier A rate among "
        "researched leads: "
        + ", ".join(f"{r.region_name} {pct(r.tier_a_rate)}"
                    for r in table[table["researched"] >= 10].sort_values(
                        "tier_a_rate", ascending=False).itertuples())
        + " (regions with 10+ researched)."
    )  # fmt: skip
    return Finding("f5_regions", "Where the segment is, and where the best leads are",
                   f"{MARKET} + {RESEARCHED}", headline, table, regions_chart(table))  # fmt: skip


# F6. Product mix.


def mix_label(lines, icp: IcpConfig) -> str:
    order = list(icp.market.product_lines or icp.market.rge_domains)
    lines = sorted(set(lines if lines is not None else []), key=lambda x: order.index(x)
                   if x in order else len(order))  # fmt: skip
    if not lines:
        return "unknown (no certification)"
    names = [icp.market.line_labels.get(x, x) for x in lines]
    return f"{names[0]} only" if len(names) == 1 else " + ".join(names)


def f6_product_mix(d: Inputs, icp: IcpConfig) -> Finding:
    m = d.market.assign(mix=d.market["product_lines"].map(lambda x: mix_label(x, icp)))
    r = researched(d)
    r = r[~r["is_reference"]].assign(mix=r["product_lines"].map(lambda x: mix_label(x, icp)))
    groups = {
        "Market": m,
        "In segment": m[m["in_segment"]],
        "Researched": r,
        "Tier A": r[r["tier"] == "A"],
    }
    keep = list(m["mix"].value_counts().index[:MAX_MIX])
    rows = []
    for pop, g in groups.items():
        mix = g["mix"].where(g["mix"].isin(keep), "other")
        for label, n in mix.value_counts().items():
            rows.append({"population": pop, "mix": label, "groups": int(n),
                         "share": round(n / len(g), 3)})  # fmt: skip
    table = pd.DataFrame(rows)
    multi = {pop: (g["product_lines"].map(lambda x: len(x) if x is not None else 0) > 1).mean()
             for pop, g in groups.items()}  # fmt: skip
    headline = (
        "Share of groups certified for more than one product line: "
        + ", ".join(f"{p} {pct(v)}" for p, v in multi.items())
        + (
            ". The researched set is picked by the pre-score, which rewards the mix, so "
            "compare market vs in segment."
        )
    )
    order = [*keep, "other"]
    return Finding("f6_product_mix", "Larger installers run more product lines",
                   f"{MARKET} + {RESEARCHED}", headline, table,
                   mix_chart(table, order, list(groups)))  # fmt: skip


# F7. The website the SDR needs, and what the agent sees on it.

SAME, DIFFERENT, FOUND, NONE = (
    "same as registry",
    "different from registry",
    "found, registry had none",
    "none found",
)


def f7_websites(d: Inputs, icp: IcpConfig) -> Finding:
    r = researched(d)
    agent = d.signals.drop_duplicates("group_id").set_index("group_id")["website"]
    r = r.assign(agent_website=r["group_id"].map(agent))
    host = lambda u: website_host(u) if isinstance(u, str) else None
    reg, ag = r["website"].map(host), r["agent_website"].map(host)
    status = pd.Series(DIFFERENT, index=r.index)
    status[ag.isna()] = NONE
    status[ag.notna() & reg.isna()] = FOUND
    status[ag.notna() & (ag == reg)] = SAME
    table = pd.DataFrame({
        "group_id": r["group_id"], "name": r["name"], "registry_website": r["website"],
        "agent_website": r["agent_website"], "website_status": status,
        "pre_tech_maturity": r["pre_tech_maturity"], "tech_maturity": r["tech_maturity"],
        "tier": r["tier"],
    })  # fmt: skip
    counts = (
        table["website_status"].value_counts().reindex([SAME, DIFFERENT, FOUND, NONE])
        .fillna(0).astype(int).rename_axis("website_status").reset_index(name="groups")
    )  # fmt: skip
    tech = pd.crosstab(table["pre_tech_maturity"], table["tech_maturity"])
    tech.index = [f"pre-score tech {v:g}" for v in tech.index]
    tech.columns = [f"agent {v:g}" for v in tech.columns]
    n = len(table)
    c = counts.set_index("website_status")["groups"]
    has_site = table[table["pre_tech_maturity"] == 1]
    split = has_site["tech_maturity"].value_counts()
    headline = (
        f"For {c[DIFFERENT] + c[FOUND]} of {n} researched groups ({pct((c[DIFFERENT] + c[FOUND]) / n)}) "
        f"the agent's website is not the registry's: {c[FOUND]} had none in the registry, "
        f"{c[DIFFERENT]} a different one (check by hand: some are a sister company's site). "
        f"Of the {len(has_site)} the pre-score credits with a website, the agent finds a "
        f"project quote form or tool on {int(split.get(1.0, 0))} and only a plain contact "
        f"form on {int(split.get(0.5, 0))}."
    )
    return Finding("f7_websites", "The agent finds the website and reads how leads come in",
                   RESEARCHED, headline, table, websites_chart(counts),
                   {"counts": counts, "tech": tech.rename_axis("pre_score").reset_index()})  # fmt: skip


FINDINGS = [f1_funnel, f2_prescore, f3_tiers, f5_regions, f6_product_mix, f7_websites]
APPENDIX = [f4_size_appendix]


# Charts. The reference palette of the dataviz skill, light mode, validated:
# the blue ordinal ramp (250/450/650), categorical slots 1-5, blue vs orange.

INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE = "#2a78d6", "#eb6834"
RAMP = ["#86b6ef", "#2a78d6", "#104281"]
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#898781"]
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
WIDTH = 560
BAR = 20


def theme(chart: alt.TopLevelMixin, title: str, subtitle: str) -> alt.TopLevelMixin:
    return chart.properties(
        title=alt.TitleParams(title, subtitle=subtitle, anchor="start", color=INK,
                              subtitleColor=INK_2, fontSize=16, subtitleFontSize=12),
        background=SURFACE,
    ).configure(font=FONT).configure_view(stroke=None).configure_axis(
        gridColor=GRID, gridWidth=1, domainColor=AXIS, tickColor=AXIS, labelColor=MUTED,
        titleColor=INK_2, labelFontSize=12, titleFontSize=12, titleFontWeight="normal",
    ).configure_legend(
        labelColor=INK_2, titleColor=INK_2, labelFontSize=12, titleFontSize=12, orient="top",
    )  # fmt: skip


def funnel_chart(t: pd.DataFrame) -> alt.TopLevelMixin:
    # A log scale has no zero, so the bars start at 10 (the domain's floor).
    top = t["count"].max() * 2
    base = alt.Chart(t).encode(
        y=alt.Y("stage:N", sort=list(t["stage"]), title=None,
                axis=alt.Axis(labelLimit=260, labelColor=INK_2)),
        x=alt.X("count:Q", scale=alt.Scale(type="log", domain=[10, top], nice=False),
                title="count (log scale)", axis=alt.Axis(format="~s")),
        tooltip=["stage", alt.Tooltip("count:Q", format=","), "population"],
    )  # fmt: skip
    bars = base.mark_bar(size=BAR, cornerRadiusEnd=4).encode(
        x2=alt.datum(10),
        color=alt.Color("population:N", scale=alt.Scale(domain=[MARKET, RESEARCHED],
                        range=[RAMP[1], RAMP[2]]), legend=alt.Legend(title=None)),
    )  # fmt: skip
    labels = base.mark_text(align="left", dx=4, color=INK_2).encode(
        text=alt.Text("count:Q", format=",")
    )
    return theme((bars + labels).properties(width=WIDTH, height=alt.Step(30)),
                 "From registry rows to the SDR queue",
                 "Each bar is what is still in play after the stage")  # fmt: skip


def jitter(ids: pd.Series) -> pd.Series:
    """A stable offset in [0, 1) per group, so the chart is the same on every render."""
    return ids.map(lambda g: int(hashlib.sha256(g.encode()).hexdigest()[:8], 16) / 16**8)


def prescore_chart(t: pd.DataFrame) -> alt.TopLevelMixin:
    t = t.assign(kind=t["is_reference"].map({True: "reference", False: "lead"}),
                 jitter=jitter(t["group_id"]))  # fmt: skip
    x = alt.X("pre_score:O", title="pre-score (open data only)", sort="descending",
              axis=alt.Axis(labelAngle=0))  # fmt: skip
    y = alt.Y("score:Q", title="agent score (1-10)", scale=alt.Scale(domain=[1, 10]))
    dots = alt.Chart(t).mark_circle(size=64, opacity=0.8, stroke=SURFACE, strokeWidth=2).encode(
        x=x, y=y,
        # The jitter fills the middle half of each column.
        xOffset=alt.XOffset("jitter:Q", scale=alt.Scale(domain=[-0.5, 1.5])),
        color=alt.Color("kind:N", scale=alt.Scale(domain=["lead", "reference"],
                        range=[BLUE, ORANGE]), legend=alt.Legend(title=None)),
        tooltip=["name", "pre_score", "score", "tier"],
    )  # fmt: skip
    medians = alt.Chart(t[t["kind"] == "lead"]).mark_tick(
        color=INK, thickness=2, size=56
    ).encode(x=x, y=alt.Y("median(score):Q"), tooltip=[alt.Tooltip("median(score):Q",
             title="median score")])  # fmt: skip
    return theme((dots + medians).properties(width=WIDTH, height=320),
                 "The pre-score finds the segment, not the best leads",
                 "Researched groups, one dot each; the black tick is the leads' median")  # fmt: skip


def signals_by_size_chart(t: pd.DataFrame, free: list[str]) -> alt.TopLevelMixin:
    """Emphasis: growth is the story, the other signals are context in gray."""
    names = {s: s.replace("_", " ") for s in free}
    long = t.melt(id_vars=["headcount_band", "groups"], value_vars=free,
                  var_name="signal", value_name="mean")  # fmt: skip
    long["signal"] = long["signal"].map(names)
    # n on the axis: the outer bands are small.
    band = {b: f"{b} (n={n})" for b, n in zip(t["headcount_band"].astype(str), t["groups"],
                                                strict=True)}  # fmt: skip
    order = list(band.values())
    long["headcount_band"] = long["headcount_band"].astype(str).map(band)
    focus = names.get("growth")
    domain = [focus, *[n for n in names.values() if n != focus]] if focus else list(names.values())
    grays = [MUTED, AXIS, "#a8a7a0"]
    colors = [BLUE, *grays][: len(domain)] if focus else CATEGORICAL[: len(domain)]
    base = alt.Chart(long).encode(
        x=alt.X("headcount_band:O", sort=order, title="headcount (agent), staff",
                axis=alt.Axis(labelAngle=0)),
        y=alt.Y("mean:Q", title="mean signal value", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("signal:N", sort=domain, scale=alt.Scale(domain=domain, range=colors),
                        legend=alt.Legend(title=None)),
        tooltip=["headcount_band", "signal", alt.Tooltip("mean:Q", format=".2f"), "groups"],
    )  # fmt: skip
    lines = base.mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round")
    dots = base.mark_circle(size=64, opacity=1, stroke=SURFACE, strokeWidth=2)
    last = long[long["headcount_band"] == order[-1]]
    ends = (
        alt.Chart(last)
        .mark_text(align="left", dx=8, color=INK_2)
        .encode(x=alt.X("headcount_band:O", sort=order), y="mean:Q", text="signal:N")
    )
    return theme((lines + dots + ends).properties(width=WIDTH, height=300),
                 "Bigger groups hire more",
                 "Researched leads; signals the size curve doesn't set")  # fmt: skip


def regions_chart(t: pd.DataFrame) -> alt.TopLevelMixin:
    layers = ["in_segment", "researched", "queue"]
    names = {"in_segment": "in segment", "researched": "researched", "queue": "in the queue"}
    long = t.melt(id_vars=["region_name"], value_vars=layers, var_name="layer",
                  value_name="groups")  # fmt: skip
    long["layer"] = long["layer"].map(names)
    # Overlaid, not stacked: the widest layer is drawn first, the queue on top.
    long = long.sort_values("layer", key=lambda s: s.map(list(names.values()).index))
    order = list(t["region_name"])
    chart = alt.Chart(long).mark_bar(size=BAR, cornerRadiusEnd=4).encode(
        y=alt.Y("region_name:N", sort=order, title=None,
                axis=alt.Axis(labelLimit=220, labelColor=INK_2)),
        x=alt.X("groups:Q", stack=None, title="groups"),
        color=alt.Color("layer:N", sort=list(names.values()),
                        scale=alt.Scale(domain=list(names.values()), range=RAMP),
                        legend=alt.Legend(title=None)),
        tooltip=["region_name", "layer", "groups"],
    )  # fmt: skip
    return theme(chart.properties(width=WIDTH, height=alt.Step(26)),
                 "Where the segment is, and where the queue is",
                 "In segment: market (open data); researched and queue: agent")  # fmt: skip


def mix_chart(t: pd.DataFrame, order: list[str], pops: list[str]) -> alt.TopLevelMixin:
    order = [o for o in order if o in set(t["mix"])]
    t = t.assign(mix_order=t["mix"].map({m: i for i, m in enumerate(order)}))
    chart = alt.Chart(t).mark_bar(size=BAR + 8, stroke=SURFACE, strokeWidth=2).encode(
        y=alt.Y("population:N", sort=pops, title=None, axis=alt.Axis(labelColor=INK_2)),
        x=alt.X("share:Q", stack="normalize", title="share of groups",
                axis=alt.Axis(format="%")),
        color=alt.Color("mix:N", sort=order,
                        scale=alt.Scale(domain=order, range=CATEGORICAL[:len(order)]),
                        legend=alt.Legend(title=None, columns=3, labelLimit=240)),
        order=alt.Order("mix_order:Q"),
        tooltip=["population", "mix", "groups", alt.Tooltip("share:Q", format=".0%")],
    )  # fmt: skip
    return theme(chart.properties(width=WIDTH, height=alt.Step(40)),
                 "Larger installers run more product lines",
                 "Certified product lines (registry); market and in segment: all groups; "
                 "researched and tier A: agent-scored leads")  # fmt: skip


def websites_chart(counts: pd.DataFrame) -> alt.TopLevelMixin:
    order = list(counts["website_status"])
    base = alt.Chart(counts).encode(
        y=alt.Y("website_status:N", sort=order, title=None,
                axis=alt.Axis(labelLimit=240, labelColor=INK_2)),
        x=alt.X("groups:Q", title="researched groups"),
        tooltip=["website_status", "groups"],
    )  # fmt: skip
    bars = base.mark_bar(size=BAR, cornerRadiusEnd=4, color=BLUE)
    labels = base.mark_text(align="left", dx=4, color=INK_2).encode(text="groups:Q")
    return theme((bars + labels).properties(width=WIDTH, height=alt.Step(34)),
                 "The agent's website vs the registry's",
                 "Researched groups: the website the agent used for its evidence")  # fmt: skip


# `icp-scout insights`


def run(icp: IcpConfig, data_dir: str | Path = "data") -> list[Finding]:
    """Every finding to data/insights/: <id>.csv, <id>.vl.json, <id>_<table>.csv."""
    d = load(data_dir)
    out = Path(data_dir) / "insights"
    out.mkdir(parents=True, exist_ok=True)
    findings = [f(d, icp) for f in FINDINGS + APPENDIX]
    for f in findings:
        f.data.to_csv(out / f"{f.id}.csv", index=False)
        for name, table in f.tables.items():
            table.to_csv(out / f"{f.id}_{name}.csv", index=False)
        if f.chart is not None:
            (out / f"{f.id}.vl.json").write_text(f.chart.to_json(), encoding="utf-8")
    return findings


def report(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        lines += [f"{f.id}  {f.title}  [{f.population}]", f"  {f.headline}", ""]
    return "\n".join(lines).rstrip()
