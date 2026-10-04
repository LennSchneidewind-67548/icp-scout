"""WP5. What the Streamlit demo shows, as pure functions over the pipeline's files.

The app (app/streamlit_app.py) only lays out widgets; everything it computes
comes from here, where it is tested. Nothing here calls a model or the network:
the app reads data/ and the recorded transcripts, and re-scores with
`score.score`, which is pure (ADR 0002). That is what makes the weight sliders
live and the demo work offline.
"""

import json
import math
import os
import re
from dataclasses import dataclass, field
from html import escape
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


# Short words the registry spells in capitals that are not acronyms, and legal forms.
LOWER_WORDS = {"DE", "DU", "DES", "LA", "LE", "LES", "ET", "EN", "AU", "AUX", "SUR"}
LEGAL_FORMS = {"SA", "SAS", "SASU", "SARL", "EURL", "SCOP", "SNC", "SCI", "GIE", "ETS"}


def display_name(raw: str | None) -> str:
    """A registry name for the screen: "ACME ENERGIE (ACME ENERGIE)" -> "Acme Energie".
    Drops a bracketed alias that repeats the name and title-cases all-capital names;
    legal forms, words without a vowel or with a digit, and one-word aliases (often
    acronyms: "(SLTE)") keep their capitals."""
    if not raw:
        return raw or ""
    name = re.sub(r"\s+", " ", raw).strip()
    head, *aliases = [x.strip() for x in re.split(r"[()]", name) if x.strip()]
    aliases = [a for a in dict.fromkeys(aliases) if a.replace(" ", "") != head.replace(" ", "")]
    if raw != raw.upper():
        return head + "".join(f" ({a})" for a in aliases)

    def word(m: re.Match) -> str:
        w = m.group(0)
        if w in LOWER_WORDS:
            return w.lower()
        if (
            w in LEGAL_FORMS
            or len(w) <= 2
            or not re.search(r"[AEIOUYÀ-Ý]", w)
            or re.search(r"\d", w)
        ):
            return w
        return w.capitalize()

    def title(text: str) -> str:
        text = re.sub(r"[A-ZÀ-Ý0-9]+", word, text)
        # "D'EMERAUDE" -> "d'Emeraude"; the first word keeps its capital.
        text = re.sub(r"(?<=\s)([DL])'", lambda m: m.group(1).lower() + "'", text)
        return text[0].upper() + text[1:]

    return title(head) + "".join(f" ({a if ' ' not in a else title(a)})" for a in aliases)


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
    t["name"] = t["name"].map(display_name)
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


def queue_changes(
    base: pd.DataFrame, new: pd.DataFrame, size: int
) -> tuple[list[tuple[str, int, int]], list[tuple[str, int, int]]]:
    """Like `queue_moves`, with each lead's rank before and after: (name, before, after)."""
    entered, left = queue_moves(base, new, size)
    before = dict(zip(base["name"], base["rank"], strict=True))
    after = dict(zip(new["name"], new["rank"], strict=True))
    return (
        sorted(((display_name(n), int(before[n]), int(after[n])) for n in entered),
               key=lambda x: x[2]),
        sorted(((display_name(n), int(before[n]), int(after[n])) for n in left),
               key=lambda x: x[2]),
    )  # fmt: skip


def moved_view(table: pd.DataFrame, base: pd.DataFrame, size: int) -> pd.DataFrame:
    """The queue's rows whose rank changed, plus the ones that left it; a `move` column
    says "entered", "left" or "". Best first."""
    entered, left = queue_moves(base, table, size)
    q = table["queue_rank"]
    in_queue = q.notna() & (q <= size)
    out = table["name"].isin(left)
    t = table[(in_queue & (table["rank_change"].fillna(0) != 0)) | out].copy()
    t["move"] = t["name"].map(lambda n: "entered" if n in entered else "left" if n in left else "")
    return t.sort_values("rank")


