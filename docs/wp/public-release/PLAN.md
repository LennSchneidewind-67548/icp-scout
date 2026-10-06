# Public release: README, case study, LinkedIn, going public

Planned 2026-10-06, after the presentation. Two phases (P1, P2). Budget: not
set by the author; estimate about 2.5 h of author time (picks, reviews, the
build-log gaps, LinkedIn), the rest agent time.

**Done when:** the repo is public. A visitor who has never heard of the case
sees, on the README, what the tool does, a pipeline image and two demo
screenshots, the design choices with links to the ADRs, a run-it section that
works from a fresh clone with no API key, and how it was built with a coding
agent. `docs/case-study.md` tells the story as general lessons.
`docs/README.md` indexes the docs. The repo has topics, a CI badge and a
social preview image. The leak check passed over every ref, PR refs included,
and over the PR and issue text, before the flip. The LinkedIn Project entry
text and the post draft sit in `private/linkedin/`. The entry goes live after
the flip; the post waits until the hiring process ends.

## Context

icp-scout was built in about 20 hours as a take-home case for a GTM
engineering role. The case has now been presented. The repo was designed
from the first commit to go public afterwards (ADR 0003, `docs/plan.md`
"After the presentation"). Case material never touched git, and the leak
check guards the whole history. What's missing is the public face: the
README still says only WP1 works, there's no visual, the docs have no entry
point, and a few docs read as if the case were still running.

The second goal is LinkedIn: a Project entry that points at the repo now, and
a post, held for later, that offers the approach as a reusable way to do ICP
research, not as a case report. Both need a visual that shows the pipeline and
the demo, without a single case-company string or a real company's score.

## Decisions

Locked by the author (interview, 2026-10-06). Later agents treat these as fixed.

- **Repo contents:** (1) `README.md` rewritten: the full pipeline, a visual,
  the design choices (ADRs), how to run it, how it was built with a coding
  agent (`docs/build-log.md`). (2) `docs/case-study.md`, a public write-up:
  problem, approach, general lessons, what I'd do next. (3) Repo hygiene:
  GitHub description, topics, a docs index, a CI badge. No hosted demo.
- **Framing:** "built as a take-home case for a GTM engineering role". The
  case company is never named (ADR 0003). The fictional vendor in
  `config/icp.example.yaml` stays.
- **History:** keep the git history. Run `bash scripts/leak-check.sh` over all
  of it, then make the repo public. The flip
  (`gh repo edit --visibility public --accept-visibility-change-consequences`)
  is the last step. The coordinator confirms it with the author; no
  implementer runs it.
- **Hiring process:** still open, but not confidential. The LinkedIn Project
  entry goes out now (that is, once the repo is public). The LinkedIn post is
  drafted, framed as a reusable framework ("how I'd approach ICP research"),
  and opens with the problem and an insight, not with "excited to share". It
  is held until the process ends.
- **LinkedIn outputs:** the Project entry text (title, a 2-3 line
  description, skills, repo link), the post draft, and a visual (a
  pipeline/scoring image and a demo screenshot). The texts live in
  `private/linkedin/` and are never committed. The visual is committed under
  `docs/assets/` and also used in the README.
- **Coordinator assumptions, kept unless the author objects:** screenshots
  and visuals come from the demo running on the example config and synthetic
  data, never from `private/`. The public write-up uses general lessons, not
  case research. The CLAUDE.md rules apply to every part (leak check, no case
  strings, a `docs/build-log.md` entry per session).

The author's picks on the open visual decisions and the "Needs you" items
(2026-10-06). Also fixed.

- **V1, pipeline image style:** the demo's theme. The tokens come from
  `.streamlit/config.toml`: background `#FDFDFB`, ink `#1B1D20`, zinc greys
  (`#52525B`, `#A1A1AA`, borders `#E4E4E7`), one orange accent `#E04E1B` used
  sparingly, Geist. The author chose this knowing the theme was derived from
  the case vendor's brand (see Risks).
