# WP2: Agent research

Budget: 5h. Planned 2026-09-29, to be built in a remote session.

**Done when:** `icp-scout research` gives every shortlisted group the four
rubric signals, each a value in [0, 1] with evidence (quote, English
translation, URL). Every model answer is recorded and replays offline, and
`icp-scout cost` reports the cost per researched lead.

## Rules for this session

- Read `CLAUDE.md`, `docs/requirements.md`, ADRs 0002-0004 and
  `docs/wp/wp1-sourcing.md` first. **Load the claude-api skill before writing
  `llm.py`** (CLAUDE.md). Take the model id, tool types and SDK calls from it,
  not from memory.
- No case-company content (ADR 0003). Build against `config/icp.example.yaml`
  and synthetic fixtures only.
- **You need no API key.** Recordings for tests are synthetic, in the exact
  shape of real Messages API responses (`message.to_dict()`), made by
  `fixtures/llm/make_fixtures.py`. The first live run is the author's (see
  "Author acceptance").
- Work on branch `wp2-research`, push, open a PR (or draft its description if
  there is no `gh`), don't merge. Add the build-log entry at the end (mode
  `remote`, author time TODO).

## Why this WP looks the way it does

- ADR 0002: the model returns signals with evidence, never a score.
- WP0: only ~29% of target companies list their own website, so the agent
  needs web search for most leads. That drives the cost per lead.
- WP1: register-source groups have an unknown product mix (pre-score 0.5).
  The agent resolves it.
- **Recordings of real companies are case content.** They can't go under the
  committed `fixtures/llm/`. The recordings directory is a setting: default
  `fixtures/llm/` (synthetic, committed), and `private/llm/` for the case run
  (set by the author with `ICP_SCOUT_RECORDINGS` or `--recordings`).

## 1. `llm.py`: the one door to a model (ADR 0004)

- `LLM(recordings_dir, mode, ledger_path)` with the modes `replay` (read only,
  raise `RecordingMiss` on a miss, like `http.CacheMiss`), `record` (call on a
  miss, store) and `refresh` (always call, overwrite).
- `LLM.create(purpose: str, lead_id: str, **params) -> dict`: the key is the
  sha256 of the canonical JSON of the request params (model, system,
  messages, tools, output_config), so any prompt change is a new recording.
  A stored file holds `{request, response, usage, cost_usd, recorded_at}`,
  written atomically (tmp + replace, as in `http.py`).
- Uses the official `anthropic` SDK: streaming with `get_final_message()`,
  SDK retries, typed errors. Model and effort come from the config (below).
  Handle `stop_reason` `pause_turn` (resume with the assistant content
  appended), `refusal` and `max_tokens` (record them, mark the lead failed).
  Enable server-side refusal fallbacks as the skill recommends for the model.
- **Cost ledger:** every call, recorded or replayed, appends one line to
  `data/ledger.jsonl`: lead, purpose, model, input / cache-write / cache-read /
  output tokens, web searches (`usage.server_tool_use`), USD, replayed yes/no.
  The price table is a constant in `llm.py` with its source and date (per
  MTok by model, plus $ per 1k web searches; take the current numbers from the
  skill and the pricing page).
- Prompt caching: the system prompt and tool list are identical for every lead,
  so put `cache_control` on the system block.

## 2. `enrich/agent.py`: research one group

**Input** per shortlisted group, from `market.parquet`: name, member names and
SIRENs, department, website (or none), RGE domains, product lines, headcount
low/mid/high, revenue, created, source, link reason. Registry facts are
context, and a registry fact can be cited as evidence (URL = the company's
page on annuaire-entreprises.data.gouv.fr).

**System prompt** (built from the config, stable across leads): the vendor
pitch, each signal's `id`, `label` and `definition`, the segment band, the
reference customers as calibration anchors, and the rules:
- a value > 0 needs at least one piece of evidence; when nothing is found the
  value is 0 and `found: false` (no evidence is not the same as a weak signal);
- quotes are verbatim from the page (usually French), each with an English
  translation (`quote_en`); the author doesn't read French;
- check that the site belongs to this company (same name, town or SIREN), not a
  namesake.

**Tools:** the server tools `web_search` and `web_fetch` (the current type
versions from the skill), with `max_uses` caps from the config (default: 5
searches, 6 fetches), plus a strict client tool `record_signals` whose schema is
built from the config's signal ids. The loop ends when the model calls
`record_signals`. Forced `tool_choice` is rejected on current models, so use
`auto` and tell the model in the prompt. (Check in the skill whether structured
outputs can be combined with the web tools. If they can, that is simpler; use
whichever is documented to work.)

**Output schema** (pydantic, validated after every call):

    {
      "website": "https://..." | null,
      "signals": {
        "<signal id>": {
          "value": 0 | 0.5 | 1 (any number in [0, 1] is accepted),
          "found": bool,
          "rationale_en": "one sentence",
          "evidence": [{"quote": "...", "quote_en": "...", "url": "..."}]
        }
      },
      "facts": {"product_lines": [...], "headcount_stated": int | null,
                "open_roles": [...], "tools_seen": [...]},
      "notes_en": "anything an SDR should know"
    }

**Checks in code**, each failure is flagged on the lead, not silently fixed:
- every configured signal is present, values are in [0, 1];
- `value > 0` has evidence;
- **every evidence URL was seen in this conversation** (a search result, a
  fetched page or the registry URL). An unseen URL is flagged as
  `unverified_url`, which catches invented links;
