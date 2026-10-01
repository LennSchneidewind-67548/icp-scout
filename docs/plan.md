# Plan

About 20 hours. Presentation date: 2026-10-05.
Rule of thumb: if the pipeline runs late, cut app polish, never the insights.

| WP | What | Budget | Done when |
|---|---|---|---|
| 0 | Setup, case-company research (product, pricing, French presence, competitors) into `private/research/` and `private/icp.yaml` | 1.5h | Rubric weights argued from research, not guessed |
| [1](wp/wp1-sourcing.md) | Sourcing: RGE pull grouped by SIRET, SIRENE join, **roll-up of sister companies to group level** (same manager, address, phone or website) before the size filter, **second source** for installers without RGE (company register, installer NAF codes and an energy name), pre-filter, funnel counts | 5.5h | `icp-scout source` writes the market table; the funnel is reportable |
| [2](wp/wp2-research.md) | Agent research on the shortlist (~150-200): signals with evidence, recordings, cost ledger | 5h | Every shortlisted company has signals + evidence; cost per lead is known |
| [3](wp/wp3-scoring.md) | Rubric score, tiers, rationale text | 1.5h | Top 50 with score, tier and a one-line why |
| [4](wp/wp4-insights.md) | Insights: regional clusters, product-mix patterns, size vs score, what separates A from C | 3h | 4-6 findings, each with one chart |
| [5](wp/wp5-demo.md) | Streamlit demo, with a replay of one lead's recorded research | 3h | The 2-3 minute demo runs offline from recordings |
| 6 | SDR hand-off: HubSpot CSV, French openers with translations | 1h | CSV imports cleanly; openers read well in translation |
| 7 | Deck + rehearsal | 2.5h | 20 minutes, timed twice |

## Things to verify early

- ~~The reference customers resolve to the right legal entities~~ Done in WP0.
  Name search failed for both. One reference is a holding whose installer
  subsidiaries are each under 30 staff (hence the group roll-up). The other
  isn't in the RGE registry at all (hence the second source).
- ~~How complete RGE `site_internet` is~~ Done in WP0: in a sample of 9,200
  target SIRETs, 29% have their own website, 55% only a certifier's profile page, and 16% none.
  The agent needs web search for most leads, which drives the cost per lead.
- SIRENE headcount bands are coarse (e.g. 20-49, 50-99) and can be years old;
  say so in the assumptions.

## After the presentation

- Swap in synthetic fixtures, check `git log` for anything case-specific, make the repo public.
- LinkedIn post: the problem, the funnel numbers, cost per lead, link to the repo.
