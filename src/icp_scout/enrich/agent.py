"""WP2. Research one shortlisted group and extract the rubric signals.

The agent reads the group's registry facts, finds and reads its website with
server-side web search and web fetch, and ends by calling `record_signals`: each
signal from the ICP config as a value in [0, 1] with evidence (a verbatim quote,
its English translation, the URL). It never produces the score: that is the
rubric's job (ADR 0002).

The code checks the answer and flags what fails; it does not fix anything. An
answer that doesn't fit the schema gets one retry with the error sent back, then
the lead is `failed`. A value above 0 without evidence, or evidence citing a URL
that never appeared in the conversation, is kept and flagged.
"""

import json
import math
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from icp_scout.config import IcpConfig
from icp_scout.llm import LLM

PURPOSE = "research"
TOOL = "record_signals"
# The basic server tool versions, not the dynamic-filtering ones (_20260209).
# In the pilot (2026-09-29, Sonnet 5.5), the model called the _20260209 tools
# directly with their code-execution input ({"params": {...}}), and every call
# failed with invalid_tool_input. When they did work, each search went through
# several code-execution turns and cost about twice as much. The basic versions
# also run on Haiku 4.5.
WEB_SEARCH = "web_search_20250305"
WEB_FETCH = "web_fetch_20250910"
MAX_TOKENS = 64000  # streamed, so no HTTP timeout; thinking counts against it
MAX_CALLS = 6  # per lead: first answer + pause_turn resumes + one retry
REGISTRY_URL = "https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str
    quote_en: str
    url: str


class SignalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float = Field(ge=0, le=1)
    found: bool
    rationale_en: str
    evidence: list[Evidence]


class Facts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_lines: list[str] = []
    headcount_stated: int | None = None
    open_roles: list[str] = []
    tools_seen: list[str] = []


def result_model(icp: IcpConfig) -> type[BaseModel]:
    """The answer's pydantic model: one required field per configured signal."""
    signals = create_model(
        "Signals",
        __config__=ConfigDict(extra="forbid"),
        **{s.id: (SignalResult, ...) for s in icp.signals},
    )
    return create_model(
        "ResearchResult",
        __config__=ConfigDict(extra="forbid"),
        website=(str | None, ...),
        signals=(signals, ...),
        facts=(Facts, ...),
        notes_en=(str, ...),
    )


# Prompt and tools: identical for every lead, so they stay in the prompt cache.


def system_prompt(
    icp: IcpConfig,
    search: str = "web_search",
    fetch: str = "web_fetch",
    answer: str = TOOL,
    extra: str = "",
) -> str:
    """The research brief. The defaults name the API tools; the claude-code backend
    passes its own tool names and a note on WebFetch."""
    r, seg = icp.research, icp.segment
    signals = "\n".join(
        f"- `{s.id}` ({s.label}): {' '.join((s.definition or '').split())}" for s in icp.signals
    )
    refs = "\n".join(f"- {name}" for name in icp.reference_customers) or "- (none given)"
    return f"""\
You research one company group for {icp.vendor.name}, which sells: {" ".join(icp.vendor.pitch.split())}

Your job is to find evidence for the signals below, not to judge the company. \
For each signal, record a value in [0, 1] (usually 0, 0.5 or 1) against its \
definition, with the evidence behind it. A rubric in code turns the values into \
a score; you never score.

The target segment is groups of {seg.headcount_min}-{seg.headcount_max} staff in total \
(all companies of the group together).

Signals:
{signals}

Known good fits, for calibration (companies like these would get high values):
{refs}

How to work:
- You get the group's registry facts first: its companies with their SIRENs \
and registry pages, certified domains, headcount bands, revenue, and the \
website if the registry lists one. Registry facts count as evidence; cite the \
company's registry page as the URL.
- If no website is given, look for it with {search}. Before you use a site, \
check that it belongs to this group (same name, town or SIREN), not a namesake.
- Read the pages that matter with {fetch}: home, services or products, \
careers or recruitment, about, contact or quote request. Also look for the \
group's job ads. You have at most {r.max_searches} searches and {r.max_fetches} \
fetches; stop when you have enough.{extra}

Rules for evidence:
- A value above 0 needs at least one piece of evidence. If you find nothing, \
set value 0 and found false: no evidence is not the same as a weak signal.
- A quote is copied verbatim from the page in its original language (usually \
French), one or two sentences. quote_en is its English translation.
- url is the exact page the quote is on: a search result or page you retrieved \
in this conversation, or a registry page given to you. Never cite a URL you did \
not retrieve.
- rationale_en: one sentence in English on why this value.
- Write everything in English except the quotes, including any text between tool calls.

When you are done, call {answer} once with everything. That call is your answer; \
do not write the findings as text. In notes_en, tell an SDR what to know before \
calling (in English): group structure, recent news, a namesake you ruled out.
"""


