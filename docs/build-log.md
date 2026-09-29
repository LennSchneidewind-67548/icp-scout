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
| TODO | 3 | $0 | 1 of 8 (WP0) |

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

**Follow-up, same session:** the author asked for a slide on the AI-assisted
workflow; the agent agreed on the condition that it shows the author's
decisions, not the tools, and set up this log. Then a CI leak check was
added: the case-specific terms are a GitHub secret and every commit and commit
message in history is checked against it, printing paths only. It was tested
both ways (passes on the real history, fails on a term that is present).

---

## 2026-09-29 · WP0: case research and rubric calibration · `local`

**Author time:** TODO

**Mode note.** Run locally on purpose: every output is case material in
`private/`. The agent pointed out that a remote session couldn't see it and
couldn't return it without committing it. Later work packages sent to remote sessions build
against the example config only.

**The agent researched:** the vendor's product, pricing model and presence
in the market, the local competitor landscape, and both reference customers
in the RGE registry and the company register. It also checked the configured
RGE domain labels (exact matches) and how often RGE lists a real website.

**What the data changed:**
- One reference is a holding. Its installer subsidiaries are each under 30
  staff, so per-company sourcing would have filtered out the best-known fit.
  → WP1 rolls sister companies up to group level before the size filter.
- The other reference isn't in the RGE registry at all (commercial-PV roots,
  newer residential brand). → WP1 gets a second source; the blind spot goes
  on the slides.
- Only 29% of target RGE companies list their own website. → The agent needs
  web search, which will drive the cost per lead.

**The agent proposed, the author decided:**
- Weights: the agent proposed 3/3/2/2 (size / mix / growth / tech). The author chose
  **3/4/2/1**: product mix is the differentiator against the PV-first competitors, and
  tech maturity is mostly unknown from outside. Both references still land in tier A.
- Group roll-up: accepted as recommended.
- Non-RGE installers: the agent recommended flagging them as a blind spot only; the
  author chose to **build a second source** (+1.5h on WP1).
- Competitor use is not a no-go; it counts as a sign of software readiness. Accepted.

**Caught:** a name search for either reference returns unrelated
same-name companies. Matching by website, manager and address was needed.

**Output:** research notes and the calibrated config (private). Signals get an
optional `definition` field (what 0 / 0.5 / 1 mean), shown to the agent in WP2.
The example config and a test were updated. The leak-term list grew from 5 to 15 terms.

---

## 2026-09-29 · WP1 plan for a remote session · `local`

**Author time:** TODO

**Asked for:** a plan for WP1 as a Markdown file under `docs/`, to be handed to
a remote session by the author. From now on, one file per WP in `docs/wp/`.

**The agent checked before planning:** both APIs live. The RGE endpoint, row
count and fields; the register's lookup by SIREN and its filtered search
(NAF code and headcount band, which makes the second source a paged query
rather than a scrape).

**Caught:** the register lists **auditors** among a company's officers, as
legal entities. Linking companies through legal-entity officers without
filtering them out would have merged unrelated companies through a shared
audit firm. The plan excludes them and requires a test for it. Also: a
website shared by many companies (a certifier's profile page) must not link
them, and name keywords must match whole words.

**The agent proposed:** group headcount as the sum of band midpoints, a
`near_band` flag, a pre-score weighted with the rubric weights, and synthetic
fixtures from the start. Open for the author's review in the PR.

**Output:** `docs/wp/wp1-sourcing.md`, linked from `docs/plan.md`.

---

## 2026-09-29 · Remote session setup · `local`

**Author time:** TODO

**Asked for:** how to hand `docs/wp/wp1-sourcing.md` to a remote session, then
the environment setup for it.

**The agent proposed:** a `SessionStart` hook in `.claude/settings.json` that
runs `scripts/remote-setup.sh` (`pip install -e ".[dev]"`, like CI) and only
does so when `CLAUDE_CODE_REMOTE=true`, so local sessions keep using `.venv`.
Kept in the repo rather than in the web environment's setup script, so it is
versioned. Network access for the two data hosts still has to be allowed in the
environment settings by the author.

**Output:** `.claude/settings.json`, `scripts/remote-setup.sh`.
