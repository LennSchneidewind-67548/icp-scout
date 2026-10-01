"""WP5. The demo: market map, ranked lead table, per-lead evidence, live weight sliders.

`streamlit run app/streamlit_app.py`. Reads data/ (or $ICP_SCOUT_DATA) and the
recorded transcripts ($ICP_SCOUT_RECORDINGS); makes no model call and no network
request. Everything it computes is in icp_scout.demo; this file lays out widgets.
"""

import time

import pandas as pd
import streamlit as st

from icp_scout import config, demo, insights

st.set_page_config(page_title="ICP Scout", layout="wide")
demo.load_env()
icp = config.load()
DATA_DIR = str(demo.data_dir())
RECORDINGS = str(demo.recordings_dir())


@st.cache_data(show_spinner="Loading the pipeline's files ...")
def load(data_dir: str) -> demo.DemoData:
    return demo.load(data_dir)


@st.cache_data
def rerank(_icp, config_id: str, data_dir: str, weights: tuple) -> pd.DataFrame:
    return demo.rerank(_icp, load(data_dir), dict(weights))


@st.cache_data
def map_spec(_icp, config_id: str, data_dir: str) -> dict:
    return demo.map_chart(demo.map_frame(load(data_dir), _icp)).to_dict()


try:
    data = load(DATA_DIR)
except demo.MissingData as e:
    st.error(str(e))
    st.stop()

CONFIG_ID = icp.model_dump_json()
BASE = demo.config_weights(icp)
LABELS = {s.id: s.label for s in icp.signals}

# Sidebar: the weight sliders


def reset_weights() -> None:
    for sid, w in BASE.items():
        st.session_state[f"w_{sid}"] = round(w)


with st.sidebar:
    st.header("Signal weights")
    st.caption("Re-scores all researched leads with the rubric. No model call.")
    weights = {
        s.id: st.slider(s.label, 0, 5, round(s.weight), step=1, key=f"w_{s.id}")
        for s in icp.signals
    }
    st.button("Reset to config", on_click=reset_weights)
    if not any(weights.values()):
        st.warning("All weights are 0: showing the config weights.")
        weights = BASE

base = rerank(icp, CONFIG_ID, DATA_DIR, tuple(sorted(BASE.items())))
table = rerank(icp, CONFIG_ID, DATA_DIR, tuple(sorted(weights.items())))
size = icp.queue.size
entered, left = demo.queue_moves(base, table, size)

st.title(f"ICP Scout: {icp.vendor.name}")
market_tab, queue_tab, lead_tab, insights_tab = st.tabs(
    ["Market", "Queue", "Lead", "Insights"], key="tab"
)

# Market

with market_tab:
    m = data.market
    cols = st.columns(4)
    cols[0].metric("Groups from open data", f"{len(m):,}")
    seg = icp.segment
    cols[1].metric(f"In segment ({seg.headcount_min}-{seg.headcount_max} staff)",
                   f"{int(m['in_segment'].sum()):,}")  # fmt: skip
    cols[2].metric("Researched by the agent", f"{len(data.scored):,}")
    cols[3].metric("SDR queue", f"{int(data.scored['queue_rank'].notna().sum()):,}")
    st.vega_lite_chart(spec=map_spec(icp, CONFIG_ID, DATA_DIR), theme=None, width="content")

# Queue

with queue_tab:
    if weights != BASE:
        st.info(f"**{len(entered)} leads entered the top {size}, {len(left)} left.** "
                "Same evidence, new weights, no model call.")  # fmt: skip
        if entered or left:
            with st.expander("Which leads"):
                c_in, c_out = st.columns(2)
                c_in.markdown("**Entered**\n" + "".join(f"\n- {n}" for n in entered))
                c_out.markdown("**Left**\n" + "".join(f"\n- {n}" for n in left))
    q = demo.queue_table(icp, data, table)
    f1, f2 = st.columns(2)
    tiers = f1.multiselect("Tier", ["A", "B", "C"], default=["A", "B", "C"])
    regions = f2.multiselect("Region", sorted(q["region"].unique()))
    shown = q[q["tier"].isin(tiers) & (q["region"].isin(regions) if regions else True)]
    st.dataframe(
        shown,
        hide_index=True,
        height=600,
        column_order=[
            "rank",
            "rank_change",
            "name",
            "score",
            "tier",
            "region",
            "queue",
            "reason_en",
        ],
        column_config={
            "rank": st.column_config.NumberColumn("Rank", width="small"),
            "rank_change": st.column_config.NumberColumn(
                "Moved",
                format="%+d",
                width="small",
                help="Places gained (+) or lost (-) against the config weights",
            ),
            "name": st.column_config.TextColumn("Group"),
            "score": st.column_config.ProgressColumn(
                "Score", min_value=1, max_value=10, format="%.1f"
            ),
            "tier": st.column_config.TextColumn("Tier", width="small"),
            "region": st.column_config.TextColumn("Region"),
            "queue": st.column_config.TextColumn(
                "Queue", width="small", help="SDR queue place; references are calibration"
            ),
            "reason_en": st.column_config.TextColumn("Why", width="large"),
        },
    )

