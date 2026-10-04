"""WP5. The demo: Market, Queue (with weights, the lead and its replay), Insights.

`streamlit run app/streamlit_app.py`. Reads data/ (or $ICP_SCOUT_DATA) and the
recorded transcripts ($ICP_SCOUT_RECORDINGS); makes no model call and no network
request. Everything it computes is in icp_scout.demo; this file lays out widgets.
The look follows the redesign's token sheet (.streamlit/config.toml): top
navigation, no sidebar, colour only for tiers and queue movement.
"""

import re
import time
from datetime import date
from html import escape
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from icp_scout import config, demo, insights

st.set_page_config(page_title="ICP Scout", layout="wide")
demo.load_env()
icp = config.load()
DATA_DIR = str(demo.data_dir())
RECORDINGS = str(demo.recordings_dir())

# The deck's tokens (see .streamlit/config.toml): ink, zinc greys, one accent.
INK, INK_2, MUTED, LINE = "#1B1D20", "#3F3F46", "#52525B", "#E4E4E7"
ACCENT, ACCENT_TXT, ACCENT_TINT = "#E04E1B", "#C2410C", "#FCEEE7"
# Up and down in the queue: green and red, apart from the accent's orange.
POS, NEG = "#166534", "#B42318"
# Tier badges, from the accent to grey: (background, text), each AA on its background.
TIER_TINT = {"A": ("#C2410C", "#FFFFFF"), "B": ("#FCEEE7", "#9A3412"),
             "C": ("#F0F0EC", "#52525B")}  # fmt: skip
TIER_TEXT = {"A": "#C2410C", "B": "#B45309", "C": "#71717A"}
ROW_TINT = {"entered": "#E7F5EC", "left": "#FBEAE9"}

st.html("""<style>
/* The top bar is 64 px and overlays the page: start below it. */
.block-container {padding: 5.25rem 3rem 2rem; max-width: none}
header[data-testid="stHeader"] {border-bottom: 1px solid #E4E4E7; background: #FDFDFB}
[data-testid="stTopNavLink"] p {font-size: 16px; font-weight: 500; color: #52525B}
[data-testid="stTopNavLink"][aria-current="page"] {box-shadow: inset 0 -2px 0 #E04E1B;
  border-radius: 0}
[data-testid="stTopNavLink"][aria-current="page"] p {font-weight: 600; color: #1B1D20}
/* The deck's headings: semibold, tight tracking. */
h1, h2, h3, h4 {letter-spacing: -0.02em}
/* Cards like the deck's chart panels: white on the off-white page. */
[class*="st-key-card_"] {background: #FFFFFF; border-radius: 16px}
/* The table's hover toolbar (search, download) covers the controls above it. */
[data-testid="stDataFrame"] [data-testid="stElementToolbar"] {display: none}
.st-key-page_head {border-bottom: 2px solid #1B1D20; padding-bottom: 14px !important;
  margin-bottom: 4px}
.st-key-page_head h2 {padding: 0; line-height: 1.1}
/* Streamlit pulls a heading's next element up by 17 px; here the rule comes next. */
.st-key-page_head [data-testid="stMarkdownContainer"] {margin-bottom: 0}
.eyebrow {font-size: 13px; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
  color: #C2410C; margin: 0 0 8px}
.kv a, .facts a {color: #C2410C}
.fun-head {display: flex; justify-content: space-between; align-items: baseline;
  font-size: 18px; color: #3F3F46}
.fun-head span + span {font-size: 15px; color: #71717A}
.fun-num {font-size: 44px; line-height: 1.05; font-weight: 600; letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums}
.fun-bar {height: 12px; border-radius: 6px; background: #F0F0EC; overflow: hidden;
  display: flex; margin-top: 8px}
.fun-conv {font-size: 16px; color: #52525B; padding: 8px 0 14px}
.legend {display: flex; gap: 18px; flex-wrap: wrap; font-size: 15px; color: #3F3F46}
.legend span {display: flex; align-items: center; gap: 8px}
.legend i {width: 11px; height: 11px; border-radius: 50%; display: inline-block}
.step {display: grid; grid-template-columns: 36px 1fr; gap: 0 16px}
.step .rail {display: flex; flex-direction: column; align-items: center}
.step .dot {width: 30px; height: 30px; flex: none; border-radius: 50%; display: flex;
  align-items: center; justify-content: center; font-size: 14px; font-weight: 600;
  border: 1.5px solid #D4D4D8; background: #FFFFFF}
.step.done .dot {border-color: #1B1D20}
.step.now .dot {background: #E04E1B; color: #FFFFFF; border-color: #E04E1B}
.step.later {opacity: .35}
.step .line {width: 1.5px; flex: 1; background: #E4E4E7; min-height: 10px}
.step .body {padding: 2px 0 10px; display: flex; flex-direction: column; gap: 4px;
  min-width: 0}
.step .head {display: flex; align-items: center; gap: 12px; min-width: 0}
.step .kind {font-size: 15px; font-weight: 600; width: 62px; flex: none}
.step code {font-family: "Geist Mono", monospace; font-size: 14px; padding: 3px 10px;
  border-radius: 6px; background: #F4F4F1;
  color: #1B1D20; white-space: nowrap; overflow: hidden; text-overflow: ellipsis}
.step .result {font-size: 15px; color: #52525B; padding-left: 74px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis}
.kv {display: grid; grid-template-columns: 1fr 1fr 2fr; gap: 16px; margin: 4px 0 8px;
  font-size: 16px}
.kv-label {font-size: 13px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: #71717A; margin-bottom: 2px}
.kv-note {font-size: 14px; color: #71717A; margin-top: 2px}
.facts {display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; font-size: 15px}
.facts > div:nth-child(odd) {color: #52525B}
.step .found {margin: 4px 0 0 74px; border: 1px solid #E4E4E7; border-left: 3px solid #E04E1B;
  border-radius: 0 10px 10px 0; background: #FFFFFF}
.step .found div {display: grid; grid-template-columns: 220px 48px 1fr; gap: 0 16px;
  padding: 6px 14px; border-bottom: 1px solid #EDEDF0; font-size: 15px;
  align-items: baseline}
.step .found div:last-child {border-bottom: none}
.step .found em {color: #52525B; font-style: normal}
</style>""")


