# Plan

About 20 hours. Presentation date: TODO (around 2026-10-06).
Rule of thumb: if the pipeline runs late, cut app polish, never the insights.

| WP | What | Budget | Done when |
|---|---|---|---|
| 0 | Setup, case-company research (product, pricing, French presence, competitors) into `private/research/` and `private/icp.yaml` | 1.5h | Rubric weights argued from research, not guessed |
| 1 | Sourcing: RGE pull grouped by SIRET, SIRENE join, pre-filter, funnel counts | 4h | `icp-scout source` writes the market table; the funnel is reportable |
| 2 | Agent research on the shortlist (~150-200): signals with evidence, recordings, cost ledger | 5h | Every shortlisted company has signals + evidence; cost per lead is known |
| 3 | Rubric score, tiers, rationale text | 1.5h | Top 50 with score, tier and a one-line why |
| 4 | Insights: regional clusters, product-mix patterns, size vs score, what separates A from C | 3h | 4-6 findings, each with one chart |
| 5 | Streamlit demo | 2.5h | The 2-3 minute demo runs offline from recordings |
| 6 | SDR hand-off: HubSpot CSV, French openers with translations | 1h | CSV imports cleanly; openers read well in translation |
| 7 | Deck + rehearsal | 2.5h | 20 minutes, timed twice |

## Things to verify early

- The reference customers resolve to the right legal entities: a name search
  can return a same-named holding or an unrelated firm (see `private/notes.md`).
  How the references look in the data calibrates the rubric.
- How complete RGE `site_internet` is. Without a website the agent needs web search.
- SIRENE headcount bands are coarse (e.g. 20-49, 50-99) and can be years old;
  say so in the assumptions.

## After the presentation

- Swap in synthetic fixtures, check `git log` for anything case-specific, make the repo public.
- LinkedIn post: the problem, the funnel numbers, cost per lead, link to the repo.