# Lead


def show_quotes(evidence: list[dict]) -> None:
    for e in evidence:
        # Registry facts are quoted too, and they are not French: "as quoted", not "French".
        quoted, english = st.columns(2)
        quoted.markdown(f"> {e['quote']}  \n*As quoted*")
        english.markdown(f"> {e['quote_en']}  \n*English* · [{e['url']}]({e['url']})")


def show_step(step: demo.Step, n: int) -> None:
    if step.kind == "search":
        st.markdown(f"**{n}. Search** `{step.text}`")
    elif step.kind == "fetch":
        st.markdown(f"**{n}. Fetch** [{step.text}]({step.text})")
    else:
        st.markdown(f"**{n}. Record:** the signals it ended with")
        for sid, sig in step.record["signals"].items():
            st.markdown(f"`{LABELS.get(sid, sid)}` **{sig['value']:g}**: {sig['rationale_en']}")
            show_quotes(sig["evidence"])


@st.fragment
def replay_panel(gid: str) -> None:
    """Its buttons re-run only this panel, not the page with the map."""
    st.subheader("Research replay")
    replay = demo.replay_steps(RECORDINGS, data.ledger, gid)
    if replay is None:
        st.info(f"No recorded research run for this lead in {RECORDINGS}.")
        return
    key = f"step_{gid}"
    shown = st.session_state.get(key, 0)
    b = st.columns([1, 1, 1, 1, 4])
    if b[0].button("Next step", disabled=shown >= len(replay.steps)):
        shown += 1
    play = b[1].button("Play")
    if b[2].button("Show all"):
        shown = len(replay.steps)
    if b[3].button("Restart"):
        shown = 0
    steps = st.container()
    with steps:
        for i, step in enumerate(replay.steps[:shown]):
            show_step(step, i + 1)
    if play:
        for i in range(shown, len(replay.steps)):
            time.sleep(1.2)
            with steps:
                show_step(replay.steps[i], i + 1)
        shown = len(replay.steps)
    st.session_state[key] = shown
    cost = "at list price, run on the subscription" if replay.notional else "API spend"
    st.caption(f"{replay.searches} searches, {replay.fetches} pages fetched, "
               f"{replay.tokens:,} tokens, ${replay.usd:.2f} ({cost})")  # fmt: skip


with lead_tab:
    order = table.sort_values("rank")
    options = list(order["group_id"])
    names = dict(zip(order["group_id"], order["name"], strict=True))
    ranks = dict(zip(order["group_id"], order["rank"], strict=True))
    gid = st.selectbox("Lead", options, format_func=lambda g: f"#{ranks[g]} {names[g]}")
    card = demo.lead_card(data, gid)
    row = table[table["group_id"] == gid].iloc[0]

    st.subheader(card["name"])
    c = st.columns(4)
    c[0].metric("Score", f"{row['score']:.1f}")
    c[1].metric("Tier", row["tier"])
    c[2].metric("Rank", int(row["rank"]))
    qr = row["queue_rank"]
    c[3].metric("Queue", "calibration" if row["is_reference"] else
                "-" if pd.isna(qr) else int(qr))  # fmt: skip
    st.markdown(f"**Why:** {row['reason_en']}")
    if card["headcount"] is not None:
        basis = f": {card['headcount_basis_en']}" if card["headcount_basis_en"] else ""
        st.caption(f"Headcount ~{card['headcount']:.0f} ({card['headcount_source']}){basis}")
    if card["website"]:
        st.caption(f"Website: {card['website']} · Companies: {', '.join(card['members'])}")

    for sig in card["signals"]:
        weight = weights.get(sig["signal"], 0)
        head = (f"{LABELS.get(sig['signal'], sig['signal'])}: **{row[sig['signal']]:.2f}** "
                f"(weight {weight:g})")  # fmt: skip
        with st.expander(head, expanded=sig is card["signals"][0]):
            st.markdown(sig["rationale_en"] or "")
            if sig["regrade_basis_en"]:
                st.caption(f"Regraded from the agent's {sig['agent_value']:g}: "
                           f"{sig['regrade_basis_en']}")  # fmt: skip
            if sig["flags"]:
                st.warning(f"Flags: {', '.join(sig['flags'])}")
            show_quotes(sig["evidence"])
            if not sig["evidence"]:
                st.caption("No evidence found.")
    with st.expander("The agent's facts and notes"):
        st.json(card["facts"], expanded=True)
        st.markdown(card["notes_en"] or "")

    st.divider()
    replay_panel(gid)

# Insights

with insights_tab:
    if not data.insights:
        st.info("No charts yet: run `icp-scout insights` first.")
    for f in insights.FINDINGS:
        spec = data.insights.get(f.__name__)
        if spec:
            st.vega_lite_chart(spec=spec, theme=None, width="content")
