# Build log

How this project gets built: an AI-assisted workflow, with the calls made by
the author. One entry per session. The point is to record the decisions,
not the typing. What the author decided, rejected or caught matters most.

Modes: `voice-dump` (unstructured spoken context) · `interview` (agent asks,
author decides) · `local` (Claude Code on the author's machine) · `remote`
(a work package sent to a Claude remote session) · `review` (author checks
and merges agent output) · `manual` (no AI).

Keep entries free of case-company specifics (ADR 0003); those go in `private/notes.md`.

## Totals

| Author time | Agent sessions | LLM spend (pipeline) | Work packages done |
|---|---|---|---|
| TODO | 1 | $0 | 0 of 8 (WP0 started) |

---

## 2026-09-29 · Kickoff and setup · `voice-dump` → `interview` → `local`

**Author time:** TODO

**Input.** A spoken brain dump: the case, two goals (win the case, public
portfolio repo later), the idea of making it company-agnostic, and whether
to reuse code from outreach-engine.

**The agent challenged, the author decided:**
- Public repo: feasible if designed in from the first commit. The agent
  argued for going public only after the presentation, with case material
  never committed. Accepted (ADR 0003).
- Reusing outreach-engine: the agent argued against copying its code and for
  reusing its patterns, since the code is coupled to job postings. Accepted (ADR 0004).
- Over-engineering: the agent flagged that the tool must serve the insights.
  The author set a 20h budget; `docs/plan.md` cuts app polish first.

**Interview:** 4 rounds, 16 questions → `docs/requirements.md`.
Where the author diverged from the agent's recommendation:
- Declined a hand-labelled accuracy eval; cost per lead is reported, accuracy isn't.
- Left residential B2C focus out of the scoring signals.
- Chose an HTML slides deck over PowerPoint.

**Agent research:** confirmed two open data sources (ADEME RGE registry,
recherche-entreprises API) could source the whole market without
scraping, and tested both live before committing to them (ADR 0001).

**Caught in review:** the first CLAUDE.md named the case company and would
have been committed. Fixed before the first commit. Push of the CI workflow
was rejected (missing `workflow` token scope); author re-authenticated.

**Output:** repo, docs, ADRs 0001-0004, config loader with tests, CI green.
