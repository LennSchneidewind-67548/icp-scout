"""WP5: the demo's logic in demo.py and a smoke test of the Streamlit app, on synthetic data."""

import json

import pandas as pd
import pytest
from conftest import ROOT

from icp_scout import demo, insights

APP = str(ROOT / "app" / "streamlit_app.py")
API_RECORDING = "30bd58ab584f8212a771c1f81928c12faf016448befbc7ebe17a38762757602a"


@pytest.fixture
def data(demo_dir):
    return demo.load(demo_dir)


def recordings(demo_dir):
    return demo_dir.parent / "recordings"


def test_load_names_the_missing_command(tmp_path):
    with pytest.raises(demo.MissingData, match="icp-scout source"):
        demo.load(tmp_path)


def test_config_weights_reproduce_scored_parquet(icp, data):
    table = demo.rerank(icp, data, demo.config_weights(icp))
    cols = ["group_id", "score", "tier", "rank"]
    pd.testing.assert_frame_equal(table[cols], data.scored[cols])
    assert (table["rank_change"] == 0).all()


def test_new_weights_change_the_order(icp, data):
    assert list(data.scored["group_id"]) == ["g2", "g1", "g3"]
    w = demo.config_weights(icp) | {"product_mix": 0, "growth": 5}
    table = demo.rerank(icp, data, w)
    assert list(table["group_id"]) == ["g2", "g3", "g1"]
    assert dict(zip(table["group_id"], table["rank_change"], strict=True)) == {
        "g2": 0, "g3": 1, "g1": -1}  # fmt: skip


def test_weights_of_zero_allowed_all_zero_rejected(icp):
    new = demo.with_weights(icp, {"growth": 0})
    assert {s.id: s.weight for s in new.signals}["growth"] == 0
    assert {s.id: s.weight for s in icp.signals}["growth"] == 2  # the original is untouched
    with pytest.raises(ValueError, match="at least one"):
        demo.with_weights(icp, dict.fromkeys(demo.config_weights(icp), 0))
    with pytest.raises(ValueError, match="unknown"):
        demo.with_weights(icp, {"nope": 1})


def test_queue_moves(icp, data):
    base = demo.rerank(icp, data, demo.config_weights(icp))
    new = demo.rerank(icp, data, {"size_fit": 3, "product_mix": 3, "growth": 0,
                                  "tech_maturity": 0})  # fmt: skip
    assert demo.queue_moves(base, new, 1) == (["ALPHA SOLAIRE"], ["BETA THERMIQUE"])
    assert demo.queue_moves(base, new, 3) == ([], [])


def test_queue_changes_and_the_moved_view(icp, data):
    base = demo.rerank(icp, data, demo.config_weights(icp))
    new = demo.rerank(icp, data, {"size_fit": 3, "product_mix": 3, "growth": 0,
                                  "tech_maturity": 0})  # fmt: skip
    entered, left = demo.queue_changes(base, new, 1)
    assert entered == [("Alpha Solaire", 2, 1)] and left == [("Beta Thermique", 1, 2)]
    moved = demo.moved_view(new, base, 1)
    assert dict(zip(moved["name"], moved["move"], strict=True)) == {
        "ALPHA SOLAIRE": "entered", "BETA THERMIQUE": "left"}  # fmt: skip
    assert demo.moved_view(base, base, 1).empty


def test_moved_label_why_and_contributions():
    assert [demo.moved_label(c) for c in [3, -2, 0, None]] == ["▲3", "▼2", "–", "–"]
    assert demo.moved_label(5, "entered") == "NEW"
    assert demo.why("9.7 A | PV + heat pumps | ~120 staff") == "PV + heat pumps | ~120 staff"
    assert demo.why("no score prefix") == "no score prefix"
    pts = demo.contributions({"a": 3, "b": 1}, {"a": 1.0, "b": 0.5})
    assert pts == {"a": 6.75, "b": 1.125}  # 1 + 7.875 is the score


