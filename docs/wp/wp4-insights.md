# WP4: Insights

Budget: 3h. Planned 2026-10-01, local session.

**Done when:** `icp-scout insights` turns `data/market.parquet`,
`data/signals.parquet` and `data/scored.parquet` into one data table and one
chart spec per finding, and 4-6 findings are written up in
`private/insights.md`, each with a number, a chart, what it changes for the
SDR motion, and its caveat.

## Why this WP looks the way it does

- The brief grades the approach, the assumptions and the prioritization, not
  only the list. Each finding has to change a decision (who to call first,
  which territory, what to say), not just describe the data.
- Two populations, never mixed without saying so: the **market** (17,986
  groups, 1,221 in segment; open data only) and the **researched set** (177
  groups; agent signals). The pre-score picked the researched set, so patterns
  in it hold for the shortlist, not the market. Every chart says which
  population it shows.
- n = 177, and the tiers come from our own rubric: report counts and medians,
  no significance claims. "What separates A from C" partly restates the
  weights, so that finding looks at what the weights don't force: real
  headcount, region, product lines, roll-up, website presence.

## 1. Candidate findings (compute all, keep the 4-6 that hold)

| # | Finding to test | Population | Chart | What it changes |
|---|---|---|---|---|
| F1 | The funnel: registry rows → groups → in segment → shortlist → queue; how many in-segment groups exist only because of the roll-up or the second source | market | horizontal funnel bars | Size of the addressable market; why the group roll-up matters |
| F2 | Open data can't rank: pre-score vs agent score (Spearman about 0.1); the references the pre-filter missed | researched | scatter, pre-score vs score, references marked | Prioritization happens in the research step; the cost per lead (about $0.17-0.22) makes it scalable |
| F3 | What separates A from B/C: growth (mean 0.82 vs 0.29) and real headcount (median about 70 vs 35), not product mix (saturated) | researched | signal means by tier (dot plot) | Hiring is the trigger to watch |
| F4 | Size vs score: registry band vs the agent's headcount; where the sweet spot sits | researched | strip/scatter, headcount vs score | The registry band 20-49 hides real size; SDRs verify size, not trust the registry |
| F5 | Regional clusters: in-segment groups and A-tier count per region | market + researched | bars, or a map from lat/lon | Territory split for SDRs, field-event targeting |
| F6 | Product mix: PV only / heat pumps only / both; market vs in segment vs tier A | market + researched | 100% stacked bars | Messaging by product line |
| (F7) | Tech maturity: share with their own website or a lead form | researched | bars | Opener angle (digital lead handling) |

A finding is kept when the difference shows in plain counts, survives dropping
the references, and changes a decision. Otherwise it becomes one line in the
appendix.

**Decided (author, 2026-10-01):** keep F1, F2, F3, F5, F6, F7. F4 goes to
the appendix: the regrade falls back to the registry midpoint, so the two
headcounts can't disagree much. F3 takes the part of F4 the weights don't
force (growth rises with headcount). F7 covers both scoring (a project quote
form vs a plain contact form) and enrichment (the website the SDR needs).

## 2. `insights.py` (code, no model)

- One pure function per finding, `(market, signals, scored, icp) -> DataFrame`,
  on the fields already in the parquet files (`region`, `product_lines`,
  `members`, `source`, `headcount_*`, `pre_score`, the signal values, `tier`).
  Config through `config.load`. No model calls, no API money.
- Charts as Altair specs (Altair ships with Streamlit, so no new dependency),
  saved as Vega-Lite JSON. The WP5 app renders them with `st.altair_chart`,
  the WP7 deck with vega-embed: one source for both.
- `icp-scout insights` writes `data/insights/<id>.csv` and `<id>.vl.json` and
  prints the headline number per finding. Region codes map to names through a
  small table in code (public INSEE codes, not case content).
- Load the `dataviz` skill before writing the chart specs.

## 3. Write-up (private)

`private/insights.md`: per kept finding, the headline, the number, the chart
file, what it changes, the caveat. The deck (WP7) is built from it.

## 4. Tests (synthetic, `config/icp.example.yaml`)

- Each finding function on a small synthetic market and scored frame: counts,
  population label, references excluded where stated.
- The chart specs are valid JSON with the expected encodings.

## Steps and time

1. Compute every candidate in a scratch script and look at the numbers (45 min)
2. The author picks 4-6 findings (decision point)
3. `insights.py` + CLI + tests for the kept ones (60 min)
4. Charts per the dataviz skill, check they read at slide size (30 min)
5. `private/insights.md` + build log (30 min)

## Risks

- Findings that only restate the rubric weights (F3). Lead with what the
  weights don't force.
- Region and product lines come from the registry; groups from the second
  source have no product lines.
- Time: if late, keep F1, F2, F3 and F5 and cut chart polish (`docs/plan.md`).
