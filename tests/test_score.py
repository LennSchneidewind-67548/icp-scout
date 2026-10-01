"""WP3: the rubric in score.py and the regrade pass, on synthetic data."""

import json

import pandas as pd
import pytest
from conftest import ScriptedClient
from pydantic import ValidationError

from icp_scout import cli, config, score
from icp_scout.claude_code import ClaudeCode
from icp_scout.enrich import regrade
from icp_scout.llm import LLM

IDS = ["size_fit", "product_mix", "growth", "tech_maturity"]


def signals(values: dict[str, list[float]], found=True) -> pd.DataFrame:
    """values: group_id -> the four signal values, in IDS order."""
    rows = []
    for gid, vs in values.items():
        for sid, v in zip(IDS, vs, strict=True):
            ev = [{"quote": "q", "quote_en": "q", "url": "https://x.example/"}] if found else []
            rows.append({"group_id": gid, "name": f"Name {gid}", "status": "ok", "signal": sid,
                         "value": v, "found": found, "rationale_en": "r", "evidence": ev})  # fmt: skip
    return pd.DataFrame(rows)


def market(headcounts: dict[str, float], pre: dict[str, float] | None = None) -> pd.DataFrame:
    return pd.DataFrame([
        {"group_id": g, "members": [g[1:]], "headcount_mid": h,
         "pre_score": (pre or {}).get(g, 0.5)}
        for g, h in headcounts.items()
    ])  # fmt: skip


# The sweet-spot curve (example config: band 30-300, sweet spot 60-200, edge 0.6)


@pytest.mark.parametrize(
    "headcount, expected",
    [(60, 1), (120, 1), (200, 1), (30, 0.6), (300, 0.6), (45, 0.8), (250, 0.8), (20, 0.6),
     (900, 0.6), (None, None)],
)  # fmt: skip
def test_size_curve(icp, headcount, expected):
    assert score.size_curve(headcount, icp.segment) == pytest.approx(expected)


def test_sweet_spot_must_lie_inside_the_band(icp):
    seg = icp.segment.model_dump() | {"sweet_spot": (20, 200)}
    with pytest.raises(ValidationError, match="inside"):
        config.Segment.model_validate(seg)


# Score, tiers, ranking


def test_score_formula_and_tiers(icp):
    # Example weights 3/3/2/2, total 10.
    t = score.score(icp, signals({"g1": [1, 1, 1, 1], "g2": [1, 0.5, 0, 0.5]}),
                    market({"g1": 100, "g2": 100}))  # fmt: skip
    s = t.set_index("group_id")
    assert s.loc["g1", "score"] == 10.0 and s.loc["g1", "tier"] == "A"
    assert s.loc["g2", "score"] == pytest.approx(1 + 9 * (3 + 1.5 + 0 + 1) / 10)  # 5.95
    assert s.loc["g2", "tier"] == "C"


def test_size_follows_the_curve_only_where_the_agent_put_the_group_in_the_band(icp):
    t = score.score(icp, signals({"g1": [1, 1, 1, 1], "g2": [0.5, 1, 1, 1]}),
                    market({"g1": 34.5, "g2": 34.5}))  # fmt: skip
    s = t.set_index("group_id")
    assert s.loc["g1", "size_fit"] == pytest.approx(0.6 + 0.4 * 4.5 / 30)
    assert s.loc["g2", "size_fit"] == 0.5  # the agent's value stands


def test_regrade_overrides_graded_signals_and_headcount(icp):
    rg = {"g1": {"headcount": 120, "grades": {"growth": {"value": 0.25, "basis_en": "b"}},
                 "phrases": {}}}  # fmt: skip
    t = score.score(icp, signals({"g1": [1, 1, 1, 1]}), market({"g1": 34.5}), rg)
    r = t.iloc[0]
    assert r["growth"] == 0.25 and r["size_fit"] == 1 and r["headcount_source"] == "regrade"


def test_a_weight_change_reranks_with_no_model_call(icp):
    sig = signals({"mix": [1, 1, 0, 0.5], "grow": [1, 0, 1, 1]})
    m = market({"mix": 100, "grow": 100})
    assert list(score.score(icp, sig, m)["group_id"]) == ["grow", "mix"]
    heavy = [s.model_copy(update={"weight": 10 if s.id == "product_mix" else s.weight})
             for s in icp.signals]  # fmt: skip
    icp2 = icp.model_copy(update={"signals": heavy})
    assert list(score.score(icp2, sig, m)["group_id"]) == ["mix", "grow"]


def test_ties_go_to_evidence_then_name_never_the_pre_rank(icp):
    sig = pd.concat([signals({"gb": [1, 1, 1, 1], "ga": [1, 1, 1, 1]}),
                     signals({"gc": [1, 1, 1, 1]}, found=False)])  # fmt: skip
    m = market({"ga": 100, "gb": 100, "gc": 100}, pre={"gc": 1.0, "gb": 0.9, "ga": 0.1})
    assert list(score.score(icp, sig, m)["group_id"]) == ["ga", "gb", "gc"]


def test_references_are_ranked_but_never_queued(icp):
    icp = icp.model_copy(update={"reference_sirens": ["2"], "queue": config.Queue(size=1)})
    t = score.score(icp, signals({"g2": [1, 1, 1, 1], "g1": [1, 1, 0.5, 1], "g3": [0, 0, 0, 0]}),
                    market({"g1": 100, "g2": 100, "g3": 100}))  # fmt: skip
    s = t.set_index("group_id")
    assert s.loc["g2", "rank"] == 1 and pd.isna(s.loc["g2", "queue_rank"])
    assert s.loc["g1", "queue_rank"] == 1 and pd.isna(s.loc["g3", "queue_rank"])
    assert "reference (calibration, not queued)" in s.loc["g2", "reason_en"]