@st.cache_data(show_spinner="Loading the pipeline's files ...")
def load(data_dir: str) -> demo.DemoData:
    return demo.load(data_dir)


@st.cache_data
def rerank(_icp, config_id: str, data_dir: str, weights: tuple) -> pd.DataFrame:
    return demo.rerank(_icp, load(data_dir), dict(weights))


@st.cache_data
def map_spec(_icp, config_id: str, data_dir: str) -> dict:
    return demo.map_chart(demo.map_frame(load(data_dir), _icp)).to_dict()


@st.cache_data
def replay(recordings: str, data_dir: str, gid: str) -> demo.Replay | None:
    return demo.replay_steps(recordings, load(data_dir).ledger, gid)


try:
    data = load(DATA_DIR)
except demo.MissingData as e:
    st.error(str(e))
    st.stop()

CONFIG_ID = icp.model_dump_json()
BASE = demo.config_weights(icp)
LABELS = {s.id: s.label for s in icp.signals}
SIZE = icp.queue.size
SEG = icp.segment

# Widget state survives a page switch only if it is written back on every run.
for sid, w in BASE.items():
    st.session_state.setdefault(f"w_{sid}", round(w))
for k, v in {
    "view": "queue",
    "tier": "All",
    "region": "All regions",
    "lead_tab": "signals",
}.items():
    st.session_state.setdefault(k, v)
st.session_state.setdefault("lead", None)
st.session_state.setdefault("pick", 0)  # bumped to clear the table's selection
for k in [f"w_{sid}" for sid in BASE] + ["view", "tier", "region", "lead_tab"]:
    if k in st.session_state:
        st.session_state[k] = st.session_state[k]

weights = {sid: st.session_state[f"w_{sid}"] for sid in BASE}
if not any(weights.values()):
    weights = BASE
changed = [sid for sid in BASE if weights[sid] != round(BASE[sid])]
base = rerank(icp, CONFIG_ID, DATA_DIR, tuple(sorted(BASE.items())))
table = rerank(icp, CONFIG_ID, DATA_DIR, tuple(sorted(weights.items())))
entered, left = demo.queue_changes(base, table, SIZE)


def day(iso: str | None) -> str:
    d = date.fromisoformat(iso) if iso else None
    return f"{d.day} {d:%b %Y}" if d else "?"


