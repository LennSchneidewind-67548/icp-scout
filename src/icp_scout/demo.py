"""WP5. What the Streamlit demo shows, as pure functions over the pipeline's files.

The app (app/streamlit_app.py) only lays out widgets; everything it computes
comes from here, where it is tested. Nothing here calls a model or the network:
the app reads data/ and the recorded transcripts, and re-scores with
`score.score`, which is pure (ADR 0002). That is what makes the weight sliders
live and the demo work offline.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import altair as alt
import pandas as pd

from icp_scout import insights, score
from icp_scout.config import IcpConfig

DEFAULT_DATA = Path("data")
DEFAULT_RECORDINGS = Path("fixtures/llm")
# The command that writes each file, for the app's "missing file" message.
WRITTEN_BY = {
    "market.parquet": "icp-scout source",
    "signals.parquet": "icp-scout research",
    "scored.parquet": "icp-scout score",
    "funnel.json": "icp-scout source",
}
SEARCH_TOOLS = {"web_search", "WebSearch"}
FETCH_TOOLS = {"web_fetch", "WebFetch"}


class MissingData(FileNotFoundError):
    """A pipeline output the demo needs is not there; the message names the command."""


@dataclass
class DemoData:
    market: pd.DataFrame
    signals: pd.DataFrame
    scored: pd.DataFrame
    funnel: dict
    regrades: dict[str, dict]  # group_id -> regrade result, status ok only
    research: dict[str, dict]  # group_id -> the agent's validated answer
    insights: dict[str, dict] = field(default_factory=dict)  # finding id -> Vega-Lite spec
    ledger: list[dict] = field(default_factory=list)


def load_env(path: str | Path = ".env") -> None:
    """Read only the ICP_SCOUT_* lines of .env: the app never needs an API key."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip().startswith("ICP_SCOUT_"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def data_dir() -> Path:
    return Path(os.environ.get("ICP_SCOUT_DATA") or DEFAULT_DATA)


def recordings_dir() -> Path:
    return Path(os.environ.get("ICP_SCOUT_RECORDINGS") or DEFAULT_RECORDINGS)


