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
| TODO | 8 | ~$2.04 | 1 of 8 (WP0); WP1 and WP2 merged, pilot done |

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

---

## 2026-09-29 · WP1: sourcing · `remote`

**Author time:** TODO

**Asked for:** implement `docs/wp/wp1-sourcing.md`, following its session rules.
Built against the example config and synthetic fixtures only; `private/` was
not visible.

**The agent checked live before building:** both APIs reachable from the
sandbox (the register through a flaky proxy). The register refuses
`page * per_page` above 10,000; the person filters (`nom_personne`,
`prenoms_personne`, `date_naissance_personne_min/max`) exist and work, and
unknown parameters get a 400; officer names come as `"NAME (USAGE NAME)"`.

**Caught while building:**
- httpx drops a URL's own query string when `params` is passed, so following
  the registry's `next` link silently lost the filter and cursor and looped
  until the process was killed. Now the cursor is passed as params, and a
  repeated cursor raises.
- A person search ending on 29 February of a non-leap year got a 400.
- Physical-person auditors appear among officers too, not only audit firms;
  both are excluded from linking.
- A company whose RGE qualification lapsed can come back through the second
  source (installer NAF code, energy word in the name). Kept, with a test.
- The remote image's `python3` is 3.11; the project needs 3.12, so the setup
  hook could not have installed it. It now builds `.venv` with python3.12.

**The agent decided, for the author to review in the PR:**
- Manager key = surname + *first* given name + birth month (the register
  lists first names inconsistently).
- Manager expansion only adds construction trades (NAF 43.*) and holdings
  (64.20Z, 70.10Z): a manager's property or restaurant company would
  inflate the group's headcount.
- `near_band` as specified: with a 30-300 band, half the width is 135, so
  every smaller company is "near". On a live sample of 500 companies, near-band
  groups outnumbered in-band ones nearly two to one. At full scale they should not reach
  the shortlist, but the "in or near the segment" funnel stage is inflated.
- The pre-score saturates: about 2.4% of companies score 1.0, so the shortlist
  is decided by the tie-break (largest group first).
- One in three active certified companies has no headcount band (`NN`,
  mostly non-employers) and drops out as "headcount unknown".

**Output:** `icp-scout source` / `icp-scout funnel`, `group.py`, `prefilter.py`,
`funnel.py`, a cached rate-limited HTTP client, new optional config keys,
synthetic fixtures with their generator, 33 tests. The full pull was not run
here (about 2 lookups/s through the sandbox proxy); it is left for the author.
The sandbox clone had no git remote. The author gave the repository, the agent
pushed the branch; the sandbox has no GitHub CLI, so the author opens the PR
from the drafted description.

---

## 2026-09-29 · WP2 plan · `local`

**Author time:** TODO

**Asked for:** a plan for WP2 (agent research) in `docs/`, and how to run
its implementation in a remote session.

**The agent proposed:** `docs/wp/wp2-research.md`, in the same shape as WP1:
one door to the model (`llm.py`) that records, replays and writes a cost
ledger; an agent with web search and web fetch that ends by calling a strict
`record_signals` tool whose schema comes from the config; checks in code
(evidence required for any value above 0, every evidence URL must have been
seen in the conversation); `icp-scout research` and `icp-scout cost`; a
budget guard. The remote session builds against synthetic recordings and needs
no API key; the live pilot (5 leads) and the full run are the author's, locally.

**Caught while planning:** recordings of real companies are case content, so
they can't live under the committed `fixtures/llm/`. The recordings directory
is now a setting: `fixtures/llm/` for synthetic ones, `private/llm/` for the case.

**Left for the author:** model and effort after the pilot (default from the
claude-api skill: the current Opus at medium effort), and the budget.

**Output:** `docs/wp/wp2-research.md`, WP2 linked from `docs/plan.md`.

---

## 2026-09-29 · WP2 agent research · `local`

**Author time:** TODO

**Asked for:** implement `docs/wp/wp2-research.md`. It was planned as a
`remote` session; Anthropic was having an incident, so it ran locally
instead, with the same rules (synthetic data only, no API key, branch + PR).