- **V2, pipeline image content:** one 2:1 image. Top: the six stages left to
  right, each with a 3-5 word note and an "LLM" or "no LLM" mark. Bottom: the
  scoring strip (four signals × weights → `1 + 9 × weighted mean` → tiers
  A/B/C). No counts.
- **V3, demo screens:** two, the Queue with a lead open and the Market page
  (map and funnel). Both go in the README; LinkedIn uses the Queue one next to
  the pipeline image.
- **V4, README opening:** the pitch first, then the framing as an italic note
  under the pipeline image (texts in Architecture 4).
- **V5, case study voice:** first person, past tense, plain and short (the
  build log's tone), about 1,200 words, lessons as bold lead-ins.
- **V6, LinkedIn Project entry title:** "icp-scout: AI-assisted ICP scoring
  for GTM teams" (the author's own wording, none of the drafted options).
- **N1, demo data:** the synthetic example dataset (Architecture 1), about
  300 lines with its test.
- **N2, numbers in public texts:** process numbers only (hours, agent
  sessions, cost per researched lead, test count). No market or score numbers
  from the case run. Applies to the README, the case study and LinkedIn.
- **N3, merged remote branches:** delete them before the flip.
- **N4, the build log's open lines:** the coordinator asks the author for each
  "author decided / caught" gap in P2; author times are estimated from session
  timestamps as in PR #10.

## Architecture

### 1. A synthetic example dataset for the demo (`fixtures/demo/make_demo.py`)

Picked by the author (N1). The committed fixtures are too thin to
screenshot. `make_fixtures.market` on `fixtures/sources/` gives 34 groups, 9
in segment and 3 researched: a near-empty map and a three-row queue. So P1
adds a generator that writes a full-size, clearly fictional `data/` directory
the existing app reads unchanged:

- `python fixtures/demo/make_demo.py [out_dir]`, default `data/example/`
  (`data/` is gitignored, and a subdirectory never overwrites the author's case
  files in `data/`). Seeded, so the output and the screenshots are
  reproducible. It lives in `fixtures/`, not `src/`, because it builds on
  `fixtures/llm/make_fixtures.py`, which imports `tests/conftest.py`.
- **Start from the real fixture pipeline:** `make_fixtures.market(out)`, then
  `research.run(icp, out, mode="replay", recordings_dir=fixtures/llm,
  group_ids=make_fixtures.GROUPS)`. The three recorded leads (Brise Marine
  Energies, Vallon Thermique, Cap Horizon Solaire) keep their real recorded
  transcripts, so the research replay works on them.
- **Add synthetic groups:** about 6,000 market groups placed around ~40 French
  city centres with jitter (lat/lon, `region` codes that `insights.REGIONS_FR`
  knows), headcount bands, product lines and pre-scores. About 600 are in
  segment and 175 are researched (`prefilter.shortlist_size` in the example
  config). Synthetic `signals.parquet` rows use the same columns as
  `research.run` writes. Values are on the 0/0.25/0.5/0.75/1 scale, loosely
  correlated with the pre-score so the insight charts look plausible. Every
  piece of evidence is a templated French quote with `quote_en` next to it and
  a URL on an `.example` domain. Names come from invented word lists (the
  fixtures' style), and every website is `.example`. Then `regrade/`,
  `research/`, `ledger.jsonl`, a `funnel.json` with counts consistent with the
  market, and `companies.parquet` for `insights.load`.
- **Then the real code:** `score.run(icp, out)` and `insights.run(icp, out)`.
  The scores come from the rubric, as always (ADR 0002). No model call, no
  network, no new recording.
- **Run it:**
  `ICP_SCOUT_CONFIG=config/icp.example.yaml ICP_SCOUT_DATA=data/example ICP_SCOUT_RECORDINGS=fixtures/llm streamlit run app/streamlit_app.py`.
  This is also the README's "try the demo" path. All three variables are set
  explicitly, because `demo.load_env` only fills unset `ICP_SCOUT_*` values
  from `.env`, and the author's `.env` may point at `private/`.
- **Test** (`tests/test_example_data.py`): the generator at a small size
  (a `n_groups` argument) into `tmp_path`. `demo.load` succeeds, `insights.run`
  writes the six specs, the three recorded leads have a replay
  (`demo.replay_steps`), every URL is on `.example`, and the queue holds 50
  leads at full size.

### 2. A deep link to an open lead (`app/streamlit_app.py`)

The best screenshot is the Queue page with a lead open (score breakdown and
quoted evidence). Today that view needs a row click, and headless Chrome
can't click. `queue_page` reads `st.query_params.get("lead")`. If that
group is in the table, the lead pane opens on it, as a row click would. One
`AppTest` in `tests/test_demo.py` covers it. Nothing changes without the
parameter.

### 3. The visuals (`docs/assets/`)

- `docs/assets/pipeline.png`: the pipeline and scoring image, 1280×640 at 2x
  (2560×1280). That is GitHub's social-preview size and close to LinkedIn's
  1200×627, so one image serves the README, the repo's social preview and
  LinkedIn. The source is `docs/assets/src/pipeline.html`, a static page with
  the Geist fonts from `app/static/`. It is rendered with headless Chrome
  (`--window-size=1280,640 --force-device-scale-factor=2 --screenshot`). No new
  dependency, and the image can be re-rendered after a wording change.
  - **Style (V1):** the demo's theme, with the tokens copied from
    `.streamlit/config.toml`: background `#FDFDFB`, ink `#1B1D20` for text,
    zinc greys `#52525B` (secondary text), `#A1A1AA` (marks, arrows) and
    `#E4E4E7` (borders), one accent `#E04E1B` used sparingly (the "LLM" marks
    and the score formula), Geist and Geist Mono from `app/static/`. It
    matches the screenshots, so the README and LinkedIn look like one piece.
  - **Content (V2):** top row, the six stages left to right: open registries
    → market table → pre-filter → agent research → rubric score → SDR
    hand-off. Each has a 3-5 word note and an "LLM" or "no LLM" mark. Bottom
    strip, the scoring: four signals × weights → `1 + 9 × weighted mean` →
    tiers A/B/C. No counts. The signal names and the tier cut-offs come from
    `config/icp.example.yaml`, so nothing is case-specific.
- `docs/assets/demo-queue.png` (Queue with a lead open, via `?lead=`: the
  score breakdown and a French quote with its English) and
  `docs/assets/demo-market.png` (map and funnel), per V3: the example build
  from section 1 on port 8502 (8501 stays free for the author's case review
  build), 1440×900 at 2x, each ≤ 1 MB. Both go in the README; LinkedIn uses
  `demo-queue.png` next to the pipeline image.
- **Check before committing any image:** the vendor shown is the example
  config's fictional vendor, the URLs are `.example`, and no name from
  `private/` appears. Run the leak check with the real terms in the main
  checkout.

### 4. The README (`README.md`)

Order (V4: pitch first, framing under the image): name, the one-line pitch,
the CI badge
(`https://github.com/LennSchneidewind-67548/icp-scout/actions/workflows/ci.yml/badge.svg`),
`docs/assets/pipeline.png`, the framing as an italic note under the image,
then the sections below. The two texts:

- Pitch: "icp-scout maps a whole market from open data, researches a
  shortlist with an AI agent, scores it with a rubric you can read, and hands
  SDRs a ranked queue."
- Framing note (italic): "*Built as a take-home case for a GTM engineering
  role. The case company stays private; the example config targets a
  fictional vendor.*"

The sections:

1. **What it does:** the six stages, one line each, with what each costs (the
   pre-filter makes no LLM call, the agent runs only on the shortlist).
2. **The demo:** the two screenshots (V3) with a one-line caption each, marked
   synthetic data and fictional companies. Then what to try: open a lead,
   step through the replay, move a weight and watch the queue re-rank.
3. **Design choices:** ADRs 0001-0004 as one bullet each with the link, plus
   "it states what it costs" and "it drafts, people send". The ADR 0001
   limit (the approach needs a comparable open registry) goes here, as the
   ADR asks.
4. **Run it:** install (macOS/Linux activate path first, Windows second),
   `pytest`, the example demo from section 1, then the real pipeline
   (`icp-scout source`, `research`, `score`, `insights`, `export`) with what
   each writes and what needs an API key or the `claude` CLI. Pointing it at
   your own ICP is a copy of `config/icp.example.yaml`.
5. **How it was built:** a Claude Code workflow where the author makes the
   calls. Link `docs/build-log.md` (sessions, what the agent proposed, what the
   author decided or caught), the WP plans, and the ADR 0003 leak check that
   kept the case company out of git. Process numbers only (N2): hours, agent
  sessions, cost per researched lead, test count; no market or score numbers
  from the case run.
6. **Repo map** (short) and a link to `docs/README.md`.
7. **License:** MIT.

### 5. The case study (`docs/case-study.md`)

First person, past tense, plain and short in the build log's tone, about
1,200 words, each lesson as a bold lead-in (V5). Process numbers only: hours,
agent sessions, cost per researched lead, test count; no market or score
numbers from the case run (N2). Sections: **The problem** (the brief in general terms, as
`docs/requirements.md` states it), **The approach** (the whole market from
open data, then the agent on a shortlist, then the rubric, then the hand-off;
link the ADRs), **What I learned** (general lessons), **What I'd do next**,
and **How it was built**. Candidate lessons, all already recorded in committed
docs, are listed below. The implementer drafts them, and the author cuts or
reorders in review.

- Start from the whole market, not a list. Completeness turns the list into
  market insight, and agent money goes only to a shortlist (ADR 0001).
- Let the model extract and the rubric score. Evidence makes a score
  checkable, and weights become a business conversation that re-ranks live
  (ADR 0002).
- Real company structure matters: rolling sister companies up to groups
  changed who qualifies on size (WP1).
- Small firms have a thin web presence, so research cost is driven by search
  and fetches more than by the model (WP0, WP2).
- A rubric saturates: when the top leads max every signal, weights can't
  separate them. Finer grades applied to the recorded evidence fix the cut
  without new research (WP3, WP5 finding).
- Record every model answer: the demo runs offline, CI needs no key,
  re-scoring is free, and the replay shows the agent's work (WP2, WP5).
- Building with an agent: what it caught, what the author caught (from the
  build log).

What I'd do next: the n8n workflow (out of scope in `docs/requirements.md`),
CRM sync beyond the CSV import, triggers that re-score a lead (a new
certification, new job posts), a small hand-labelled accuracy set, and
registries in other countries.

### 6. Docs that read oddly in public

- `docs/README.md` (new): the index. Requirements, plan, the WP plans, ADRs,
  build log, case study, this plan, with one line each.
- `CLAUDE.md`: keep it; it is evidence of the agent workflow. Its first
  paragraph moves to past tense ("was built as a case study"), and one line
  says `private/` is not in the repo. Everything else stays: the rules and the
  Pipeline section are what an agent working in the repo still needs.
- `docs/requirements.md` and `docs/plan.md`: they stay as the kickoff record.
  One italic note under each title: "Written for the case, before the
  presentation; `private/` is not in the public repo." `docs/plan.md` "After
  the presentation" links to this plan.
- `docs/wp/*.md`: unchanged (historical; their `private/` steps were the
  author's own runs).

### 7. Going public (P2: checks, metadata, LinkedIn, the flip)

- **Leak sweep, history:** in the main checkout (where
  `private/leak-terms.txt` exists), fetch every PR head first:
  `git fetch origin '+refs/pull/*/head:refs/pull-heads/*'`. Then run
  `bash scripts/leak-check.sh`. PR refs become public with the repo and stay
  even after a branch is deleted, and `git rev-list --all` only sees them once
  fetched.
- **Leak sweep, GitHub text:** new `scripts/leak-check-github.sh`. It runs
  the same terms over PR titles and bodies, PR review comments, issue
  comments and commit comments, through `gh api --paginate`. It prints only PR
  and issue numbers, never the text, like `leak-check.sh`. It is run once by
  hand, not in CI.
- **Before the flip:** delete the merged remote branches (N3, decided by the
  author; 10 at planning time, e.g. `wp1-sourcing`). The coordinator lists
  them with `git branch -r --merged origin/main` and runs the deletion; their
  commits are in `main`, and PR refs keep the history visible. Set topics
  with `gh repo edit --add-topic` (ruled list below). Upload
  `docs/assets/pipeline.png` as the social preview (web UI only: Settings →
  Social preview). Close out the build log: the Totals row (it still says
  "WP7 is left"), author times estimated from session timestamps as in PR
  #10, and the "author decided / caught" gaps, which the coordinator asks the
  author for one by one, a few lines each (N4). No gap is filled with a guess
  or with "not recorded".
- **LinkedIn texts** in `private/linkedin/` (main checkout, never
  committed): `project-entry.md` (the title "icp-scout: AI-assisted ICP
  scoring for GTM teams" (V6), the 2-3 line description, skills, repo link)
  and `post-draft.md` (2-3 hooks, one body, image notes: `pipeline.png` plus
  `demo-queue.png`). Process numbers only (N2). The hooks are marked so the
  author can pick there.
- **The flip:** the coordinator asks the author, then runs
  `gh repo edit --visibility public --accept-visibility-change-consequences`.
- **After the flip:** in a logged-out browser window, the README renders,
  the badge is green, the images load, `docs/case-study.md` renders, and a
  pasted repo link shows the social preview (LinkedIn Post Inspector). CI
  runs once on the public repo, and the leak-check job passes with the secret.
  Then the author adds the Project entry on LinkedIn. The post stays in
  `private/linkedin/` until the process ends.

## Phases

| Phase | Goal | Depends on | Device check |
|---|---|---|---|
| P1 | The repo's public face: the example dataset and `?lead=` link, the pipeline image and two demo screenshots, the new README with badge, `docs/case-study.md`, `docs/README.md`, past-tense notes in CLAUDE.md, requirements and plan. The author can open the README on the PR branch on GitHub and the example demo locally. | Nothing open (V1-V5, N1, N2 picked) | Browser: the example demo on :8502, and the README and case study rendered on GitHub (branch view) |
| P2 | Go public: `scripts/leak-check-github.sh`, the full leak sweep (PR refs included), branch cleanup, topics and social preview, the build log closed out, the LinkedIn texts in `private/linkedin/`, then the flip (coordinator, with the author) and the logged-out checks. The author can add the Project entry. | P1 merged; the author's answers to the build-log gaps (N4) and the go-ahead for the flip | Browser: the logged-out repo view after the flip; LinkedIn Post Inspector (author) |

P1 likely splits into four parts, run in order: the example dataset and deep
link (logic), the visuals (iterating), the README with the docs index and
touch-ups, and the case study. P2 is one PR (the script and the build log);
the rest of P2 is checks and steps outside git.

## Open visual decisions

None. The author picked V1-V6 on 2026-10-06; the picks are under Decisions.
The only choice left is the LinkedIn post's hook, picked in
`private/linkedin/post-draft.md` in P2.

## Needs you

None. N1-N4 are answered under Decisions.

## Rulings

- Ruling: the generator writes to `data/example/` and lives in `fixtures/demo/` — `data/` is gitignored and a subdirectory can't overwrite the case files; `fixtures/` because it reuses `make_fixtures.py`, which imports `tests/conftest.py` — cost if wrong: a moved script and one README line.
- Ruling: `?lead=<group_id>` deep link in the Queue page — headless Chrome can't click a row, and no screenshot tool may be added — cost if wrong: about 20 lines to remove.
- Ruling: images are rendered from an HTML source with the existing headless Chrome — no new dependency, re-renderable after wording changes — cost if wrong: redraw by hand.
- Ruling: one 1280×640 (2x) pipeline image for README, social preview and LinkedIn — GitHub's preview size, near LinkedIn's — cost if wrong: one extra crop.
- Ruling: the example build runs on port 8502 with all three `ICP_SCOUT_*` variables set — keeps the author's case review build on 8501 and stops `.env` from pulling in `private/` — cost if wrong: none.
- Ruling: CLAUDE.md, requirements and plan get a past-tense note, not a rewrite; WP plans stay unchanged — they are the honest record, and readers of a case repo expect it — cost if wrong: a few lines.
- Ruling: PR heads are fetched before the leak check, and PR and issue text gets its own check script — both become public with the repo, and `leak-check.sh` sees neither — cost if wrong: a few minutes.
- Ruling: topics `gtm-engineering, lead-scoring, sales-intelligence, icp, open-data, ai-agents, llm, claude, streamlit, python` — the role, the method and the stack — cost if wrong: one `gh` command.
- Ruling: the pipeline image takes its signal names, weights and tier cut-offs from `config/icp.example.yaml`, and its colours from `.streamlit/config.toml` — one source for each, and nothing case-specific can slip in — cost if wrong: one re-render.
- Ruling: README install shows macOS/Linux first, Windows second — the author now works on macOS, and visitors mostly use POSIX shells — cost if wrong: none.
- Ruling: the GitHub description stays as it is — it already states the pipeline in one line — cost if wrong: one `gh` command.

## Risks

- **A real company's name in the synthetic data.** Invented names can match
  a real firm by chance, and a screenshot would then show it with a made-up
  score. Names come from invented word lists, every URL is `.example`, and the
  captions say "synthetic data, fictional companies".
- **`.env` pulls the case data into a screenshot.** All three variables are
  set explicitly (Architecture 1). Before committing, check that the image
  shows the example vendor.
- **The demo's look echoes the case vendor's brand.** The WP7 deck took one
  accent and a font close to the vendor's, and the demo theme followed it.
  The author chose this theme for the pipeline image anyway (V1), knowing
  it. The theme is already in history, so the risk is only that the shared
  images are recognisable. Accepted; no part changes the palette.
- **The leak check only warns in a worktree** (no `private/`). Every part
  runs the real check in the main checkout before its PR merges, or relies on
  CI with the secret.
- **Things outside git go public too:** PR text, review comments and Actions
  logs. The GitHub-text check covers the first two; `leak-check.sh` prints
  only hashes and paths, so the logs are safe.
- **The Project entry links a private repo** if it goes out before the flip.
  The order in P2 prevents that.

## Deviations

### Deviations found while building P1

- [Rule 1] Part A: the generator's funnel reasons that carry numbers ("dropped 1 expired",
  "+2 with NAF ...", "41 companies rolled up") are rewritten with the new counts instead of
  kept word for word, so no stage text contradicts its count. Ids, labels and order are kept.
- [Rule 2] Part A: the 34 real fixture groups are moved onto real French cities (the three
  recorded leads where their recordings say: Quimper, Grenoble, Avignon). The fixtures
  place them at one fake point, which would show as a clump on the map.
- [Rule 2] Part A: the test that every evidence URL ends in `.example` also allows the
  public registry host that the recorded Vallon lead cites; that recording is fixed.
- [Rule 3] Part A: pseudo-word names draw two or three syllables; two alone give 520 names,
  too few for 6,000 groups.
- [Rule 3] Part B: headless Chrome's `--screenshot` with `--virtual-time-budget` captures
  the Streamlit loading skeleton (a blank page): the app renders over a websocket. The two
  demo screenshots are taken through the DevTools protocol instead (`docs/assets/src/shoot.py`,
  wait 14 s, then `Page.captureScreenshot`), same size and scale, no new dependency. The
  queue shot does not scroll the lead pane: the name, score, tier and breakdown fit, but
  the French quote's text falls just below the fold at 1440x900 (its "As quoted / English"
  header shows); a scroll that shows the quote hides the name.

## Deviations found while building P2

- [Rule 2] The release Totals row's date cell reads "to the flip" instead of a date, so
  the row has the planned two TODO cells and nothing else.
- [Rule 2] The estimated author times use the session files' real prompts, which are
  sparse (the coordinator session holds 11). The windows are tied to entries through PR
  merge times (#14 to #21), so the 2026-10-06 times are rough, from ~5 to ~25 min.
- [Rule 2] The case author time is ~14.5 h: the entries to 2026-10-03 add up to ~11.8 h,
  plus five 30-minute estimates from the author for 2026-10-03 and 2026-10-04.