def stamp() -> str:
    snap = (data.funnel.get("meta") or {}).get("today")
    return f"Open data {day(snap)} · agent run {day(demo.last_run(data.ledger))}"


def page_head(eyebrow: str, title: str, caption: str | None = None) -> None:
    """The deck's slide header: an accent eyebrow, the title, an ink rule."""
    with st.container(key="page_head", gap=None):
        st.html(f"<p class='eyebrow'>{escape(eyebrow)}</p>")
        st.header(title, anchor=False)
    if caption is not None:
        st.caption(caption)


def bar(segments: list[tuple[float, str]]) -> str:
    return "".join(f"<div style='width:{w:.1%};background:{c}'></div>" for w, c in segments)


# Market


def market_page() -> None:
    m, s = data.market, data.scored
    groups, seg = len(m), int(m["in_segment"].sum())
    leads = s[~s["is_reference"]]
    queue = leads[leads["queue_rank"].notna() & (leads["queue_rank"] <= SIZE)]
    log = demo.log_share(groups)

    def tiers_bar(rows: pd.DataFrame) -> list[tuple[float, str]]:
        n = len(rows)
        return [(log(n) * (rows["tier"] == t).sum() / n, demo.TIER_COLORS[t]) for t in "ABC"]

    stages = [
        ("Groups from open data", "registry + company register", groups,
         f"↓ {seg / groups:.1%} have {SEG.headcount_min}–{SEG.headcount_max} staff",
         [(log(groups), demo.MARKET_GREY)]),
        ("In segment", f"{SEG.headcount_min}–{SEG.headcount_max} staff", seg,
         f"↓ {len(s) / seg:.0%} researched by the agent (top pre-score)",
         [(log(seg), demo.SEGMENT_GREY)]),
        ("Researched by the agent", f"${demo.run_cost(data.ledger):,.0f} at list price",
         len(s), f"↓ top {SIZE} go to SDRs", tiers_bar(s)),
        ("SDR queue", "ranked by the rubric", len(queue), "", tiers_bar(queue)),
    ]  # fmt: skip

    funnel, where = st.columns([0.32, 0.68], gap="large")
    with funnel:
        page_head("Open data", "The market")
        st.markdown(f"<p style='font-size:18px;color:{MUTED};margin-bottom:28px'>"
                    f"Installer groups in {escape(icp.market.country)}, built from the "
                    f"certified-installer registry and the company register.<br>"
                    f"<span style='font-size:15px'>{escape(stamp())}</span></p>",
                    unsafe_allow_html=True)  # fmt: skip
        for label, source, value, conv, segs in stages:
            st.markdown(
                f"<div class='fun-head'><span>{escape(label)}</span><span>{escape(source)}"
                f"</span></div><div class='fun-num'>{value:,}</div>"
                f"<div class='fun-bar'>{bar(segs)}</div><div class='fun-conv'>{conv}</div>",
                unsafe_allow_html=True,
            )
        st.caption("Bar length on a log scale. Colour = tier, as on the map.")

    with where.container(border=True, key="card_map"):
        spec, title, subtitle = demo.app_spec(map_spec(icp, CONFIG_ID, DATA_DIR))
        spec["config"]["legend"]["disable"] = True
        spec["height"] = 640
        st.subheader(title, anchor=False)
        st.caption(subtitle)
        counts = demo.map_frame(data, icp)["layer"].value_counts()
        # The layers are exclusive, so the labels say so: the funnel's counts include them.
        dots = [(demo.MARKET, "Outside segment", demo.MARKET_GREY),
                (demo.IN_SEGMENT, "In segment, not researched", demo.SEGMENT_GREY)] + [
            (f"Tier {t}", f"Tier {t}", demo.TIER_COLORS[t]) for t in "ABC"
        ]  # fmt: skip
        st.markdown("<div class='legend'>" + "".join(
            f"<span><i style='background:{c}'></i>{label} · {counts.get(n, 0):,}</span>"
            for n, label, c in dots) + "</div>", unsafe_allow_html=True)  # fmt: skip
        st.vega_lite_chart(spec=spec, theme=None, width="stretch")


# Queue


def reset_weights() -> None:
    for sid, w in BASE.items():
        st.session_state[f"w_{sid}"] = round(w)
    st.session_state["view"] = "queue"  # "Moved" is empty after a reset