def test_app_spec_moves_the_title_out():
    spec = {"title": {"text": "Bigger groups hire more", "subtitle": "Researched leads"},
            "config": {"axis": {"labelFontSize": 12}}, "mark": "bar"}  # fmt: skip
    out, title, subtitle = demo.app_spec(spec)
    assert (title, subtitle) == ("Bigger groups hire more", "Researched leads")
    assert "title" not in out and out["config"]["axis"]["labelFontSize"] == 13
    assert spec["config"]["axis"]["labelFontSize"] == 12  # the saved spec is untouched


def test_app_spec_swaps_the_neutral_palette():
    spec = {"mark": {"type": "bar", "color": insights.ACCENT},
            "encoding": {"color": {"scale": {"range": [insights.MID_GREY, insights.ACCENT]}}}}  # fmt: skip
    out, _, _ = demo.app_spec(spec)
    assert out["mark"]["color"] == demo.TIER_COLORS["A"]
    assert out["encoding"]["color"]["scale"]["range"] == [demo.SEGMENT_GREY, demo.TIER_COLORS["A"]]
    assert spec["mark"]["color"] == insights.ACCENT  # the saved spec is untouched


def test_run_cost_and_last_run():
    ledger = [
        {"at": "2026-09-30T14:02:00+00:00", "purpose": "research", "backend": "api",
         "usd": 0.5},
        {"at": "2026-10-01T08:00:00+00:00", "purpose": "regrade", "backend": "claude-code",
         "usd": 0.0, "notional_usd": 0.25},
    ]  # fmt: skip
    assert demo.run_cost(ledger) == 0.75
    assert demo.last_run(ledger) == "2026-09-30" and demo.last_run([]) is None


def test_queue_table_regions_and_columns(icp, data):
    q = demo.queue_table(icp, data, demo.rerank(icp, data, demo.config_weights(icp)))
    assert q.set_index("group_id").loc["g2", "region"] == "Auvergne-Rhône-Alpes"
    assert list(q["queue"]) == ["1", "2", "3"]


def test_lead_card_puts_quote_en_next_to_every_quote(data):
    card = demo.lead_card(data, "g1")
    assert card["name"] == "Alpha Solaire" and card["headcount_source"] == "regrade"
    assert card["headcount_basis_en"] == "The site says 100."
    assert card["facts"]["headcount_stated"] == 100
    quotes = [e for s in card["signals"] for e in s["evidence"]]
    assert quotes and all(e["quote"] and e["quote_en"] and e["url"] for e in quotes)
    assert [s["signal"] for s in card["signals"] if not s["evidence"]] == [
        "growth", "tech_maturity"]  # fmt: skip
    with pytest.raises(KeyError):
        demo.lead_card(data, "g4")  # not researched


def test_replay_steps_in_order_ending_with_the_record(demo_dir, data):
    replay = demo.replay_steps(recordings(demo_dir), data.ledger, "g1")
    assert [(s.kind, s.text) for s in replay.steps] == [
        ("fetch", "https://g1.example/"),
        ("search", "ALPHA SOLAIRE recrutement"),
        ("record", ""),
    ]
    assert replay.steps[-1].record["signals"]["size_fit"]["evidence"][0]["quote_en"]
    assert (replay.searches, replay.fetches, replay.tokens) == (1, 1, 1160)
    assert replay.usd == 0.12 and replay.notional


def test_replay_none_without_a_recording(demo_dir, data):
    assert demo.replay_steps(recordings(demo_dir), data.ledger, "g2") is None
    line = {"lead": "g2", "purpose": "research", "key": "0" * 64}
    assert demo.replay_steps(recordings(demo_dir), [line], "g2") is None


def test_replay_reads_api_recordings():
    """The committed synthetic recordings are Messages API answers."""
    line = {"lead": "g900000060", "purpose": "research", "key": API_RECORDING,
            "backend": "api", "model": "claude-opus-5-5", "input_tokens": 1, "usd": 0.05}  # fmt: skip
    replay = demo.replay_steps(ROOT / "fixtures" / "llm", [line], "g900000060")
    kinds = [s.kind for s in replay.steps]
    assert kinds[-1] == "record" and "search" in kinds
    assert replay.usd == 0.05 and not replay.notional


