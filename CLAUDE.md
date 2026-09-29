# CLAUDE.md

## What this is

A case study for a GTM engineering application, built as a general tool: source a market from open data, research a shortlist
with an agent, score it with a rubric, hand SDRs a ranked queue. The brief is
in `private/Case.md`, the role in `private/JobDescription.md`. Every decision
from the kickoff is in `docs/requirements.md`; the work packages and hour
budgets are in `docs/plan.md`.

## Rules

- **Never commit case-company content** (ADR 0003). The company name, the
  real ICP config, research, the scored list and the deck stay in `private/`.
  No company-specific strings in code, tests, fixtures, docs or commit
  messages. That includes this file. `bash scripts/leak-check.sh` checks
  all of git history against `private/leak-terms.txt`; CI runs it on every
  push with the `LEAK_TERMS` secret. Add new case-specific names to both.
- Everything specific to a vendor or market comes from the ICP config
  (`config/icp.example.yaml`, or `ICP_SCOUT_CONFIG=private/icp.yaml` for the case).
- The model never outputs the score; it extracts signals with evidence (ADR 0002).
- Every LLM answer is recorded under `fixtures/llm/` so the demo runs offline.
  Load the claude-api skill before writing `llm.py`.
- Time budget is ~20h total. Insights and the deck matter more than app polish.
- The author does not read French: every French text gets an English translation next to it.
- At the end of every session (local or remote), add an entry to
  `docs/build-log.md`: mode, what the agent proposed, what the author
  decided, rejected or caught, and the output. Leave author time as TODO.

## Commands

```sh
source .venv/Scripts/activate
pytest
icp-scout show-config
```