def clear_filters() -> None:
    st.session_state["tier"], st.session_state["region"] = "All", "All regions"


def show_moved() -> None:
    st.session_state["view"] = "moved"


def weight_sliders() -> None:
    st.caption(f"Re-ranks all {len(table)} researched leads with the rubric: same "
               "evidence, no model call. 0× ignores a signal, 5× counts it most.")  # fmt: skip
    for s, col in zip(icp.signals, st.columns(len(icp.signals), gap="large"), strict=True):
        col.slider(s.label, 0, 5, step=1, key=f"w_{s.id}", on_change=show_moved, format="%d×")
        if s.id in changed:
            col.markdown(f"<div style='color:{POS};font-size:15px;margin-top:-12px'>was "
                         f"{round(BASE[s.id])}×</div>", unsafe_allow_html=True)  # fmt: skip
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Reset to config", on_click=reset_weights, disabled=not changed)
        st.caption(f"{len(changed)} weight{'s' if len(changed) != 1 else ''} changed")
    if not any(st.session_state[f"w_{sid}"] for sid in BASE):
        st.warning("All weights are 0: showing the config weights.")


def queue_rows(view: str) -> pd.DataFrame:
    q = demo.queue_table(icp, data, table)
    if view == "moved":
        moved = demo.moved_view(table, base, SIZE)
        q = q.set_index("group_id").loc[moved["group_id"]].reset_index()
        q["move"] = list(moved["move"])
    else:
        q["move"] = ""
        if view == "queue":
            rank = table.set_index("group_id")["queue_rank"]
            q = q[q["group_id"].map(rank).le(SIZE)]
    q["moved"] = [demo.moved_label(c, mv) for c, mv in zip(q["rank_change"], q["move"],
                                                            strict=True)]  # fmt: skip
    q["why"] = q["reason_en"].map(demo.why).str.replace(" | ", " · ", regex=False)
    q.loc[q["move"] == "left", "name"] += " · left"
    q["place"] = pd.to_numeric(q["queue"], errors="coerce").astype("Int64")
    return q.reset_index(drop=True)


def styled(q: pd.DataFrame):
    def row(r: pd.Series) -> list[str]:
        tint = ROW_TINT.get(r["move"])
        css = f"background-color: {tint};" if tint else ""
        if r["move"] == "left":
            css += f"color: {MUTED};"
        return [css] * len(r)

    def moved(v: str) -> str:
        big = v == "NEW" or (v[:1] in "▲▼" and int(v[1:]) >= 3)
        c = "#A1A1AA" if not big else POS if v.startswith(("▲", "NEW")) else NEG
        return f"color: {c}; font-weight: 600"

    def tier(t: str) -> str:
        return f"color: {TIER_TEXT[t]}; font-weight: 600"

    return q.style.apply(row, axis=1).map(moved, subset=["moved"]).map(tier, subset=["tier"])


COLUMNS = {
    "place": st.column_config.NumberColumn("#", width=44, help="Place in the SDR queue"),
    "rank": st.column_config.NumberColumn("Rank", width=52,
                                          help="Rank of all researched leads"),
    "moved": st.column_config.TextColumn(
        "Moved", width=70, help="Places gained (▲) or lost (▼) against the config weights"
    ),
    "name": st.column_config.TextColumn("Company", width=260),
    "score": st.column_config.NumberColumn("Score", format="%.1f", width=60,
                                           help="1–10 from the rubric"),
    "tier": st.column_config.TextColumn("Tier", width=44),
    "region": st.column_config.TextColumn("Region", width="small"),
    "queue": st.column_config.TextColumn(
        "Queue", width=90, help="SDR queue place; references are calibration, not leads"
    ),
    "why": st.column_config.TextColumn("Why", width=640),
}
TABLE_HEIGHT = 520  # the table and the lead pane both end above a 1440x900 fold


