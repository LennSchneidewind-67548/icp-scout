import json
import sys

import pandas as pd
import pytest
from conftest import ROOT, ScriptedClient
from pydantic import ValidationError

from icp_scout import cli, config, llm, research
from icp_scout.enrich import agent
from icp_scout.llm import LLM, RecordingMiss

RECORDINGS = ROOT / "fixtures" / "llm"
GROUPS = ["g900000010", "g900000060", "g900000110"]
sys.path.insert(0, str(RECORDINGS))
import make_fixtures


@pytest.fixture(scope="module")
def market_dir(tmp_path_factory):
    """data/ after `icp-scout source` on the source fixtures."""
    data_dir = tmp_path_factory.mktemp("data")
    make_fixtures.market(data_dir)
    return data_dir


@pytest.fixture
def data_dir(market_dir, tmp_path):
    (tmp_path / "market.parquet").write_bytes((market_dir / "market.parquet").read_bytes())
    return tmp_path


def lead(data_dir, gid="g900000010"):
    return research.shortlist(data_dir, [gid], None)[0]


# llm.py: keys, modes, ledger


def test_same_request_same_key_and_a_prompt_change_is_a_new_key():
    params = {"model": "m", "system": "s", "messages": [{"role": "user", "content": "hi"}]}
    reordered = {"messages": [{"content": "hi", "role": "user"}], "system": "s", "model": "m"}
    assert llm.request_key(params) == llm.request_key(reordered)
    assert llm.request_key(params) != llm.request_key({**params, "system": "s2"})
    # Transport settings are not part of the key.
    assert llm.request_key(params) == llm.request_key({**params, "betas": ["x"]})


def test_replay_never_builds_a_client_and_raises_on_a_miss(tmp_path):
    model = LLM(RECORDINGS, "replay", tmp_path / "ledger.jsonl")
    with pytest.raises(RecordingMiss):
        model.create("research", "g1", model="claude-opus-5-5", messages=[])
    assert model._client is None


def test_record_stores_once_then_replays(tmp_path):
    answer = make_fixtures.message(1, [make_fixtures.text("ok")], "end_turn", {"input": 10})
    client = ScriptedClient(lambda params: answer)
    params = {"model": "claude-opus-5-5", "max_tokens": 10,
              "messages": [{"role": "user", "content": "hi"}]}  # fmt: skip
    recorder = LLM(tmp_path / "rec", "record", tmp_path / "ledger.jsonl", client=client)
    assert recorder.create("test", "g1", **params)["content"][0]["text"] == "ok"
    recorder.create("test", "g1", **params)
    assert len(client.requests) == 1  # the second call replayed
    # Refusal fallback on by default, outside the key.
    assert client.requests[0]["fallbacks"] == "default"
    assert client.requests[0]["betas"] == [llm.FALLBACK_BETA]
    stored = json.loads(next((tmp_path / "rec" / "test").glob("*.json")).read_text("utf-8"))
    assert set(stored) == {"request", "response", "usage", "cost_usd", "recorded_at"}
    LLM(tmp_path / "rec", "refresh", client=client).create("test", "g1", **params)
    assert len(client.requests) == 2


def test_ledger_prices_cache_and_searches_and_marks_replays(tmp_path):
    usage = {"input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
             "cache_read_input_tokens": 1_000_000, "output_tokens": 1_000_000,
             "server_tool_use": {"web_search_requests": 3, "web_fetch_requests": 2}}  # fmt: skip
    # Opus 5.5: $4 input, $5 cache write, $0.20 cache read, $20 output, $10 per 1k searches.
    assert llm.cost_usd("claude-opus-5-5", usage) == pytest.approx(4 + 5 + 0.2 + 20 + 0.03)
    with pytest.raises(KeyError, match="no price"):
        llm.cost_usd("claude-unknown", usage)

    answer = {**make_fixtures.message(1, [], "end_turn", {}), "usage": usage}
    ledger = tmp_path / "ledger.jsonl"
    model = LLM(tmp_path / "rec", "record", ledger, client=ScriptedClient(lambda p: answer))
    model.create("test", "g1", model="claude-opus-5-5", messages=[])
    model.create("test", "g1", model="claude-opus-5-5", messages=[])
    live, replayed = llm.read_ledger(ledger)
    assert (live["replayed"], replayed["replayed"]) == (False, True)
    assert live["usd"] == replayed["usd"] == pytest.approx(29.23)
    assert live["web_searches"] == 3 and live["cache_read_tokens"] == 1_000_000
    assert model.spent_usd == pytest.approx(29.23)  # replays cost nothing this run