def moved_label(change, move: str = "") -> str:
    """The Moved column: NEW for a lead that entered the queue, else ▲3, ▼2 or –."""
    if move == "entered":
        return "NEW"
    if change is None or pd.isna(change) or change == 0:
        return "–"
    return f"▲{int(change)}" if change > 0 else f"▼{-int(change)}"


def why(reason_en: str | None) -> str:
    """The reason line without its leading "9.7 A | ", which the table already shows."""
    return re.sub(r"^\d+(\.\d+)? [A-Z] \| ", "", reason_en or "")


def contributions(weights: dict[str, float], values: dict[str, float]) -> dict[str, float]:
    """Points each signal adds to the base score of 1: 9 x weight x value / total weight."""
    total = sum(weights.values())
    return {s: 9 * w * float(values.get(s) or 0) / total for s, w in weights.items()}


def run_cost(ledger: list[dict]) -> float:
    """Every model call of the run at list price: API spend, or the CLI's estimate."""
    return round(sum(
        (x.get("notional_usd") if x.get("backend") == "claude-code" else x.get("usd")) or 0
        for x in ledger
    ), 2)  # fmt: skip


def last_run(ledger: list[dict]) -> str | None:
    """The date (YYYY-MM-DD) of the last research call, or None."""
    days = [x["at"][:10] for x in ledger if x.get("purpose") == "research" and x.get("at")]
    return max(days) if days else None


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
        "name": display_name(s["name"]),
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
    aim: str = ""  # what a fetch looked for (the agent's own prompt, English)
    found: str = ""  # one line on what came back: "8 results: a.fr, b.fr" or "1,200 words"


@dataclass
class Replay:
    steps: list[Step]
    searches: int
    fetches: int
    tokens: int
    usd: float  # API money, or the CLI's list-price estimate for claude-code runs
    notional: bool  # True when usd is an estimate, not money spent


def tool_results(rec: dict) -> dict[str, object]:
    """tool_use id -> its result's content, from a claude-code transcript or an API
    recording (the request's earlier turns and the response)."""
    if "transcript" in rec:
        msgs = [(m.get("message") or {}).get("content") for m in rec["transcript"]]
    else:
        msgs = [m["content"] for m in rec["request"].get("messages", [])]
        msgs.append(rec["response"]["content"])
    return {
        b["tool_use_id"]: b.get("content")
        for content in msgs
        if isinstance(content, list)
        for b in content
        if isinstance(b, dict) and str(b.get("type", "")).endswith("tool_result")
        and b.get("tool_use_id")
    }  # fmt: skip


def search_summary(result) -> str:
    """ "8 results: a.fr, b.fr, c.com" from a search result, or ""."""
    urls = re.findall(r"""['"]url['"]\s*:\s*['"](https?://[^'"]+)""", str(result or ""))
    hosts = list(dict.fromkeys(
        h.removeprefix("www.") for h in (re.sub(r"^https?://", "", u).split("/")[0] for u in urls)
    ))  # fmt: skip
    if not urls:
        return ""
    return f"{len(urls)} result{'s' if len(urls) != 1 else ''}: " + ", ".join(hosts[:3])


def fetch_summary(result) -> str:
    """ "Read about 1,200 words" from a fetch result, or "" (none, or encrypted)."""
    if isinstance(result, list):
        result = " ".join(x.get("text", "") for x in result if isinstance(x, dict))
    words = len(str(result or "").split()) if isinstance(result, str) else 0
    return f"Read about {round(words, -1):,} words" if words >= 20 else ""


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
    results = tool_results(rec)
    steps = []
    for b in blocks:
        if b.get("type") not in ("tool_use", "server_tool_use"):
            continue
        name, inp = b.get("name"), b.get("input") or {}
        result = results.get(b.get("id"))
        if name in SEARCH_TOOLS:
            steps.append(Step("search", inp.get("query", ""), found=search_summary(result)))
        elif name in FETCH_TOOLS:
            aim = re.split(r"(?<=\.)\s", inp.get("prompt") or "")[0].rstrip(".")
            aim = aim if len(aim) <= 110 else aim[:108].rsplit(" ", 1)[0] + " …"
            steps.append(Step("fetch", inp.get("url", ""), aim=aim, found=fetch_summary(result)))
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
# The app's data colours, from the deck's token sheet: zinc greys for context, then the
# tiers from grey to the accent, so the eye lands on tier A as on the slides. The steps
# differ in lightness too, so they hold in greyscale.
MARKET_GREY, SEGMENT_GREY = "#C8C8CE", "#8E8E96"
TIER_COLORS = {"A": "#E04E1B", "B": "#F2A07B", "C": "#52525B"}
LAYER_COLORS = [MARKET_GREY, SEGMENT_GREY, *(TIER_COLORS[t[-1]] for t in TIERS[::-1])]