def moves_html(rows: list[tuple[str, int, int]], head: str, colour: str, show: int = 4) -> str:
    """The first `show` leads that entered or left, with their rank before -> after."""
    items = "".join(
        f"<div style='display:flex;justify-content:space-between;gap:12px;padding:3px 0;"
        f"border-bottom:1px solid #EDEDF0'><span style='overflow:hidden;text-overflow:"
        f"ellipsis;white-space:nowrap'>{escape(n)}</span><span style='color:{MUTED};"
        f"white-space:nowrap;font-variant-numeric:tabular-nums'>{a} → {b}</span></div>"
        for n, a, b in rows[:show]
    )  # fmt: skip
    more = (f"<div style='color:{MUTED};font-size:15px;padding-top:4px'>+ {len(rows) - show} "
            "more in the table below</div>" if len(rows) > show else "")  # fmt: skip
    return (f"<div style='font-size:18px;font-weight:600;color:{colour};margin-bottom:4px'>"
            f"{'▲' if colour == POS else '▼'} {head}</div>{items or 'none'}{more}")


def queue_page() -> None:
    lead = st.session_state["lead"]
    if lead is not None and lead not in set(table["group_id"]):
        lead = st.session_state["lead"] = None
    researched = len(table)
    n_moved = len(demo.moved_view(table, base, SIZE))
    views = {"queue": f"Queue · {SIZE}", "moved": f"Moved · {n_moved}",
             "all": f"All researched · {researched}"}  # fmt: skip

    # One layout whether a lead is open or not: title, one row of controls, then the
    # table, with the lead beside it. Opening a lead only narrows the table.
    page_head("Research + rubric", "SDR queue")
    caption = st.empty()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.segmented_control("View", list(views), format_func=views.get, key="view",
                             required=True, label_visibility="collapsed")  # fmt: skip
        st.segmented_control("Tier", ["All", "A", "B", "C"], key="tier",
                             format_func=lambda t: t if t == "All" else f"Tier {t}",
                             required=True, label_visibility="collapsed")  # fmt: skip
        regions = sorted(demo.queue_table(icp, data, table)["region"].unique())
        st.selectbox("Region", ["All regions", *regions], key="region", width=240,
                     label_visibility="collapsed")  # fmt: skip
    badge = f" :green-badge[{len(changed)} changed]" if changed else ""
    with st.expander("Signal weights: re-rank the queue live" + badge):
        weight_sliders()

    view = st.session_state["view"]
    if changed and view == "moved":
        with st.container(border=True, key="card_moves"):
            for col, rows, word, colour in zip(
                st.columns(2, gap="large"), (entered, left), ("entered", "left"),
                (POS, NEG), strict=True,
            ):  # fmt: skip
                col.html(moves_html(rows, f"{len(rows)} {word} the top {SIZE}", colour))

    q = queue_rows(view)
    tier = st.session_state.get("tier") or "All"
    region = st.session_state.get("region") or "All regions"
    q = q[(q["tier"] == tier) | (tier == "All")]
    q = q[(q["region"] == region) | (region == "All regions")].reset_index(drop=True)
    noun = f"tier-{tier} lead" if tier != "All" else "lead"
    count = f"{len(q)} {noun}{'s' if len(q) != 1 else ''}"
    where = f" in {region}" if region != "All regions" else ""
    scope = {"queue": f"{count}{where} in the top {SIZE}", "moved": f"{count}{where} moved",
             "all": f"{count}{where}"}[view]  # fmt: skip
    top = int((q["score"] == q["score"].max()).sum()) if len(q) else 0
    ties = (f" {top} tie at {q['score'].max():.1f}: more evidence first, then by name."
            if top > 1 else "")  # fmt: skip
    caption.caption(f"{scope} · {researched} researched.{ties} "
                    + ("" if lead else "Tick a row's box to open the lead. ") + stamp())  # fmt: skip

    if lead is None:
        main, pane = st.container(), None
    else:
        main, pane = st.columns([0.42, 0.58], gap="medium")
    with main:
        if q.empty:
            if tier != "All" or where:
                st.info("No lead matches these filters.")
                st.button("Clear filters", on_click=clear_filters)
            else:
                st.info("No lead changed rank: move a weight to see the queue re-rank.")
        else:
            first = {"queue": "place"}.get(view, "rank")
            cols = [first] + (["moved"] if changed or view == "moved" else [])
            cols += ["name", "tier", "score"]
            if lead is None:
                cols += ["why", "region"] + (["queue"] if view == "all" else [])
            at = q.index[q["group_id"] == lead].tolist()
            event = st.dataframe(
                styled(q),
                hide_index=True,
                height=TABLE_HEIGHT,
                row_height=40,
                column_order=cols,
                column_config=COLUMNS,
                on_select="rerun",
                selection_mode="single-row",
                selection_default={"selection": {"rows": at}} if at else None,
                key=f"queue_{st.session_state['pick']}_{view}_{tier}_{region}",
            )  # fmt: skip
            rows = event.selection.rows
            if rows and q.loc[rows[0], "group_id"] != lead:
                st.session_state["lead"] = q.loc[rows[0], "group_id"]
                st.rerun()

    if lead is not None:
        with pane.container(border=True, height=TABLE_HEIGHT, key="card_lead"):
            lead_pane(lead)


