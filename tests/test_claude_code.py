"""The claude-code backend against a fake CLI: no process is started."""

import json
import subprocess
import sys

import pytest
from test_research import good_answer, lead

from icp_scout import claude_code, research
from icp_scout.claude_code import ClaudeCode, CliError
from icp_scout.enrich import agent
from icp_scout.llm import RecordingMiss, read_ledger

SITE = "https://brise-marine.example/"


def stream(
    answer, *, key_source="none", status="allowed", five_hour=0.1, seven_day=0.2, fetch=SITE
):
    """The stream-json messages of one CLI run: init, a fetch, the answer, the result."""
    return [
        {"type": "system", "subtype": "init", "apiKeySource": key_source},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {"query": "q"}},
            {"type": "tool_use", "id": "t2", "name": "WebFetch", "input": {"url": fetch}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": f"Links: [{{\"url\":\"{fetch}\"}}]"},
            {"type": "tool_result", "tool_use_id": "t2", "content": "« Devis gratuit »"},
        ]}},
        {"type": "rate_limit_event", "rate_limit_info": {
            "status": status, "rateLimitType": "five_hour",
            "unifiedWindows": {"five_hour": {"utilization": five_hour},
                               "seven_day": {"utilization": seven_day}}}},
        {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3,
         "total_cost_usd": 0.31, "usage": {"input_tokens": 10, "output_tokens": 500},
         "structured_output": answer},
    ]  # fmt: skip


class FakeCli:
    def __init__(self, *runs):
        self.runs, self.calls = list(runs), []

    def __call__(self, cmd, prompt, cwd, timeout):
        self.calls.append({"cmd": cmd, "prompt": prompt,
                           "system": (cwd / "system.md").read_text(encoding="utf-8")})  # fmt: skip
        yield from self.runs.pop(0)


def cc_icp(icp, **research):
    update = {"backend": "claude-code", "concurrency": 1, **research}
    return icp.model_copy(update={"research": icp.research.model_copy(update=update)})


def ids(icp):
    return [s.id for s in icp.signals]


def test_records_once_then_replays_with_no_api_cost(icp, data_dir, tmp_path):
    cli = FakeCli(stream(good_answer(ids(icp), url=SITE)))
    cc = ClaudeCode(tmp_path / "rec", "record", data_dir / "ledger.jsonl", runner=cli)
    out = agent.research_claude_code(icp, cc, lead(data_dir))
    assert out["status"] == "ok" and out["flags"] == [] and out["calls"] == 3
    call = cli.calls[0]
    assert "BRISE MARINE" in call["prompt"] and "WebFetch" in call["system"]
    assert call["cmd"][call["cmd"].index("--model") + 1] == icp.research.model
    assert json.loads(call["cmd"][call["cmd"].index("--json-schema") + 1])["required"]

    again = ClaudeCode(tmp_path / "rec", "replay", data_dir / "ledger.jsonl")
    assert agent.research_claude_code(icp, again, lead(data_dir)) == out
    ledger = read_ledger(data_dir / "ledger.jsonl")
    assert [(r["usd"], r["notional_usd"], r["replayed"]) for r in ledger] == [
        (0.0, 0.31, False), (0.0, 0.31, True)]  # fmt: skip
    assert ledger[0]["web_searches"] == 1 and ledger[0]["web_fetches"] == 1
    assert ledger[0]["windows"] == {"five_hour": 0.1, "seven_day": 0.2}
    with pytest.raises(RecordingMiss):
        agent.research_claude_code(icp, again, lead(data_dir, "g900000060"))


def test_evidence_citing_a_page_never_retrieved_is_flagged(icp, data_dir, tmp_path):
    answer = good_answer(ids(icp), url="https://elsewhere.example/")
    cc = ClaudeCode(tmp_path, "record", runner=FakeCli(stream(answer)))
    out = agent.research_claude_code(icp, cc, lead(data_dir))
    assert {f["code"] for f in out["flags"]} == {"unverified_url"}


def test_an_invalid_answer_fails_the_lead(icp, data_dir, tmp_path):
    answer = good_answer(ids(icp)[1:])
    cc = ClaudeCode(tmp_path, "record", runner=FakeCli(stream(answer)))
    out = agent.research_claude_code(icp, cc, lead(data_dir))
    assert out["status"] == "failed" and "invalid structured output" in out["reason"]


def test_a_run_that_would_bill_an_api_key_is_stopped_and_not_recorded(icp, data_dir, tmp_path):
    run = stream(good_answer(ids(icp)), key_source="ANTHROPIC_API_KEY")
    cc = ClaudeCode(tmp_path, "record", runner=FakeCli(run))
    with pytest.raises(CliError, match="API key"):
        agent.research_claude_code(icp, cc, lead(data_dir))
    assert not list(tmp_path.rglob("*.json"))


def test_the_api_key_never_reaches_the_cli(monkeypatch, tmp_path):
    seen, real = {}, subprocess.Popen

    def popen(cmd, env, **kw):
        seen.update(env)
        return real([sys.executable, "-c", "print('{}')"], **kw)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(claude_code.subprocess, "Popen", popen)
    assert list(claude_code.run_cli(["claude"], "hi", tmp_path, 10)) == [{}]
    assert "ANTHROPIC_API_KEY" not in seen and seen


def test_a_full_usage_window_stops_the_run_and_the_next_run_resumes(icp, data_dir, tmp_path):
    answer = good_answer(ids(icp))
    rec = tmp_path / "rec"
    # Lead 1 passes the 90% mark; lead 2 is not started.
    cli = FakeCli(stream(answer, five_hour=0.95))
    results = research.run(cc_icp(icp), data_dir, limit=3, recordings_dir=rec, runner=cli,
                           log=lambda _: None)  # fmt: skip
    assert len(results) == 1 and len(cli.calls) == 1
    # A limit hit mid-lead: that lead is not recorded.
    cli = FakeCli(stream(answer, status="rejected"))
    results = research.run(cc_icp(icp), data_dir, limit=3, recordings_dir=rec, runner=cli,
                           log=lambda _: None)  # fmt: skip
    assert len(results) == 1 and len(list(rec.rglob("*.json"))) == 1
    # Later: lead 1 replays, leads 2 and 3 run.
    cli = FakeCli(stream(answer), stream(answer))
    results = research.run(cc_icp(icp), data_dir, limit=3, recordings_dir=rec, runner=cli,
                           log=lambda _: None)  # fmt: skip
    assert [r["status"] for r in results] == ["ok"] * 3 and len(cli.calls) == 2


def test_cost_report_shows_the_list_price_of_subscription_runs(icp, data_dir, tmp_path):
    cli = FakeCli(stream(good_answer(ids(icp))), stream(good_answer(ids(icp))))
    research.run(cc_icp(icp), data_dir, limit=2, recordings_dir=tmp_path / "rec", runner=cli,
                 log=lambda _: None)  # fmt: skip
    report = research.cost_report(data_dir)
    assert "Total cost         $0.00" in report
    assert "2 leads via claude-code: $0 of API money; at list price $0.62" in report


def test_the_weekly_window_has_its_own_lower_cap(icp, data_dir, tmp_path):
    cli = FakeCli(stream(good_answer(ids(icp)), seven_day=0.75))
    results = research.run(cc_icp(icp), data_dir, limit=3, recordings_dir=tmp_path / "rec",
                           runner=cli, log=lambda _: None)  # fmt: skip
    assert len(results) == 1  # 75% is under the 5-hour cap but over the 7-day one
