"""WP3. Regrade one researched group from its recorded evidence: no web, no new facts.

WP2's three-step values saturate the rubric (most leads tie at the top). This
pass reads what the agent already recorded and returns, per lead:
- the group's headcount as a number, for the sweet-spot curve in score.py;
- each signal that has `grades` in the config, on that finer scale;
- a short English phrase per signal, for the SDR's one-line reason.
It never scores (ADR 0002): it grades signals against written scales.
"""

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from icp_scout.config import IcpConfig
from icp_scout.enrich.agent import _clean, _object

PURPOSE = "regrade"
TOOL = "record_grades"
EFFORT = "low"  # a reading task over a few quotes
MAX_TOKENS = 8000
STEPS = [0, 0.25, 0.5, 0.75, 1]


def graded(icp: IcpConfig) -> list:
    return [s for s in icp.signals if s.grades]


def result_model(icp: IcpConfig) -> type[BaseModel]:
    grade = create_model(
        "Grade",
        __config__=ConfigDict(extra="forbid"),
        value=(float, Field(ge=0, le=1)),
        basis_en=(str, ...),
    )
    grades = create_model(
        "Grades", __config__=ConfigDict(extra="forbid"), **{s.id: (grade, ...) for s in graded(icp)}
    )
    phrases = create_model(
        "Phrases", __config__=ConfigDict(extra="forbid"), **{s.id: (str, ...) for s in icp.signals}
    )
    return create_model(
        "RegradeResult",
        __config__=ConfigDict(extra="forbid"),
        headcount=(int | None, ...),
        headcount_basis_en=(str, ...),
        grades=(grades, ...),
        phrases=(phrases, ...),
    )


def schema(icp: IcpConfig) -> dict:
    grade = _object({
        "value": {"type": "number", "enum": STEPS},
        "basis_en": {"type": "string", "description": "One sentence: which evidence, why this step."},
    })  # fmt: skip
    return _object({
        "headcount": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                      "description": "The whole group's staff, best estimate, or null."},
        "headcount_basis_en": {"type": "string"},
        "grades": _object({s.id: grade for s in graded(icp)}),
        "phrases": _object({s.id: {"type": "string", "description": "At most 8 words."}
                            for s in icp.signals}),
    })  # fmt: skip


def system_prompt(icp: IcpConfig) -> str:
    seg = icp.segment
    scales = "\n".join(f"- `{s.id}` ({s.label}): {' '.join(s.grades.split())}" for s in graded(icp))
    return f"""\
You regrade one company group that a research agent already investigated for \
{icp.vendor.name}. You get the agent's recorded findings: per signal a value, \
a rationale and verbatim evidence, plus registry facts. You have no web access. \
Use only what is recorded; never add facts of your own. You never score.

1. headcount: the whole group's staff as one number (the target segment is \
{seg.headcount_min}-{seg.headcount_max}). Prefer a number the evidence states for \
the whole group. If the stated number covers one company or only field staff, \
and the registry bands are larger, use the larger figure. With no stated number, \
use the midpoint of the registry bands. null only if there is neither. Say in \
headcount_basis_en which source you used.

2. Grade these signals on their finer scale, using one of {STEPS}:
{scales}
If the recorded evidence doesn't support a step, take the lower one. A signal \
the agent valued 0 with no evidence stays 0.

3. phrases: per signal, at most 8 English words an SDR can read at a glance, \
concrete, e.g. "PV + air/water heat pumps + storage", "3 open sales roles", \
"quote simulator on site", "~120 staff across 4 branches". No judgement words.

Answer with {TOOL} (or the structured output) only."""


def lead_message(lead: dict, signals: list[dict], facts: dict | None) -> str:
    body = {
        "group_name": lead["name"],
        "registry_headcount_bands_sum": {
            "low": lead.get("headcount_low"),
            "mid": lead.get("headcount_mid"),
            "high": lead.get("headcount_high"),
            "companies_without_band": lead.get("headcount_unknown"),
        },
        "agent_signals": {
            s["signal"]: {
                "value": s["value"],
                "rationale_en": s["rationale_en"],
                "evidence": [{"quote_en": e["quote_en"], "url": e["url"]} for e in s["evidence"]],
            }
            for s in signals
        },
        "agent_facts": facts,
    }
    return "Regrade this group. Recorded findings:\n\n" + json.dumps(
        _clean(body), ensure_ascii=False, indent=1
    )