def close_lead() -> None:
    st.session_state["lead"] = None
    st.session_state["pick"] += 1


def show_quotes(evidence: list[dict]) -> None:
    # Registry facts are quoted too, and they are not French: "as quoted", not "French".
    head = st.columns([0.4, 0.4, 0.2])
    for c, label in zip(head, ["As quoted", "English", "Source"], strict=True):
        c.caption(label)
    for e in evidence:
        quoted, english, source = st.columns([0.4, 0.4, 0.2])
        # A registry field ("headcount_bands_sum: ...") is data, not a quote; an English
        # quote needs no translation.
        if re.match(r"^[a-z_]+:", e["quote"]):
            quoted.markdown(":gray[Registry data]")
        elif e["quote"] == e["quote_en"]:
            quoted.markdown(":gray[Same as English]")
        else:
            quoted.markdown(f"«\u00a0{e['quote']}\u00a0»")
        english.markdown(e["quote_en"])
        host = (urlparse(e["url"]).netloc or e["url"]).removeprefix("www.")
        source.markdown(f"<a href='{escape(e['url'])}' title='{escape(e['url'])}' "
                        "style='display:block;white-space:nowrap;overflow:hidden;"
                        f"text-overflow:ellipsis'>{escape(host)} ↗</a>",
                        unsafe_allow_html=True)  # fmt: skip


def key_values(card: dict) -> str:
    """Headcount, website and the group's companies as a labelled grid."""
    cells = []
    if card["headcount"] is not None:
        note = f"<div class='kv-note'>{escape(card['headcount_source'] or '')}</div>"
        cells.append(("Headcount", f"~{card['headcount']:.0f} staff{note}"))
    if card["website"]:
        host = (urlparse(card["website"]).netloc or card["website"]).removeprefix("www.")
        cells.append(("Website", f"<a href='{escape(card['website'])}'>{escape(host)} ↗</a>"))
    if card["members"]:
        names = ", ".join(demo.display_name(m) for m in card["members"])
        n = len(card["members"])
        cells.append((f"{n} compan{'ies' if n != 1 else 'y'}", escape(names)))
    return "<div class='kv'>" + "".join(
        f"<div><div class='kv-label'>{k}</div><div>{v}</div></div>" for k, v in cells
    ) + "</div>"  # fmt: skip


def facts_html(facts: dict) -> str:
    """The agent's facts as a definition list: lists joined, keys in words."""

    def value(v) -> str:
        if isinstance(v, list):
            return "<br>".join(escape(str(x)) for x in v) or "–"
        if isinstance(v, dict):
            return "<br>".join(f"{escape(str(k))}: {escape(str(x))}" for k, x in v.items())
        return escape(str(v))

    return "<div class='facts'>" + "".join(
        f"<div>{escape(str(k).replace('_', ' ').capitalize())}</div><div>{value(v)}</div>"
        for k, v in facts.items()
    ) + "</div>"  # fmt: skip