**The agent built, per the plan:** `llm.py` (record / replay / refresh,
sha256 request keys, atomic recordings, a cost ledger, prices from the pricing
page), the agent (`enrich/agent.py`: web search + web fetch + a strict
`record_signals` tool built from the config's signals), the runner
(`research.py`: thread pool, resumable, budget guard, `signals.parquet`),
`icp-scout research` / `icp-scout cost`, synthetic recordings made by
`fixtures/llm/make_fixtures.py` through the agent itself, 19 new tests.

**The agent decided, for the author to review in the PR:**
- Structured outputs vs. a strict tool: the skill documents structured
  outputs as incompatible with citations, and web search answers carry
  citations, so it kept the strict `record_signals` tool with `tool_choice: auto`.
- Only schema failures (a missing signal, a value out of range) get the one
  retry and then fail the lead. A value without evidence and an unseen URL are
  flagged but not retried: re-asking costs a call, and a flag is enough for
  the SDR to check.
- Server-side refusal fallback on by default (`fallbacks: "default"`), as the
  skill recommends. A fallback answer is priced at the model the response names.
- `icp-scout cost` counts each recording once, at its recorded cost, so a replay
  doesn't double the cost per lead. Live spend is shown on its own line.
- The CLI now reads `.env` (the plan puts the API key there).

**Caught during the session:**
- The author's `.env` points `ICP_SCOUT_CONFIG` at the private case config.
  Once the CLI read `.env`, a test ran against it and missed its recordings.
  Tests now switch `.env` loading off.
- Recording the case run into the committed `fixtures/llm/` by mistake would
  leak case content. `research` now refuses to record there with any config
  but the example.

**Not verified:** no live call was made (no key in the session). A dry run
through the real SDK with a mock transport showed the request is built as
intended. Whether the API accepts the strict schema, and what a lead really
costs, is for the author's 5-lead pilot.

**Output:** branch `wp2-research`, PR opened.

---

## 2026-09-29 · WP2 pilot · `local`

**Author time:** TODO

**Asked for:** merge the WP2 PR and run the pilot. Then, from the author: a
$15 cap on API spend for the whole project, $3 for the pilot, and "if there's
any way to cheaply compare the output of both configs, run both and put the
findings in the presentation".

**The author caught:** the agent had written a $60 budget into the private
config that was never agreed. It is now $3, and the agent records spend
figures as the author's decision (memory).

**The agent proposed, the author chose:** ways to cut cost (the Pro plan
instead of the API, a cheaper model, the top 50 only, fewer and shorter
pages, lower effort, batching). For the pilot: two configs that differ only
in the model (Sonnet 5.5 vs Opus 5.5), on the same 5 leads, compared in code
(`icp-scout compare`) with no LLM judge.

**Found by running it:**
- The full sourcing pull ran for the first time (about 1.5h, 21k register
  lookups). **Neither reference customer made the shortlist.** One was below
  the pre-score cut: no website in the registry, so growth and tech maturity
  score 0. The other isn't in either source. The author chose to research
  both anyway: `--group` now accepts any group in the market, and a new
  `market.extra_sirens` adds named companies to sourcing.
- **The first Sonnet run was invalid.** Every web tool call failed with
  `invalid_tool_input`: the model called the `_20260209` (dynamic filtering)
  tools with code-execution-style input. The answers passed validation as
  honest "not found" answers; "0 searches" in the cost report gave it away.
  Four diagnostic calls isolated it. The agent now uses the basic tool
  versions, which were also cheaper in those tests.
- A live response with search results holds datetimes, and `to_dict()` failed
  to serialize it after the call was paid. Fixed with `mode="json"`.

**Result (details in `private/pilot/findings.md`):** Opus costs 3.7x Sonnet per
lead, uses its search and fetch allowance, and finds more (a second website,
expired job ads, a group-level headcount). Sonnet stops at the first page. Both
rate both reference customers highly; Opus matched the author's hand score
for one of them exactly. One disagreement comes from an ambiguous rubric
definition (does a contact form count as a lead form?).

**Output:** PR #3 (page-size cap, `icp-scout compare`, `extra_sirens`,
off-shortlist `--group`, basic web tools, JSON-mode serialization). Pilot
spend about $2.04 of the $3.

**Left for the author:** model and scope for the full run within about $12.96
(measured: Sonnet on all 175 about $10.50, Opus on the top 50 about $11); the
rubric definition of a lead form.

---

## 2026-09-29 · WP2 full run on the subscription · `local`

**Author time:** TODO

**Asked for:** the Opus config for the full run, but on the author's Pro plan
instead of the API, with the pilot as the only API cost evidence. Merge PR #3.
The agent should decide the open rubric question itself.

**The agent decided:** a plain contact form counts 0.5 for tech maturity; a
quote form that asks about the project, or a simulator, counts 1. Nearly every
site has a contact form, so counting it doesn't tell leads apart.

**The agent built:** a `claude-code` research backend: one `claude -p` call
per lead, with the same prompt, schema, checks, recordings and ledger. Guards:
the API key never reaches the CLI, and a run that reports an API key source is
killed before its first model call.

**The agent caught:** the subscription's 7-day usage window resets on the
presentation morning, so a run that used it up would leave no Claude for the
remaining work packages. The guard has a cap per window: 90% of the 5-hour
window, 70% of the 7-day window. It also found that the CLI's web search
returns only links and its fetch returns a summary, so the prompt asks for
verbatim passages. Search and fetch limits went back to 5/6, since the pilot's
3/3 was only there to save API money.

