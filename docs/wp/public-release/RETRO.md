# Public release retro

- **Shipped:** plan #14, decisions #15, P1 plan #16; P1 parts A #17 (example dataset, `?lead=` link), B #18 (pipeline image, screenshots), C #19 (README, docs index, case study), fix #20 (image layout); P2 plan #21, part A #22 (GitHub-text leak check, build log closed), closing #23 (go-public entry, release totals); sign-off docs #24. Repo public on 2026-10-06.
- **Stops:** interview 2 rounds (repo shape, framing, LinkedIn scope, history; then hiring status). Picks 2 (image style, README opening, LinkedIn title, with a second round for new title options). Decisions 3 (the case-study page, the build-log gaps, the go-public yes plus two build-log fields). Reviews 2 (P1, where the author caught the pipeline image layout on GitHub; P2 checked logged-out by the coordinator).
- **Rulings that held:** example data from a seeded generator rather than the thin fixtures; one 2560×1280 image reused for the README, social preview and LinkedIn; LinkedIn texts written by the coordinator in the main checkout, since worktrees have no `private/`; deleting the 10 merged branches before the flip.
- **Rulings that were wrong or weak:** reading "drafts are fine" as "took it as proposed" for build-log fields that had no draft. It went unchallenged, but it was an inference. The 6 Oct author times are rough, tied to merge times.
- **Where it stalled:** the first planner couldn't be resumed because the coordinator removed its worktree before sending it the picks, so a fresh planner was spawned. Headless Chrome `--screenshot` captured only Streamlit's loading skeleton, so the worker added a DevTools script, `docs/assets/src/shoot.py`. Two parts needed one fix round each (#18 crop and layout, #19 brief details and hours). One `/conductor:break` and resume between phases, with no loss.
- **Usage:** `usage.py` found no sessions. It looks for `design/public-release/`, but this project keeps plans in `docs/wp/`.
- **Improve conductor:**
  - `usage.py` should read the plan path from the ledger's `Plan:` line (or the Pipeline "Plans:" setting), not hard-code `design/<slug>/`. The same goes for where RETRO.md goes.
  - Coordinator: don't remove a planner's worktree until its picks round is done, or the planner can't be resumed with `SendMessage`.
  - The Pipeline screenshot recipe should warn that Streamlit needs a DevTools capture, not `--screenshot`.
  - When the feature skill asks build-log-style questions with partial drafts, offer an explicit "as proposed" option per gap rather than inferring it.
  - A go-public feature should have a P2 template: the leak sweep including PR refs and PR text, branch cleanup, the flip behind an explicit yes, then logged-out checks.
