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

## Architecture

### 1. A synthetic example dataset for the demo (`fixtures/demo/make_demo.py`)

**Default, pending decision (N1):** the committed fixtures are too thin to
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
  dependency, and the image can be re-rendered after a wording change. Its
  style and content are open (V1, V2).
- `docs/assets/demo-queue.png` (Queue with a lead open, via `?lead=`) and
  `docs/assets/demo-market.png` (map and funnel): the example build from
  section 1 on port 8502 (8501 stays free for the author's case review
  build), 1440×900 at 2x, each ≤ 1 MB. The screens are open (V3).
- **Check before committing any image:** the vendor shown is the example
  config's fictional vendor, the URLs are `.example`, and no name from
  `private/` appears. Run the leak check with the real terms in the main
  checkout.

### 4. The README (`README.md`)

Order: name, a one-line pitch and the framing line (V4), the CI badge
(`https://github.com/LennSchneidewind-67548/icp-scout/actions/workflows/ci.yml/badge.svg`),
`docs/assets/pipeline.png`, then:

1. **What it does:** the six stages, one line each, with what each costs (the
   pre-filter makes no LLM call, the agent runs only on the shortlist).
2. **The demo:** the two screenshots with a one-line caption each, marked
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
   kept the case company out of git. Process numbers only (N2).
6. **Repo map** (short) and a link to `docs/README.md`.
7. **License:** MIT.

### 5. The case study (`docs/case-study.md`)

First person, past tense, about 1,000-1,500 words, voice and numbers per V5
and N2. Sections: **The problem** (the brief in general terms, as
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
- **Before the flip (author confirms):** delete the 10 merged remote branches
  (N3). Set topics with `gh repo edit --add-topic` (ruled list below). Upload
  `docs/assets/pipeline.png` as the social preview (web UI only: Settings →
  Social preview). Close out the build log: the Totals row (it still says
  "WP7 is left"), author times estimated from session timestamps as in PR
  #10, and the "author decided / caught" gaps (N4).
- **LinkedIn texts** in `private/linkedin/` (main checkout, never
  committed): `project-entry.md` (2-3 title options, the description,
  skills, repo link) and `post-draft.md` (2-3 hooks, one body, image notes).
  Same numbers rule as the case study (N2). Every option is marked so the
  author can pick.
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
| P1 | The repo's public face: the example dataset and `?lead=` link, the pipeline image and two demo screenshots, the new README with badge, `docs/case-study.md`, `docs/README.md`, past-tense notes in CLAUDE.md, requirements and plan. The author can open the README on the PR branch on GitHub and the example demo locally. | The author's picks on V1-V5 and N1, N2 | Browser: the example demo on :8502, and the README and case study rendered on GitHub (branch view) |
| P2 | Go public: `scripts/leak-check-github.sh`, the full leak sweep (PR refs included), branch cleanup, topics and social preview, the build log closed out, the LinkedIn texts in `private/linkedin/`, then the flip (coordinator, with the author) and the logged-out checks. The author can add the Project entry. | P1 merged; picks on N3, N4, V6 | Browser: the logged-out repo view after the flip; LinkedIn Post Inspector (author) |

P1 likely splits into four parts, run in order: the example dataset and deep
link (logic), the visuals (iterating), the README with the docs index and
touch-ups, and the case study. P2 is one PR (the script and the build log);
the rest of P2 is checks and steps outside git.

## Open visual decisions

The author picks before P1's visuals part starts. Recommended option first.

- **V1. Style of the pipeline image.**
  1) The demo's theme: warm off-white, ink, one orange accent, Geist. It
  matches the screenshots, so README and LinkedIn look like one piece.
  2) A neutral variant: the same layout in ink and greys with a blue accent.
  This puts distance from the deck's look, which WP7 built from the case
  vendor's brand study (see Risks).
  3) A Mermaid diagram in the README (GitHub renders it) plus a PNG export
  for LinkedIn. Least work, but it looks generic.
- **V2. What the pipeline image shows.**
  1) One 2:1 image. Top: the six stages left to right (open registries →
  market table → pre-filter → agent research → rubric score → SDR hand-off),
  each with a 3-5 word note and an "LLM" or "no LLM" mark. Bottom: the scoring
  strip (four signals × weights → `1 + 9 × weighted mean` → tiers A/B/C). No
  counts.
  2) Two images, flow and scoring apart. Clearer, but LinkedIn gets two
  uploads and the social preview only one.
  3) Flow only; the scoring stays as text in the README.
- **V3. Which demo screens.**
  1) Two: Queue with a lead open (score breakdown, a French quote with its
  English) and Market (map and funnel). Both go in the README; LinkedIn uses
  the Queue one next to the pipeline image.
  2) Only Queue with a lead open.
  3) Option 1 plus a short GIF of a weight slider re-ranking the queue. This
  is the demo's best moment, but the author records it by hand with a screen
  recorder.
