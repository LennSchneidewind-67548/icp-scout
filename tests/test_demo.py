"""WP5: the demo's logic in demo.py and a smoke test of the Streamlit app, on synthetic data."""

import json

import pandas as pd
import pytest
from conftest import ROOT

from icp_scout import demo

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


def test_queue_table_regions_and_columns(icp, data):
    q = demo.queue_table(icp, data, demo.rerank(icp, data, demo.config_weights(icp)))
    assert q.set_index("group_id").loc["g2", "region"] == "Auvergne-Rhône-Alpes"
    assert list(q["queue"]) == ["1", "2", "3"]


def test_lead_card_puts_quote_en_next_to_every_quote(data):
    card = demo.lead_card(data, "g1")
    assert card["name"] == "ALPHA SOLAIRE" and card["headcount_source"] == "regrade"
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


def test_app_renders_every_tab(app):
    assert not app.exception
    assert [t.label for t in app.tabs] == ["Market", "Queue", "Lead", "Insights"]
    assert app.dataframe[0].value.iloc[0]["name"] == "BETA THERMIQUE"
    assert any("Research replay" in s.value for s in app.subheader)


def test_app_slider_changes_the_first_row(app):
    app.slider(key="w_growth").set_value(0).run()
    app.slider(key="w_tech_maturity").set_value(0).run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["name"] == "ALPHA SOLAIRE"
    assert "1 leads entered" not in app.info[0].value  # 3 leads, a queue of 50: none moved