**Result:** 52 leads (top 50 + both references), 0 failed, 1 flagged, $0 of
API money (list-price estimate $8.91). Weekly usage went from 38% to 44%.
Against the API pilot, the only value changes on tech maturity come from the
new rule. The scores barely separate inside the top 50 (41 A, 11 B, 0 C);
that's an input for WP3. Details in `private/pilot/findings.md`.

**Output:** branch `wp2-claude-code`, PR.

---

## 2026-09-30 · WP2 wide run on the subscription · `local`

**Author time:** TODO

**Asked for:** research the rest of the 175-lead shortlist on the Pro plan,
using up to 90% of a fresh 5-hour window, with the caps unchanged and no API
use. The agent's score, not the pre-score, should pick the top 50. Then a first
re-rank, analysis only.

**The agent did:** checked the caps (five_hour 0.9, seven_day 0.7) and ran the
research in the background. It watched the log for failures instead of polling,
because this session shares the same window. It then scored every researched
lead with the rubric weights in a scratch script. `score.py` is still only a
docstring, so the pipeline is unchanged.

**The agent caught:** `icp-scout cost` reports 120 leads where the run reports
118 of 175. The difference is the two references off the shortlist, not a
double count. The guard stopped at 92%, not 90%, because leads already
running finish after the cap is hit.

**Result:** 118 of 175 researched (66 new), 0 failed, 1 flagged (the same one
as before), $0 of API money. The 5-hour window went from 5% to 92%, the 7-day
window from 45% to 52%. 57 leads are left, about one more 5-hour window. In the
re-rank, 21 of the agent's top 50 had pre-rank 51-118, and the pre-score barely
predicts the agent's score (Spearman -0.14). One reference ranks 17, the other
79, outside the top 50. The rubric saturates: 11 distinct scores, 86 of 120 in
tier A, 53 leads at 9.55 or above for 50 slots, so a tie-break decides the cut.
This goes into WP3. Details in `private/pilot/findings.md`.

**Output:** `data/` and `private/` updated (not committed); this entry.

---

## 2026-09-30 · WP2 finished: last leads and full re-rank · `local`

**Author time:** TODO

**Asked for:** research the rest of the shortlist and say what comes next.

**The agent did:** ran the last 5 leads after the 5-hour window reset, with
the caps unchanged; the rest replayed from recordings. It then reran the
previous session's scratch re-rank on the full set. `score.py` is still only a
docstring.

**The agent caught:** the run logs don't record plan usage, so the usage for
this batch is unmeasured rather than estimated.

**Result:** 175 of 175 researched (plus both references), 0 failed, 1 flagged
(unchanged), $0 of API money, list-price estimate $0.171 per lead. In the
re-rank, 22 of the agent's top 50 had pre-rank 51-175, 13 of them from the
last 57 leads. Spearman between pre-rank and score is -0.07. The rubric
saturates further: 30 leads at the maximum, 73 at or near it for 50 slots,
so the pre-rank tie-break decides 20 places. One reference ranks 113th.
Details in `private/pilot/findings.md`.

**Output:** `data/` and `private/` updated (not committed); this entry.

---

## 2026-10-01 · WP3: finer signals, score.py, the SDR queue · `local`

**Author time:** TODO

**Asked for:** merge WP2, then plan WP3 before building it; the agent was to
argue the case for references in the SDR queue.

**The agent proposed:** a written plan (`docs/wp/wp3-scoring.md`): a regrade
pass over the recorded evidence (growth on five steps, a headcount number,
a phrase per signal) and a headcount sweet spot in code. It argued for
references in the queue (strongest known fits, visible calibration) but
recommended calibration only, since they may be the vendor's customers.

**The author decided:** finer signals rather than a better tie-break; sweet
spot 60-200; references as calibration, not queued; approved the regrade run.

**The agent caught:** the signal `definition` is part of the research prompt,
so a finer growth scale there would have invalidated every WP2 recording; it
went into a new `grades` key. After the run: the scale it wrote puts undated
postings at 0.5, which cut 18 leads from growth 1, some with many roles on
their own careers page. The author decided roles on the group's own careers
page count as current; a second regrade applied it (17 leads up to 1). The
agent then caught that the first run had graded undated job-board ads as
current against its own scale; the clearer wording made the second run apply
the rule, which moved 6 leads out of the queue. The author kept the strict rule: undated
job-board postings stay non-current.

**Result:** `icp-scout regrade` and `icp-scout score`; config keys
`segment.sweet_spot`, `edge_value`, `grades`, `reference_sirens`, `queue.size`.
Two regrades of 177, $0 of API money. After the second: 56 distinct scores
(was 13), 7 queue places decided by a tie-break (was 20; 0 after the first
regrade), 96 A / 74 B / 7 C. 89 tests pass. Details in
`private/pilot/findings.md`.

**Output:** WP3 code, tests and docs on branch `wp3-scoring`; `data/` and
`private/` updated (not committed); this entry.