# Agent: schema, checks, loop


def test_schema_is_built_from_the_config_signals(icp):
    tool = agent.record_tool(icp)
    assert tool["strict"] is True
    signals = tool["input_schema"]["properties"]["signals"]
    assert signals["required"] == [s.id for s in icp.signals]
    assert signals["additionalProperties"] is False

    other = icp.model_copy(update={"signals": [config.Signal(id="a", label="A", weight=1),
                                                config.Signal(id="b", label="B", weight=2)]})  # fmt: skip
    tool = agent.record_tool(other)
    assert list(tool["input_schema"]["properties"]["signals"]["properties"]) == ["a", "b"]
    assert "`a` (A)" in agent.system_prompt(other)
    answer = good_answer(["a", "b"])
    assert set(agent.result_model(other).model_validate(answer).signals.model_dump()) == {"a", "b"}


def good_answer(ids, url="https://annuaire-entreprises.data.gouv.fr/entreprise/900000010"):
    def sig():
        return {"value": 1, "found": True, "rationale_en": "r",
                "evidence": [{"quote": "q", "quote_en": "q", "url": url}]}  # fmt: skip

    return {"website": None, "signals": {i: sig() for i in ids}, "notes_en": "",
            "facts": {"product_lines": [], "headcount_stated": None, "open_roles": [],
                      "tools_seen": []}}  # fmt: skip


def test_validation_rejects_a_missing_signal_and_a_value_out_of_range(icp):
    ids = [s.id for s in icp.signals]
    model = agent.result_model(icp)
    with pytest.raises(ValidationError, match="growth"):
        model.model_validate(good_answer([i for i in ids if i != "growth"]))
    bad = good_answer(ids)
    bad["signals"] = {**bad["signals"], "growth": {**bad["signals"]["growth"], "value": 1.5}}
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        model.model_validate(bad)


def test_checks_flag_missing_evidence_and_unseen_urls(icp):
    answer = good_answer([s.id for s in icp.signals])
    answer["signals"]["growth"] = {"value": 0.5, "found": True, "rationale_en": "r",
                                   "evidence": []}  # fmt: skip
    answer["signals"]["tech_maturity"]["evidence"][0]["url"] = "https://invented.example/x"
    seen = {agent.normalize_url(answer["signals"]["size_fit"]["evidence"][0]["url"])}
    flags = agent.check(answer, seen)
    assert {(f["code"], f["signal"]) for f in flags} == {
        ("no_evidence", "growth"),
        ("unverified_url", "tech_maturity"),
    }


def test_urls_compare_loosely_and_only_tool_results_count():
    assert agent.normalize_url("https://WWW.Site.example/a/#top") == "site.example/a"
    assert agent.normalize_url("http://site.example/") == "site.example"
    content = [
        {"type": "text", "text": "see https://from-the-model.example"},
        *make_fixtures.search("x", "q", [("https://found.example/page", "t")]),
    ]
    assert agent.seen_urls(content) == {"found.example/page"}


def test_an_invalid_answer_gets_one_retry_with_the_error(icp, data_dir, tmp_path):
    ids = [s.id for s in icp.signals]
    answers = [good_answer(ids[:-1]), good_answer(ids)]

    def script(params):
        n = sum(m["role"] == "assistant" for m in params["messages"])
        return make_fixtures.message(n, [make_fixtures.record(f"r{n}", answers[n])],
                                     "tool_use", {"input": 100})  # fmt: skip

    client = ScriptedClient(script)
    out = agent.research(icp, LLM(tmp_path / "rec", "record", client=client), lead(data_dir))
    assert (out["status"], out["calls"], out["flags"]) == ("ok", 2, [])
    retry = client.requests[1]["messages"][-1]["content"][0]
    assert retry["type"] == "tool_result" and retry["is_error"] is True
    assert "tech_maturity" in retry["content"]

    answers[1] = good_answer(ids[:-1])  # still invalid after the retry: the lead fails
    out = agent.research(icp, LLM(tmp_path / "rec2", "record", client=ScriptedClient(script)),
                         lead(data_dir))  # fmt: skip
    assert out["status"] == "failed" and "tech_maturity" in out["reason"]
    assert out["flags"][0]["code"] == "invalid_output"


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_and_max_tokens_fail_the_lead(icp, data_dir, tmp_path, stop):
    client = ScriptedClient(lambda p: make_fixtures.message(1, [], stop, {"input": 100}))
    model = LLM(tmp_path / "rec", "record", tmp_path / "ledger.jsonl", client=client)
    out = agent.research(icp, model, lead(data_dir))
    assert out["status"] == "failed" and stop in out["reason"]
    assert list((tmp_path / "rec" / "research").glob("*.json"))  # recorded all the same