- **V4. The README's opening lines.**
  1) "icp-scout maps a whole market from open data, researches a shortlist
  with an AI agent, scores it with a rubric you can read, and hands SDRs a
  ranked queue. Built as a take-home case for a GTM engineering role; the
  case company stays private, and the example config targets a fictional
  vendor."
  2) Problem first: "Outbound teams buy lists and guess at fit. icp-scout
  starts from every company in an open registry, …" with the framing line
  second.
  3) Framing first: "A take-home case for a GTM engineering role, built as a
  reusable tool: …"
- **V5. The case study's voice.**
  1) First person, past tense, plain and short (the build log's tone), about
  1,200 words, with lessons as bold lead-ins.
  2) A shorter piece (~600 words) that links out to the ADRs and the build
  log for depth.
  3) Q&A format ("Why not buy a list?", "Why not let the model score?").
- **V6. LinkedIn Project entry title (P2).**
  1) "icp-scout: from open data to a ranked SDR queue"
  2) "ICP research with an AI agent and a readable rubric"
  3) "GTM case study: scoring a whole market from open data"
  The post's hook gets 2-3 variants in `private/linkedin/post-draft.md`, picked
  there.

## Needs you

- **N1. Demo data for the screenshots.** The committed fixtures give 34
  groups, 3 researched; not worth screenshotting.
  1) The synthetic example dataset (Architecture 1). About 300 lines with its
  test. It also makes "try the demo" work from a fresh clone.
  2) Screenshot the tiny fixture demo as it is (a sparse map, three rows).
  3) No demo screenshot; the pipeline image only.
  Default used: 1.
- **N2. Numbers in public texts** (README, case study, LinkedIn).
  1) Process numbers only: hours, agent sessions, cost per researched lead,
  test count. No market or score numbers from the case run.
  2) Also the open-data market counts that committed docs already carry
  (funnel sizes in `docs/wp/wp5-demo.md`).
  3) No numbers.
  Default used: 1.
- **N3. Merged remote branches** (10, e.g. `wp1-sourcing`).
  1) Delete them before the flip. Their commits are in `main`, and PR refs
  keep the history visible.
  2) Keep them.
  Default used: 1. This is a remote deletion, so the coordinator asks first.
- **N4. The build log's open "author decided / caught" lines** (4 entries,
  plus 6 author times). A public build log full of TODOs undercuts its point,
  which is that the author made the calls.
  1) The coordinator asks the author for each one in P2 (a few lines each);
  author times are estimated from session timestamps as in PR #10.
  2) Replace the decided/caught gaps with "not recorded" and estimate the
  times.
  3) Leave them.
  Default used: 1.

## Rulings

- Ruling: the generator writes to `data/example/` and lives in `fixtures/demo/` — `data/` is gitignored and a subdirectory can't overwrite the case files; `fixtures/` because it reuses `make_fixtures.py`, which imports `tests/conftest.py` — cost if wrong: a moved script and one README line.
- Ruling: `?lead=<group_id>` deep link in the Queue page — headless Chrome can't click a row, and no screenshot tool may be added — cost if wrong: about 20 lines to remove.
- Ruling: images are rendered from an HTML source with the existing headless Chrome — no new dependency, re-renderable after wording changes — cost if wrong: redraw by hand.
- Ruling: one 1280×640 (2x) pipeline image for README, social preview and LinkedIn — GitHub's preview size, near LinkedIn's — cost if wrong: one extra crop.
- Ruling: the example build runs on port 8502 with all three `ICP_SCOUT_*` variables set — keeps the author's case review build on 8501 and stops `.env` from pulling in `private/` — cost if wrong: none.
- Ruling: CLAUDE.md, requirements and plan get a past-tense note, not a rewrite; WP plans stay unchanged — they are the honest record, and readers of a case repo expect it — cost if wrong: a few lines.
- Ruling: PR heads are fetched before the leak check, and PR and issue text gets its own check script — both become public with the repo, and `leak-check.sh` sees neither — cost if wrong: a few minutes.
- Ruling: topics `gtm-engineering, lead-scoring, sales-intelligence, icp, open-data, ai-agents, llm, claude, streamlit, python` — the role, the method and the stack — cost if wrong: one `gh` command.
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
  accent and a font close to the vendor's, and the demo theme followed it. The
  theme is already in history, so this only matters for how recognisable the
  shared images are. V1 option 2 is the way out if the author cares.
- **The leak check only warns in a worktree** (no `private/`). Every part
  runs the real check in the main checkout before its PR merges, or relies on
  CI with the secret.
- **Things outside git go public too:** PR text, review comments and Actions
  logs. The GitHub-text check covers the first two; `leak-check.sh` prints
  only hashes and paths, so the logs are safe.
- **The Project entry links a private repo** if it goes out before the flip.
  The order in P2 prevents that.

## Deviations

None yet.