def record_tool(icp: IcpConfig) -> dict:
    """The strict client tool the agent ends with; its schema comes from the config."""
    evidence = _object({
        "quote": {"type": "string", "description": "Verbatim from the page, original language."},
        "quote_en": {"type": "string", "description": "English translation of the quote."},
        "url": {"type": "string", "description": "The page the quote is on."},
    })  # fmt: skip
    signal = {
        "value": {"type": "number", "description": "In [0, 1], usually 0, 0.5 or 1."},
        "found": {"type": "boolean", "description": "False when no evidence was found."},
        "rationale_en": {"type": "string", "description": "One sentence, English."},
        "evidence": {"type": "array", "items": evidence},
    }
    signals = _object({s.id: {**_object(signal), "description": s.label} for s in icp.signals})
    strings = {"type": "array", "items": {"type": "string"}}
    facts = _object({
        "product_lines": strings,
        "headcount_stated": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "open_roles": strings,
        "tools_seen": strings,
    })  # fmt: skip
    return {
        "name": TOOL,
        "description": (
            "Record the signals with their evidence. Call once, at the end of the "
            "research; this is the answer."
        ),
        "input_schema": _object(
            {
                "website": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "description": "The group's own website, or null.",
                },
                "signals": signals,
                "facts": facts,
                "notes_en": {"type": "string"},
            }
        ),
        "strict": True,
        "eager_input_streaming": True,
    }


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def tools(icp: IcpConfig) -> list[dict]:
    r = icp.research
    fetch = {"type": WEB_FETCH, "name": "web_fetch", "max_uses": r.max_fetches}
    if r.max_page_tokens:
        fetch["max_content_tokens"] = r.max_page_tokens
    return [
        {"type": WEB_SEARCH, "name": "web_search", "max_uses": r.max_searches},
        fetch,
        record_tool(icp),
    ]


def lead_message(lead: dict) -> str:
    """The registry facts for one group, as the first user message."""
    members = [
        {"siren": s, "name": n, "registry_url": REGISTRY_URL.format(siren=s)}
        for s, n in zip(lead["members"], lead["member_names"], strict=True)
    ]
    facts = {
        "group_name": lead["name"],
        "companies": members,
        "grouped_because": lead.get("link_reason") or None,
        "department": lead.get("department"),
        "website_in_registry": lead.get("website"),
        "certified_domains": list(lead.get("domains") or []),
        "product_lines_from_certifications": list(lead.get("product_lines") or []),
        "headcount_bands_sum": {
            "low": lead.get("headcount_low"),
            "mid": lead.get("headcount_mid"),
            "high": lead.get("headcount_high"),
        },
        "revenue_eur": lead.get("revenue"),
        "oldest_company_created": lead.get("created"),
        "found_via": lead.get("source"),
    }
    return "Research this company group. Registry facts:\n\n" + json.dumps(
        _clean(facts), ensure_ascii=False, indent=1
    )


def _clean(value):
    """JSON-safe: parquet gives numpy types and NaN."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# The loop.


def research(icp: IcpConfig, llm: LLM, lead: dict) -> dict:
    """Research one group. Returns the lead's result: status, answer, flags, calls."""
    gid = lead["group_id"]
    base = {
        "model": icp.research.model,
        "max_tokens": MAX_TOKENS,
        "system": [
            {"type": "text", "text": system_prompt(icp), "cache_control": {"type": "ephemeral"}}
        ],
        "tools": tools(icp),
        "tool_choice": {"type": "auto"},
        "output_config": {"effort": icp.research.effort},
    }
    first = lead_message(lead)
    messages = [{"role": "user", "content": first}]
    seen = set(map(normalize_url, urls_in(first)))
    model = result_model(icp)
    out = {"group_id": gid, "name": lead["name"], "model": icp.research.model, "calls": 0,
           "status": "failed", "reason": None, "flags": [], "result": None}  # fmt: skip
    retried = False

    while out["calls"] < MAX_CALLS:
        response = llm.create(PURPOSE, gid, **base, messages=messages)
        out["calls"] += 1
        content = response["content"]
        seen |= seen_urls(content)
        stop = response.get("stop_reason")
        if stop in ("refusal", "max_tokens"):
            out["reason"] = f"stop_reason {stop}"
            return out
        messages = [*messages, {"role": "assistant", "content": content}]
        if stop == "pause_turn":
            continue  # the server-side loop hit its limit; resend to resume it
        call = next((b for b in reversed(content) if _is_record_call(b)), None)
        if call is None:
            if retried:
                out["reason"] = f"no {TOOL} call"
                return out
            retried = True
            nudge = f"Call {TOOL} now with your findings; it is the only way to answer."
            messages = [*messages, {"role": "user", "content": nudge}]
            continue
        try:
            answer = model.model_validate(call["input"])
        except ValidationError as e:
            if retried:
                out["reason"] = f"invalid {TOOL} input: {_short(e)}"
                out["flags"] = [{"code": "invalid_output", "signal": None, "detail": _short(e)}]
                return out
            retried = True
            error = {"type": "tool_result", "tool_use_id": call["id"], "is_error": True,
                     "content": f"The input does not validate; fix it and call {TOOL} "
                                f"again.\n{_short(e)}"}  # fmt: skip
            messages = [*messages, {"role": "user", "content": [error]}]
            continue
        result = answer.model_dump()
        out.update(status="ok", result=result, flags=check(result, seen))
        return out
    out["reason"] = f"no answer after {MAX_CALLS} calls"
    return out