def regrade(icp: IcpConfig, llm, lead: dict, signals: list[dict], facts: dict | None) -> dict:
    """One call. `llm` is an llm.LLM or a claude_code.ClaudeCode. Returns status and result."""
    from icp_scout.claude_code import ClaudeCode

    gid = lead["group_id"]
    out = {"group_id": gid, "name": lead["name"], "model": icp.research.model,
           "status": "failed", "reason": None, "result": None}  # fmt: skip
    prompt = lead_message(lead, signals, facts)
    if isinstance(llm, ClaudeCode):
        rec = llm.run(PURPOSE, gid, model=icp.research.model, effort=EFFORT,
                      system=system_prompt(icp), prompt=prompt, schema=schema(icp),
                      tools=[])  # fmt: skip
        answer = rec["result"].get("structured_output")
    else:
        tool = {"name": TOOL, "description": "Record the grades. This is the answer.",
                "input_schema": schema(icp), "strict": True}  # fmt: skip
        response = llm.create(
            PURPOSE, gid, model=icp.research.model, max_tokens=MAX_TOKENS,
            system=system_prompt(icp), messages=[{"role": "user", "content": prompt}],
            tools=[tool], tool_choice={"type": "tool", "name": TOOL},
        )  # fmt: skip
        call = next((b for b in response["content"] if b.get("type") == "tool_use"), None)
        answer = call["input"] if call else None
    if answer is None:
        out["reason"] = "no answer"
        return out
    try:
        out.update(status="ok", result=result_model(icp).model_validate(answer).model_dump())
    except ValidationError as e:
        out["reason"] = f"invalid answer: {e.error_count()} errors"
    return out


# `icp-scout regrade`: every researched group, recorded, resumable.


def run(icp: IcpConfig, data_dir, *, mode: str = "record", recordings_dir="fixtures/llm",
        client=None, runner=None, log=print) -> list[dict]:  # fmt: skip
    """Regrade every group in data/research/ that researched ok; write data/regrade/."""
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    import pandas as pd

    from icp_scout.claude_code import ClaudeCode, UsageLimit
    from icp_scout.llm import LLM, write_json
    from icp_scout.research import _row

    data_dir = Path(data_dir)
    for name in ("signals.parquet", "market.parquet"):
        if not (data_dir / name).exists():
            raise FileNotFoundError(f"{data_dir / name} not found: run `icp-scout research` first")
    signals = pd.read_parquet(data_dir / "signals.parquet")
    signals = signals[signals["status"] == "ok"]
    market = pd.read_parquet(data_dir / "market.parquet").set_index("group_id", drop=False)
    r, ledger = icp.research, data_dir / "ledger.jsonl"
    if r.backend == "claude-code":
        extra = {"runner": runner} if runner else {}
        llm = ClaudeCode(recordings_dir, mode, ledger, max_utilization=r.max_utilization, **extra)
    else:
        llm = LLM(recordings_dir, mode, ledger, client=client)

    def one(gid: str) -> dict | None:
        rows = [_row(x) for x in signals[signals["group_id"] == gid].to_dict("records")]
        research = json.loads((data_dir / "research" / f"{gid}.json").read_text("utf-8"))
        facts = (research["result"] or {}).get("facts")
        try:
            out = regrade(icp, llm, _row(market.loc[gid].to_dict()), rows, facts)
        except UsageLimit as e:
            log(f"  {gid}: usage limit ({e}); re-run later to resume.")
            return None
        write_json(data_dir / "regrade" / f"{gid}.json", out)
        return out

    ids = list(dict.fromkeys(signals["group_id"]))
    log(f"Regrading {len(ids)} groups ({mode}, {r.model}, {r.backend}) ...")
    with ThreadPoolExecutor(r.concurrency) as pool:
        results = [o for o in pool.map(one, ids) if o]
    failed = [f"{o['group_id']} ({o['reason']})" for o in results if o["status"] != "ok"]
    log(f"Done: {len(results) - len(failed)} of {len(ids)} regraded"
        + (f"; failed: {'; '.join(failed)}" if failed else ""))  # fmt: skip
    return results