def load(data_dir: str | Path) -> DemoData:
    data_dir = Path(data_dir)
    for name, command in WRITTEN_BY.items():
        if not (data_dir / name).exists():
            raise MissingData(f"{data_dir / name} not found: run `{command}` first")
    research = {}
    for path in sorted((data_dir / "research").glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        research[r["group_id"]] = r.get("result") or {}
    specs = {}
    for f in insights.FINDINGS:
        path = data_dir / "insights" / f"{f.__name__}.vl.json"
        if path.exists():
            specs[f.__name__] = json.loads(path.read_text(encoding="utf-8"))
    ledger_path = data_dir / "ledger.jsonl"
    ledger = (
        [json.loads(x) for x in ledger_path.read_text(encoding="utf-8").splitlines() if x]
        if ledger_path.exists()
        else []
    )
    return DemoData(
        market=pd.read_parquet(data_dir / "market.parquet"),
        signals=pd.read_parquet(data_dir / "signals.parquet"),
        scored=pd.read_parquet(data_dir / "scored.parquet"),
        funnel=json.loads((data_dir / "funnel.json").read_text(encoding="utf-8")),
        regrades=score.load_regrades(data_dir),
        research=research,
        insights=specs,
        ledger=ledger,
    )


# Weights and re-ranking


def with_weights(icp: IcpConfig, weights: dict[str, float]) -> IcpConfig:
    """A copy of the config with new signal weights. 0 switches a signal off; all 0
    is rejected (the score would divide by zero)."""
    unknown = set(weights) - {s.id for s in icp.signals}
    if unknown:
        raise ValueError(f"unknown signals: {sorted(unknown)}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must not be negative")
    new = [weights.get(s.id, s.weight) for s in icp.signals]
    if not any(new):
        raise ValueError("at least one signal needs a weight above 0")
    # model_copy skips validation, so the Signal model's weight > 0 does not stop a 0.
    signals = [s.model_copy(update={"weight": w}) for s, w in zip(icp.signals, new, strict=True)]
    return icp.model_copy(update={"signals": signals})


def config_weights(icp: IcpConfig) -> dict[str, float]:
    return {s.id: s.weight for s in icp.signals}


def rerank(icp: IcpConfig, data: DemoData, weights: dict[str, float]) -> pd.DataFrame:
    """The scored table under `weights`, with `rank_change` against the config weights
    (positive: moved up)."""
    base = score.score(icp, data.signals, data.market, data.regrades)
    new = score.score(with_weights(icp, weights), data.signals, data.market, data.regrades)
    before = base.set_index("group_id")["rank"]
    new["rank_change"] = (new["group_id"].map(before) - new["rank"]).astype("Int64")
    return new


def queue_table(icp: IcpConfig, data: DemoData, table: pd.DataFrame) -> pd.DataFrame:
    """The Queue tab's columns, from a `rerank` table."""
    region = data.market.set_index("group_id")["region"]
    t = table.assign(
        region=table["group_id"].map(region).map(lambda c: insights.region_name(c, icp)),
        queue=table["queue_rank"].astype(object).where(table["queue_rank"].notna(), None),
    )
    t.loc[t["is_reference"], "queue"] = "calibration"
    t["queue"] = t["queue"].map(lambda q: "" if q is None else str(q))
    cols = ["rank", "rank_change", "name", "score", "tier", "region", "queue", "reason_en",
            "group_id"]  # fmt: skip
    return t[cols]


def queue_moves(base: pd.DataFrame, new: pd.DataFrame, size: int) -> tuple[list[str], list[str]]:
    """The leads (names) that entered and left the top `size` of the queue."""

    def top(t: pd.DataFrame) -> set[str]:
        q = t["queue_rank"]
        return set(t.loc[q.notna() & (q <= size), "group_id"])

    a, b = top(base), top(new)
    names = dict(zip(new["group_id"], new["name"], strict=True))
    return sorted(names[g] for g in b - a), sorted(names[g] for g in a - b)


# One lead


def lead_card(data: DemoData, group_id: str) -> dict:
    """Everything the Lead tab shows for one group."""
    row = data.scored[data.scored["group_id"] == group_id]
    if row.empty:
        raise KeyError(f"{group_id} was not researched")
    s = row.iloc[0]
    m = data.market[data.market["group_id"] == group_id]
    m = m.iloc[0] if len(m) else None
    rg = data.regrades.get(group_id) or {}
    answer = data.research.get(group_id) or {}
    signals = []
    for r in data.signals[data.signals["group_id"] == group_id].itertuples():
        grade = (rg.get("grades") or {}).get(r.signal) or {}
        signals.append({
            "signal": r.signal,
            "agent_value": r.value,
            "value": float(s[r.signal]) if r.signal in s else r.value,
            "regrade_basis_en": grade.get("basis_en"),
            "found": bool(r.found),
            "rationale_en": r.rationale_en,
            "evidence": [
                {"quote": e["quote"], "quote_en": e["quote_en"], "url": e["url"]}
                for e in (r.evidence if r.evidence is not None else [])
            ],
            "flags": list(r.flags) if r.flags is not None else [],
        })  # fmt: skip
    first = data.signals[data.signals["group_id"] == group_id].iloc[0]
    return {
        "group_id": group_id,
        "name": s["name"],
        "score": float(s["score"]),
        "tier": s["tier"],
        "rank": int(s["rank"]),
        "queue_rank": None if pd.isna(s["queue_rank"]) else int(s["queue_rank"]),
        "is_reference": bool(s["is_reference"]),
        "reason_en": s["reason_en"],
        "headcount": None if pd.isna(s["headcount"]) else float(s["headcount"]),
        "headcount_source": s["headcount_source"],
        "headcount_basis_en": rg.get("headcount_basis_en"),
        "region": None if m is None else m.get("region"),
        "website": first["website"],
        "members": [] if m is None else list(m["member_names"]),
        "signals": signals,
        "facts": answer.get("facts") or {},
        "notes_en": first["notes_en"],
    }


# The research replay


@dataclass
class Step:
    kind: str  # "search", "fetch" or "record"
    text: str  # the query, the URL, or "" for the record
    record: dict | None = None  # the final answer, on the record step


@dataclass
class Replay:
    steps: list[Step]
    searches: int
    fetches: int
    tokens: int
    usd: float  # API money, or the CLI's list-price estimate for claude-code runs
    notional: bool  # True when usd is an estimate, not money spent


def replay_steps(recordings_dir: str | Path, ledger: list[dict], group_id: str) -> Replay | None:
    """The lead's last recorded research run, step by step. None without a recording."""
    lines = [x for x in ledger if x.get("lead") == group_id and x.get("purpose") == "research"]
    if not lines:
        return None
    last = lines[-1]
    path = Path(recordings_dir) / "research" / f"{last['key']}.json"
    if not path.exists():
        return None
    rec = json.loads(path.read_text(encoding="utf-8"))
    if "transcript" in rec:  # claude-code: one recording is the whole run
        blocks = [
            b
            for msg in rec["transcript"]
            if msg.get("type") == "assistant"
            for b in (msg.get("message") or {}).get("content") or []
            if isinstance(b, dict)
        ]
        run = [last]
    else:  # API: the last call's request carries the earlier turns of a paused run
        blocks = [
            b
            for msg in rec["request"].get("messages", [])
            if msg["role"] == "assistant" and isinstance(msg["content"], list)
            for b in msg["content"]
        ] + rec["response"]["content"]
        # Every call of this lead's run on the same model, each recording once.
        seen, run = set(), []
        for x in lines:
            if x["model"] == last["model"] and x["key"] not in seen:
                seen.add(x["key"])
                run.append(x)
    steps = []
    for b in blocks:
        if b.get("type") not in ("tool_use", "server_tool_use"):
            continue
        name, inp = b.get("name"), b.get("input") or {}
        if name in SEARCH_TOOLS:
            steps.append(Step("search", inp.get("query", "")))
        elif name in FETCH_TOOLS:
            steps.append(Step("fetch", inp.get("url", "")))
        elif isinstance(inp, dict) and "signals" in inp:
            steps.append(Step("record", "", inp))
    keys = ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens")
    notional = last.get("backend") == "claude-code"
    return Replay(
        steps=steps,
        searches=sum(s.kind == "search" for s in steps),
        fetches=sum(s.kind == "fetch" for s in steps),
        tokens=int(sum(x.get(k) or 0 for x in run for k in keys)),
        usd=round(sum(x.get("notional_usd" if notional else "usd") or 0 for x in run), 4),
        notional=notional,
    )


# The market map

MARKET, IN_SEGMENT = "Market", "In segment"
TIERS = ["Tier A", "Tier B", "Tier C"]
LAYERS = [MARKET, IN_SEGMENT, *TIERS[::-1]]
# Grey for context, the WP4 blue ramp for the tiers (darkest = best).
LAYER_COLORS = [insights.AXIS, insights.MUTED, *insights.RAMP]


def map_frame(data: DemoData, icp: IcpConfig) -> pd.DataFrame:
    """One point per located group, drawn back to front: market, in segment, researched."""
    m = data.market[data.market["lat"].notna() & data.market["lon"].notna()]
    t = m[["group_id", "name", "lat", "lon"]].copy()
    t["region"] = m["region"].map(lambda c: insights.region_name(c, icp))
    t["layer"] = m["in_segment"].map({True: IN_SEGMENT, False: MARKET})
    s = data.scored.set_index("group_id")
    hit = t["group_id"].isin(s.index)
    t.loc[hit, "layer"] = "Tier " + t.loc[hit, "group_id"].map(s["tier"])
    t["score"] = t["group_id"].map(s["score"])
    t["order"] = t["layer"].map({name: i for i, name in enumerate(LAYERS)})
    t["on_map"] = main_area(t["lat"]) & main_area(t["lon"])
    return t.sort_values("order", kind="stable").reset_index(drop=True)


def main_area(x: pd.Series) -> pd.Series:
    """Within 3 interquartile ranges of the median: drops the few far-off points (e.g.
    overseas territories) that would shrink the map to a dot."""
    q1, mid, q3 = x.quantile([0.25, 0.5, 0.75])
    return x.between(mid - 3 * (q3 - q1), mid + 3 * (q3 - q1))


def map_chart(frame: pd.DataFrame, cell: float = 0.15) -> alt.TopLevelMixin:
    """Points on lon/lat, no tiles, so it draws offline. The grey market layer is
    counted per `cell` degrees, so the browser draws a few thousand marks, not 18,000."""
    off = int((~frame["on_map"]).sum())
    frame = frame[frame["on_map"]]
    counts = frame["layer"].value_counts()
    labels = {name: f"{name} ({counts.get(name, 0):,})" for name in LAYERS}
    color = alt.Color(
        "label:N", title=None,
        scale=alt.Scale(domain=[labels[k] for k in LAYERS], range=LAYER_COLORS),
    )  # fmt: skip

    grid = frame[frame["layer"] == MARKET].assign(
        lat=lambda t: (t["lat"] / cell).round() * cell,
        lon=lambda t: (t["lon"] / cell).round() * cell,
    )
    grid = grid.groupby(["lat", "lon"]).size().rename("groups").reset_index()
    grid = grid.assign(label=labels[MARKET], lat=grid["lat"].round(3), lon=grid["lon"].round(3))
    market = alt.Chart(alt.Data(values=grid.to_dict("records"))).mark_square(
        filled=True, opacity=0.8, strokeWidth=0
    ).encode(
        longitude="lon:Q",
        latitude="lat:Q",
        color=color,
        size=alt.Size("groups:Q", scale=alt.Scale(range=[6, 40]), legend=None),
        tooltip=[alt.Tooltip("groups:Q", title="Groups in this cell")],
    )  # fmt: skip

    # In segment, then the researched by tier on top. Coordinates to ~100 m.
    top = frame[frame["layer"] != MARKET]
    top = top.assign(label=top["layer"].map(labels), lat=top["lat"].round(3),
                     lon=top["lon"].round(3))[
        ["lon", "lat", "label", "layer", "order", "name", "score", "region"]
    ]  # fmt: skip
    values = top.astype(object).where(top.notna(), None).to_dict("records")
    researched = alt.FieldOneOfPredicate(field="layer", oneOf=TIERS)
    points = (
        alt.Chart(alt.Data(values=values))
        .mark_circle(opacity=0.95)
        .encode(
            longitude="lon:Q",
            latitude="lat:Q",
            color=color,
            size=alt.condition(researched, alt.value(40), alt.value(10)),
            stroke=alt.condition(researched, alt.value(insights.SURFACE), alt.value(None)),
            order=alt.Order("order:Q"),
            tooltip=[
                alt.Tooltip("name:N", title="Group"),
                alt.Tooltip("layer:N", title="Layer"),
                alt.Tooltip("score:Q", title="Score", format=".1f"),
                alt.Tooltip("region:N", title="Region"),
            ],
        )
    )
    chart = alt.layer(market, points).project("equirectangular").properties(width=640, height=600)
    return insights.theme(
        chart,
        "Where the market is",
        f"{len(frame):,} groups; in segment highlighted, researched ones by tier"
        + (f"; {off} far-off groups (e.g. overseas) not drawn" if off else ""),
    )