def test_pause_turn_is_resumed_as_a_second_call(icp, data_dir):
    model = LLM(RECORDINGS, "replay", data_dir / "ledger.jsonl")
    out = agent.research(icp, model, lead(data_dir, "g900000010"))
    assert (out["status"], out["calls"]) == ("ok", 2)
    calls = llm.read_ledger(data_dir / "ledger.jsonl")
    assert [c["lead"] for c in calls] == ["g900000010"] * 2 and all(c["replayed"] for c in calls)


# Runner and CLI


def test_research_offline_end_to_end(data_dir, capsys):
    groups = [a for g in GROUPS for a in ("--group", g)]
    cli.main(["--data-dir", str(data_dir), "research", "--offline",
              "--recordings", str(RECORDINGS), *groups])  # fmt: skip
    signals = pd.read_parquet(data_dir / "signals.parquet")
    assert len(signals) == 3 * 4
    s = signals.set_index(["group_id", "signal"])
    assert s.loc[("g900000010", "growth"), "value"] == 1
    assert s.loc[("g900000010", "growth"), "evidence"][0]["quote_en"].startswith("We are hiring")
    assert not s.loc[("g900000060", "growth"), "found"]
    assert s.loc[("g900000060", "growth"), "value"] == 0
    assert list(s.loc[("g900000110", "tech_maturity"), "flags"]) == ["unverified_url"]
    assert list(s.loc[("g900000110", "size_fit"), "flags"]) == []
    saved = json.loads((data_dir / "research" / "g900000060.json").read_text("utf-8"))
    assert saved["result"]["website"] is None

    cli.main(["--data-dir", str(data_dir), "cost"])
    report = capsys.readouterr().out
    assert "Cost per lead" in report and "Leads researched   3" in report
    assert "Flagged leads      1" in report and "Failed leads       0" in report


def test_budget_stops_new_leads(icp, data_dir, tmp_path):
    ids = [s.id for s in icp.signals]
    answer = make_fixtures.message(1, [make_fixtures.record("r", good_answer(ids))], "tool_use",
                                   {"output": 1_000_000})  # $20 on Opus 5.5  # fmt: skip
    icp = icp.model_copy(update={"research": icp.research.model_copy(update={"concurrency": 1})})
    results = research.run(icp, data_dir, limit=3, recordings_dir=tmp_path / "rec",
                           budget_usd=30, client=ScriptedClient(lambda p: answer),
                           log=lambda _: None)  # fmt: skip
    assert len(results) == 2  # $20 after the first, $40 after the second: stop


def test_research_without_source_fails_clearly(icp, tmp_path):
    with pytest.raises(FileNotFoundError, match="icp-scout source"):
        research.run(icp, tmp_path, mode="replay", log=lambda _: None)


def test_recordings_match_the_current_prompt(data_dir):
    """Fails when the prompt, tools or config changed: re-run make_fixtures.py."""
    icp = config.load(ROOT / "config" / "icp.example.yaml")
    for gid in GROUPS:
        agent.research(icp, LLM(RECORDINGS, "replay"), lead(data_dir, gid))


def test_the_fixture_groups_are_shortlisted(market_dir):
    market = pd.read_parquet(market_dir / "market.parquet")
    assert set(GROUPS) <= set(market.loc[market["shortlisted"], "group_id"])


def test_a_case_config_cannot_record_into_the_committed_fixtures(data_dir, tmp_path):
    case = tmp_path / "case.yaml"
    case.write_text((ROOT / "config" / "icp.example.yaml").read_text("utf-8"), "utf-8")
    with pytest.raises(SystemExit, match="private/llm"):
        cli.main(["--config", str(case), "--data-dir", str(data_dir), "research",
                  "--recordings", str(RECORDINGS)])  # fmt: skip