def lead_pane(gid: str) -> None:
    card = demo.lead_card(data, gid)
    row = table[table["group_id"] == gid].iloc[0]
    rp = replay(RECORDINGS, DATA_DIR, gid)
    tabs = {
        "signals": f"Signals · {len(card['signals'])}",
        "replay": "Research replay" + (f" · {len(rp.steps)} steps" if rp else " · not recorded"),
    }
    tab = st.session_state.get("lead_tab") or "signals"
    region = insights.region_name(card["region"], icp) if card["region"] else ""
    qr = row["queue_rank"]
    place = ("calibration" if row["is_reference"] else
             "not in queue" if pd.isna(qr) else f"queue {int(qr)} of {SIZE}")  # fmt: skip
    change = row["rank_change"]
    moved = "" if pd.isna(change) or change == 0 else (
        f" <span style='color:{POS if change > 0 else NEG};font-weight:600'>"
        f"{demo.moved_label(change)}</span>")  # fmt: skip

    # One header for both views, so switching views does not move the page.
    top, close = st.columns([0.92, 0.08], vertical_alignment="top")
    bg, fg = TIER_TINT[row["tier"]]
    top.markdown(
        f"<div style='font-size:15px;color:{MUTED}'>Lead{' · ' + escape(region) if region else ''}"
        "</div><div style='display:flex;gap:14px;align-items:baseline;flex-wrap:wrap'>"
        f"<span style='font-size:32px;font-weight:600;line-height:1.2'>{escape(card['name'])}"
        f"</span></div><div style='display:flex;gap:14px;align-items:center;flex-wrap:wrap;"
        f"margin-top:6px;font-size:16px;color:{INK_2}'>"
        f"<span style='font-size:28px;font-weight:600;color:{INK}'>{row['score']:.1f}</span>"
        f"<span style='font-size:15px;font-weight:600;padding:2px 10px;border-radius:4px;"
        f"background:{bg};color:{fg}'>Tier {row['tier']}</span>"
        f"<span>Rank {int(row['rank'])} of {len(table)}{moved} · {place}</span></div>",
        unsafe_allow_html=True,
    )  # fmt: skip
    close.button("✕", on_click=close_lead, type="tertiary", help="Close the lead")

    st.segmented_control("Lead view", list(tabs), format_func=tabs.get, key="lead_tab", required=True,
                         label_visibility="collapsed")  # fmt: skip
    if tab == "signals":
        why = demo.why(row["reason_en"]).replace(" | ", " · ")
        st.markdown(f"<p style='font-size:17px;margin:4px 0 6px'>{escape(why)}</p>",
                    unsafe_allow_html=True)  # fmt: skip
        st.html(key_values(card))
        if card["headcount_source"] == "regrade" and card["headcount_basis_en"]:
            st.caption(f"Headcount regraded: {card['headcount_basis_en']}")
    if tab == "replay":
        replay_panel(gid)
        return

    values = {sig["signal"]: float(row[sig["signal"]]) for sig in card["signals"]}
    pts = demo.contributions(weights, values)
    st.markdown(f"<div style='color:{MUTED};font-size:15px;margin-bottom:-4px'>Points per "
                f"signal = 9 × value (0–1) × weight ÷ {sum(weights.values()):g} (all weights). "
                f"Score = 1.0 + {sum(pts.values()):.1f} = <strong style='color:{INK}'>"
                f"{row['score']:.1f}</strong></div>", unsafe_allow_html=True)  # fmt: skip
    for sig in card["signals"]:
        sid = sig["signal"]
        note = " :gray-badge[regraded]" if sig["regrade_basis_en"] else ""
        head = (f"{LABELS.get(sid, sid)}{note} &nbsp; **{values[sid]:.2f}** × {weights[sid]:g}"
                f" → **+{pts[sid]:.1f}**")  # fmt: skip
        with st.expander(head, expanded=sig is card["signals"][0]):
            st.markdown(sig["rationale_en"] or "")
            if sig["regrade_basis_en"]:
                st.caption(f"Regraded from the agent's {sig['agent_value']:g}: "
                           f"{sig['regrade_basis_en']}")  # fmt: skip
            if sig["flags"]:
                st.warning(f"Flags: {', '.join(sig['flags'])}")
            if sig["evidence"]:
                show_quotes(sig["evidence"])
            else:
                st.caption("No evidence found.")
    with st.expander("The agent's facts and notes"):
        st.html(facts_html(card["facts"]))
        if card["notes_en"]:
            st.caption("Notes")
            st.markdown(card["notes_en"])