def map_frame(data: DemoData, icp: IcpConfig) -> pd.DataFrame:
    """One point per located group, drawn back to front: market, in segment, researched."""
    m = data.market[data.market["lat"].notna() & data.market["lon"].notna()]
    t = m[["group_id", "name", "lat", "lon"]].copy()
    t["name"] = t["name"].map(display_name)
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
    market = alt.Chart(alt.Data(values=grid.to_dict("records"))).mark_circle(
        opacity=0.8, strokeWidth=0
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
            size=alt.condition(researched, alt.value(95), alt.value(12)),
            stroke=alt.condition(researched, alt.value("#FFFFFF"), alt.value(None)),
            strokeWidth=alt.value(1.5),
            order=alt.Order("order:Q"),
            tooltip=[
                alt.Tooltip("name:N", title="Group"),
                alt.Tooltip("layer:N", title="Status"),
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


# Charts in the app


# The saved specs keep the neutral palette (insights.py); the app swaps it for the deck's
# at display time, as the deck does, so both show the same colours.
APP_PALETTE = {
    insights.INK: "#1B1D20", insights.INK_2: "#3F3F46", insights.MUTED: "#52525B",
    insights.GRID: "#F0F0F2", insights.AXIS: "#E4E4E7", insights.LIGHT_GREY: MARKET_GREY,
    insights.MID_GREY: SEGMENT_GREY, insights.SOFT_GREY: "#A1A1AA",
    insights.ACCENT: TIER_COLORS["A"], insights.SLATES[1]: "#52525B",
}  # fmt: skip


def _restyle(text: str) -> str:
    return re.sub("|".join(APP_PALETTE), lambda m: APP_PALETTE[m.group(0)], text)


def app_spec(spec: dict) -> tuple[dict, str, str]:
    """A saved chart for the app: its title and subtitle taken out (the app shows them
    as a heading and a caption), the deck's palette and font, 13 px labels, white
    background."""
    spec = json.loads(json.dumps(spec))
    t = spec.pop("title", None) or {}
    title, subtitle = (t, "") if isinstance(t, str) else (t.get("text", ""), t.get("subtitle", ""))
    if isinstance(subtitle, list):
        subtitle = " ".join(subtitle)
    spec = json.loads(_restyle(json.dumps(spec)))
    spec["background"] = "#FFFFFF"
    c = spec.setdefault("config", {})
    c["font"] = "Geist"
    for part in ("axis", "legend"):
        c.setdefault(part, {}).update(labelFontSize=13, titleFontSize=13)
    c.setdefault("text", {})["fontSize"] = 14
    return spec, title, subtitle


def log_share(top: int):
    """n -> the bar length on a log scale where `top` is the full bar (the funnel)."""
    return lambda n: math.log10(n) / math.log10(top) if n > 1 and top > 1 else 0.0


def logo_svg(vendor: str) -> str:
    """The app name for the top bar, as an SVG: "ICP Scout" and "for <vendor>" in grey."""
    width = 120 + 10 * len(f"for {vendor}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="32" '
        f'viewBox="0 0 {width} 32"><text y="23" font-family="Geist, Segoe UI, '
        'sans-serif"><tspan font-size="20" font-weight="600" fill="#1B1D20" '
        'letter-spacing="-0.4">ICP Scout</tspan>'
        f'<tspan dx="10" font-size="16" fill="#71717A">for {escape(vendor)}</tspan></text></svg>'
    )