# The claude-code backend: the CLI runs the loop, on the author's subscription.

CC_SEARCH, CC_FETCH, CC_ANSWER = "WebSearch", "WebFetch", "StructuredOutput"
# Claude Code's WebFetch hands the page to a small model with a prompt and
# returns its answer, not the page. Without this, quotes come back paraphrased.
CC_FETCH_NOTE = f"""
- {CC_FETCH} shows you another model's reading of the page, not the page \
itself. In its prompt, ask for the relevant passages copied verbatim in the \
original language, so your quotes are verbatim."""


def research_claude_code(icp: IcpConfig, cc, lead: dict) -> dict:
    """Research one group through the `claude` CLI (claude_code.ClaudeCode).
    One run per lead: the CLI runs the loop and checks the answer against the schema."""
    from icp_scout.claude_code import tool_calls, tool_results

    gid, first = lead["group_id"], lead_message(lead)
    out = {"group_id": gid, "name": lead["name"], "model": icp.research.model, "calls": 0,
           "status": "failed", "reason": None, "flags": [], "result": None}  # fmt: skip
    rec = cc.run(
        PURPOSE,
        gid,
        model=icp.research.model,
        effort=icp.research.effort,
        system=system_prompt(icp, CC_SEARCH, CC_FETCH, CC_ANSWER, CC_FETCH_NOTE),
        prompt=first,
        schema=record_tool(icp)["input_schema"],
        tools=[CC_SEARCH, CC_FETCH],
    )
    out["calls"] = rec["result"].get("num_turns")
    answer = rec["result"].get("structured_output")
    if answer is None:
        out["reason"] = "no structured output"
        return out
    try:
        result = result_model(icp).model_validate(answer).model_dump()
    except ValidationError as e:
        out["reason"] = f"invalid structured output: {_short(e)}"
        out["flags"] = [{"code": "invalid_output", "signal": None, "detail": _short(e)}]
        return out
    # Retrieved: the URLs in search results and fetched pages, and the URLs fetched.
    seen = set(map(normalize_url, urls_in(first)))
    for text in tool_results(rec["transcript"]):
        seen |= set(map(normalize_url, urls_in(text)))
    for call in tool_calls(rec["transcript"]):
        if call.get("name") == CC_FETCH and (call.get("input") or {}).get("url"):
            seen.add(normalize_url(call["input"]["url"]))
    out.update(status="ok", result=result, flags=check(result, seen))
    return out


def _is_record_call(block: dict) -> bool:
    return block.get("type") == "tool_use" and block.get("name") == TOOL


def _short(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, err['loc'])) or 'input'}: {err['msg']}" for err in e.errors()
    )[:1500]


def check(result: dict, seen: set[str]) -> list[dict]:
    """Content checks on a schema-valid answer. Each failure is a flag, nothing is fixed."""
    flags = []
    for sid, sig in result["signals"].items():
        if sig["value"] > 0 and not sig["evidence"]:
            flags.append({"code": "no_evidence", "signal": sid,
                          "detail": f"value {sig['value']} without evidence"})  # fmt: skip
        for ev in sig["evidence"]:
            if normalize_url(ev["url"]) not in seen:
                flags.append({"code": "unverified_url", "signal": sid, "detail": ev["url"]})
    return flags


# URLs the agent actually retrieved.

URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}\\]+")


def urls_in(text: str) -> list[str]:
    return [u.rstrip(".,;:") for u in URL_RE.findall(text)]


def seen_urls(content: list[dict]) -> set[str]:
    """URLs in the server tools' results (search results, fetched pages), not the
    model's own text: those are what the evidence is checked against."""
    seen = set()
    for block in content:
        if block.get("type", "").endswith("_tool_result") and block.get("type") != "tool_result":
            seen |= set(map(normalize_url, urls_in(json.dumps(block, ensure_ascii=False))))
    return seen


def normalize_url(url: str) -> str:
    """Compare URLs loosely: scheme, www., case of the host, trailing slash, fragment."""
    url = url.strip().split("#")[0]
    m = re.match(r"(?i)^https?://(?:www\.)?([^/?]+)(.*)$", url)
    if not m:
        return url
    host, rest = m.group(1).lower(), m.group(2)
    return host + (rest.rstrip("/") if rest not in ("", "/") else "")