def test_map_frame_layers_and_far_off_points(icp, data):
    t = demo.map_frame(data, icp).set_index("group_id")
    assert t.loc["g2", "layer"] == "Tier " + data.scored.set_index("group_id").loc["g2", "tier"]
    assert t.loc["g4", "layer"] == demo.IN_SEGMENT and t.loc["g5", "layer"] == demo.MARKET
    assert not t.loc["g6", "on_map"] and t.drop("g6")["on_map"].all()
    spec = json.loads(demo.map_chart(t.reset_index()).to_json())
    assert spec["projection"]["type"] == "equirectangular"
    assert "1 far-off groups" in spec["title"]["subtitle"]


# The app


@pytest.fixture
def app(demo_dir, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ICP_SCOUT_DATA", str(demo_dir))
    monkeypatch.setenv("ICP_SCOUT_RECORDINGS", str(recordings(demo_dir)))
    monkeypatch.setenv("ICP_SCOUT_CONFIG", str(ROOT / "config" / "icp.example.yaml"))
    return AppTest.from_file(APP, default_timeout=30).run()


def page(app, url_path):
    """AppTest switches only to file pages; a function page's hash is its url_path's."""
    from streamlit.util import calc_hash

    app._page_hash = calc_hash(url_path)
    return app.run()


def test_app_renders_every_page(app):
    assert not app.exception  # Market, the default page
    assert any("market" in h.value for h in app.header)
    for p in ["queue", "insights"]:
        assert not page(app, p).exception, p
    assert any("Insights" in h.value for h in app.header)


def test_app_queue_and_a_lead(app):
    page(app, "queue")
    assert app.dataframe[0].value.iloc[0]["name"] == "Beta Thermique"
    app.session_state["lead"] = "g1"
    app.run()
    assert not app.exception
    assert any("Alpha Solaire" in m.value for m in app.markdown)  # the lead pane
    assert len(app.expander) == 6  # the weights, one per signal, facts and notes
    app.session_state["lead_tab"] = "replay"
    app.run()
    assert not app.exception
    assert "Next step →" in [b.label for b in app.button]


def test_app_lead_deep_link_opens_once(app):
    app.query_params["lead"] = "g1"
    page(app, "queue")
    assert not app.exception
    assert any("Alpha Solaire" in m.value for m in app.markdown)  # the lead pane
    assert "lead" not in app.query_params  # consumed, so the close button still closes it


def test_app_lead_deep_link_ignores_an_unknown_id(app):
    app.query_params["lead"] = "nope"
    page(app, "queue")
    assert not app.exception
    assert app.session_state["lead"] is None


def test_app_slider_changes_the_first_row(app):
    page(app, "queue")
    app.slider(key="w_growth").set_value(0).run()
    app.slider(key="w_tech_maturity").set_value(0).run()
    assert not app.exception
    assert app.session_state["view"] == "moved"  # a slider move shows what moved
    app.session_state["view"] = "all"
    app.run()
    assert app.dataframe[0].value.iloc[0]["name"] == "Alpha Solaire"
    # 3 leads, a queue of 50: none entered. The summary shows in the Moved view.
    app.session_state["view"] = "moved"
    app.run()
    assert any("0 entered the top 50" in h.proto.body for h in app.get("html"))


def test_display_name():
    assert demo.display_name("ACME ENERGIE (ACME ENERGIE)") == "Acme Energie"
    assert demo.display_name("SOCIETE DE TRAVAUX D'ISOLATION (STI)") == (
        "Societe de Travaux d'Isolation (STI)")  # fmt: skip
    assert demo.display_name("SARL RWT CLIM 3D") == "SARL RWT Clim 3D"
    assert demo.display_name("Already Mixed (Case)") == "Already Mixed (Case)"
    assert demo.display_name(None) == ""