def step_html(step: demo.Step, n: int, shown: int) -> str:
    state = "now" if n == shown else "done" if n < shown else "later"
    if step.kind == "record":
        kind, arg = "Record", f"Recorded {len(step.record['signals'])} signals"
        result = "The signals it ended with"
    else:
        kind, arg = step.kind.title(), step.text
        result = step.found or "Done"
    body = (f"<div class='head'><span class='kind'>{kind}</span><code>{escape(arg)}</code>"
            "</div>")  # fmt: skip
    body += f"<span class='result'>{escape(result if n <= shown else 'Pending')}</span>"
    if step.kind == "record" and n <= shown:
        found = []
        for sid, sig in step.record["signals"].items():
            ev = (sig.get("evidence") or [{}])[0]
            quote = (
                f"« {escape(ev['quote'])} » <em>→ {escape(ev['quote_en'])}</em>"
                if ev.get("quote")
                else f"<em>{escape(sig.get('rationale_en') or '')}</em>"
            )
            found.append(
                f"<div><strong>{escape(LABELS.get(sid, sid))}</strong>"
                f"<strong>{sig['value']:.2f}</strong><span>{quote}</span></div>"
            )
        body += "<div class='found'>" + "".join(found) + "</div>"
    return (
        f"<div class='step {state}'><div class='rail'><span class='dot'>{n}</span>"
        f"<span class='line'></span></div><div class='body'>{body}</div></div>"
    )


@st.fragment
def replay_panel(gid: str) -> None:
    """Its buttons re-run only this panel, not the page with the table."""
    rp = replay(RECORDINGS, DATA_DIR, gid)
    if rp is None:
        st.info("The research run for this lead was not recorded, so there is nothing "
                "to replay. Its signals and evidence are under Signals.")  # fmt: skip
        return
    key, total = f"step_{gid}", len(rp.steps)
    st.session_state.setdefault(key, 0)

    def go(k: int) -> None:
        st.session_state[key] = max(0, min(total, k))

    shown = st.session_state[key]
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Next step →", type="primary", disabled=shown >= total,
                  on_click=go, args=(shown + 1,))  # fmt: skip
        play = st.button("▶ Play", disabled=shown >= total)
        st.button("Show all", disabled=shown >= total, on_click=go, args=(total,))
        st.button("Restart", disabled=shown == 0, on_click=go, args=(0,))
        st.space("stretch")
        counter = st.empty()
    progress = st.progress(shown / total if total else 0)
    timeline = st.empty()

    def draw(k: int) -> None:
        counter.markdown(f"Step **{k}** of {total}")
        progress.progress(k / total if total else 0)
        timeline.html("".join(step_html(s, i + 1, k) for i, s in enumerate(rp.steps)))

    draw(shown)
    if play:
        for k in range(shown + 1, total + 1):
            time.sleep(1.6)
            draw(k)
        st.session_state[key] = total
        st.rerun(scope="fragment")  # so the buttons show the last step's state
    cost = "at list price, run on the subscription" if rp.notional else "API spend"
    with st.container(border=True, key="card_run"):
        st.markdown(f"Full run &nbsp; **{rp.searches}** search{'es' if rp.searches != 1 else ''}"
                    f" &nbsp; **{rp.fetches}** page{'s' if rp.fetches != 1 else ''} "
                    f"read &nbsp; **{rp.tokens / 1000:.1f}k** tokens &nbsp; **${rp.usd:.2f}** "
                    f":gray[({cost})]")  # fmt: skip


# Insights


def insights_page() -> None:
    page_head("Findings", "Insights", "Each chart answers one question. Researched leads only where "
              f"the chart says so. {stamp()}")  # fmt: skip
    specs = [data.insights.get(f.__name__) for f in insights.FINDINGS]
    specs = [s for s in specs if s]
    if not specs:
        st.info("No charts yet: run `icp-scout insights` first.")
        return
    for start in range(0, len(specs), 2):
        for i, (cell, spec) in enumerate(zip(st.columns(2, gap="medium"), specs[start : start + 2])):
            spec, title, subtitle = demo.app_spec(spec)
            spec["height"] = 400  # one height, so the cards in a row match
            with cell.container(border=True, height="stretch", key=f"card_{start}_{i}"):
                st.markdown(f"#### {title}")
                st.caption(subtitle)
                st.vega_lite_chart(spec=spec, theme=None, width="stretch")


st.logo(demo.logo_svg(icp.vendor.name), size="large")
page = st.navigation(
    [
        st.Page(market_page, title="Market", default=True),
        st.Page(queue_page, title="Queue", url_path="queue"),
        st.Page(insights_page, title="Insights", url_path="insights"),
    ],
    position="top",
)
page.run()