def test_tie_break_places_counts_queue_places_sharing_the_cut_score(icp):
    t = pd.DataFrame({"score": [10, 9, 9, 9, 8], "is_reference": [False] * 5})
    assert score.tie_break_places(t, 2) == 1  # place 2 of {2,3,4} at 9
    assert score.tie_break_places(t, 4) == 0
    assert score.tie_break_places(t, 9) == 0


def test_reason_line(icp):
    rg = {"g1": {"headcount": 120, "grades": {"growth": {"value": 0.5, "basis_en": "b"}},
                 "phrases": {"size_fit": "4 branches", "product_mix": "PV + heat pumps",
                             "growth": "1 roofer opening", "tech_maturity": "quote form"}}}  # fmt: skip
    r = score.score(icp, signals({"g1": [1, 1, 1, 1]}), market({"g1": 100}), rg).iloc[0]
    assert r["reason_en"] == (
        "9.1 A | ~120 staff, 4 branches | PV + heat pumps | quote form | weakest: 1 roofer opening"
    )


def test_score_command(icp, tmp_path, capsys):
    signals({"g1": [1, 1, 1, 1]}).to_parquet(tmp_path / "signals.parquet")
    market({"g1": 100}).to_parquet(tmp_path / "market.parquet")
    cli.main(["--data-dir", str(tmp_path), "score"])
    out = capsys.readouterr().out
    assert "Scored 1 groups" in out and "0 places decided by a tie-break" in out
    assert len(pd.read_parquet(tmp_path / "scored.parquet")) == 1


# The regrade pass


ANSWER = {"headcount": 80, "headcount_basis_en": "stated",
          "grades": {"growth": {"value": 0.75, "basis_en": "one sales role"}},
          "phrases": {s: "p" for s in IDS}}  # fmt: skip
LEAD = {"group_id": "g1", "name": "Name g1", "headcount_low": 50, "headcount_mid": 74.5,
        "headcount_high": 99, "headcount_unknown": 0}  # fmt: skip


def rows():
    return signals({"g1": [1, 1, 1, 1]}).to_dict("records")


def test_regrade_schema_grades_only_signals_with_grades(icp):
    s = regrade.schema(icp)
    assert list(s["properties"]["grades"]["properties"]) == ["growth"]
    assert s["properties"]["grades"]["properties"]["growth"]["properties"]["value"]["enum"] == [
        0, 0.25, 0.5, 0.75, 1,
    ]  # fmt: skip


def test_regrade_over_the_api_records_and_replays(icp, tmp_path):
    msg = {"id": "m", "type": "message", "role": "assistant", "model": icp.research.model,
           "content": [{"type": "tool_use", "id": "t", "name": regrade.TOOL, "input": ANSWER}],
           "stop_reason": "tool_use", "usage": {"input_tokens": 100, "output_tokens": 50}}  # fmt: skip
    client = ScriptedClient(lambda p: msg)
    out = regrade.regrade(icp, LLM(tmp_path, "record", client=client), LEAD, rows(), None)
    assert out["status"] == "ok" and out["result"]["grades"]["growth"]["value"] == 0.75
    assert client.requests[0]["tool_choice"] == {"type": "tool", "name": regrade.TOOL}
    again = regrade.regrade(icp, LLM(tmp_path, "replay"), LEAD, rows(), None)
    assert again == out


def test_regrade_on_the_cli_backend_uses_no_tools(icp, tmp_path):
    seen = {}

    def runner(cmd, prompt, cwd, timeout):
        seen["cmd"] = cmd
        yield {"type": "system", "subtype": "init", "apiKeySource": "none"}
        yield {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
               "total_cost_usd": 0.03, "usage": {}, "structured_output": ANSWER}  # fmt: skip

    out = regrade.regrade(icp, ClaudeCode(tmp_path, "record", runner=runner), LEAD, rows(), None)
    assert out["status"] == "ok"
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""


def test_an_invalid_regrade_fails_the_lead(icp, tmp_path):
    bad = ANSWER | {"grades": {"growth": {"value": 2, "basis_en": "b"}}}
    msg = {"content": [{"type": "tool_use", "id": "t", "name": regrade.TOOL, "input": bad}],
           "usage": {}, "model": icp.research.model}  # fmt: skip
    out = regrade.regrade(icp, LLM(tmp_path, "record", client=ScriptedClient(lambda p: msg)),
                          LEAD, rows(), None)  # fmt: skip
    assert out["status"] == "failed" and "invalid" in out["reason"]


def test_regraded_results_feed_the_score(icp, tmp_path):
    (tmp_path / "regrade").mkdir()
    rec = {"group_id": "g1", "status": "ok", "result": ANSWER}
    (tmp_path / "regrade" / "g1.json").write_text(json.dumps(rec), encoding="utf-8")
    t = score.score(icp, signals({"g1": [1, 1, 1, 1]}), market({"g1": 34.5}),
                    score.load_regrades(tmp_path))  # fmt: skip
    assert t.iloc[0]["growth"] == 0.75 and t.iloc[0]["headcount"] == 80