- one retry with the validation error sent back as the tool result; after
  that the lead is `failed`, with the reason.

## 3. Runner and outputs

`enrich/__init__.py` or a new `research.py`: `run(icp, data_dir, limit, mode,
recordings_dir, budget_usd, group_ids)`.
- Reads the shortlisted rows of `data/market.parquet` (fails clearly if
  `source` hasn't been run).
- Up to 4 leads in parallel (thread pool); resumable, because a recorded lead
  replays at no cost.
- **Budget guard:** stops starting new leads once the ledger's spend in this run
  passes `--budget-usd` (default from the config).
- Writes `data/research/<group_id>.json` (the validated result + flags) and
  `data/signals.parquet`: one row per group and signal with value, found,
  rationale, evidence (list), flags. WP3 scores from this table.

## Config changes

Optional, with defaults, so existing configs still load. Update
`config/icp.example.yaml` and `tests/test_config.py`.

    research:
      model: claude-opus-5-5     # default from the claude-api skill; author may switch after the pilot
      effort: medium
      max_searches: 5
      max_fetches: 6
      budget_usd: 60
      concurrency: 4

## CLI

- `icp-scout research [--limit N] [--group ID] [--offline] [--refresh]
  [--recordings DIR] [--budget-usd X]`. `--offline` = replay mode, fails on a
  miss. Without `--offline` it records.
- `icp-scout cost`: from the ledger, total USD, leads researched, **cost per
  lead** (mean, p50, p90), tokens and searches per lead, cache hit rate, failed
  and flagged leads.

## Tests (no network, no key)

Synthetic recordings from `fixtures/llm/make_fixtures.py` for 3 fictional
groups from `fixtures/sources/`: one clean, one where a signal isn't found, and
one whose evidence cites a URL that wasn't in the conversation.
- The same request gives the same key; changing the prompt gives a new key.
- Replay mode never builds an API client and raises `RecordingMiss` on a miss.
- The ledger computes cost from usage correctly (including cache reads and
  searches), and replayed calls are marked as such.
- The schema is built from the config's signals; a config with another signal set
  works.
- Validation: missing signal, value out of range, `value > 0` without evidence,
  unseen URL -> flagged.
- `pause_turn` is resumed (recorded as two calls).
- `icp-scout research --offline` end to end on fixtures writes
  `signals.parquet`, and `icp-scout cost` prints a cost per lead.

`ruff check .` and `pytest` green.

## Order and time

| Step | Budget |
|---|---|
| `llm.py`: recording, replay, ledger, prices | 1.25h |
| Agent: prompt, tools, schema, loop, checks | 1.5h |
| Runner, outputs, CLI (`research`, `cost`) | 0.75h |
| Synthetic recordings + tests | 1h |
| Cleanup, PR, build log | 0.5h |

If time runs short: drop the parallelism and the retry on validation
failure, and say so in the PR.

## Author acceptance (local, after the PR)

1. `ANTHROPIC_API_KEY` in `.env`; add a `research:` block to `private/icp.yaml`.
2. **Pilot on 5 leads**, including both reference customers:
   `ICP_SCOUT_CONFIG=private/icp.yaml icp-scout research --limit 5 --recordings private/llm`.
   Read the evidence: are the quotes real, are the translations right, is it the
   right company? Then `icp-scout cost`.
3. Decide model and effort from the pilot's cost per lead and evidence quality
   (a cheaper model is a config change; recordings are per model).
4. Full run over the shortlist with a budget; note the cost per lead and the
   failed/flagged counts in `private/` for the deck.
5. `icp-scout research --offline --recordings private/llm` replays with no key.
   Run the leak check.

## After the pilot: a second backend (2026-09-29)

The pilot's API runs are the cost evidence. The full run goes through the
author's Claude subscription instead, so it spends no API money:
`research.backend: claude-code` runs each lead as one `claude -p` call
(`claude_code.py`) with Claude Code's WebSearch and WebFetch and a JSON schema
for the answer. Same prompt (tool names swapped), same schema, same checks,
same recordings and ledger. The ledger shows $0 and the CLI's list-price
estimate as `notional_usd`.

- **Guards:** the API key is stripped from the child's environment, and a run
  whose init message reports an API key source is killed before its first
  model call. The stream reports how full the 5-hour and 7-day usage windows
  are; past `max_utilization` (default 90% and 70%) no new lead starts. A
  lead cut off by a limit isn't recorded, so the next run resumes it.
- **Differences to the API run:** the CLI's WebSearch returns titles and links
  only, and its WebFetch returns a small model's reading of the page, not the
  page. The prompt asks WebFetch for verbatim passages. Search and fetch
  limits are in the prompt only; the CLI doesn't enforce them.
- **Rubric change from the pilot:** a plain contact form counts 0.5 for tech
  maturity, and only a quote form that asks about the project, or a simulator,
  counts 1. Almost every site has a contact form, so counting it doesn't tell
  leads apart.

## Assumptions to state on the slides

- Signals come from public web pages at research time; no page, no signal
  (scored 0, shown as "not found", not as "weak").
- Cost per lead is measured, from the ledger, not estimated.
- Evidence URLs are checked against what the agent actually retrieved;
  quotes are not re-verified against the page text.
