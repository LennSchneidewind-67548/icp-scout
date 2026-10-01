# WP5: The Streamlit demo

Budget: 2.5h, plus about 25 min for the research replay (author, 2026-10-01).
Planned 2026-10-01, local session.

**Done when:** `streamlit run app/streamlit_app.py` shows the market, the
ranked queue, the evidence behind any lead, a step-by-step replay of that
lead's recorded research and the six WP4 charts from the files in `data/`.
The weight sliders re-rank live. The app makes no model
call and no network request, and the 2-3 minute click path is written down
and timed once.

## Why this WP looks the way it does

- The demo is 2-3 minutes inside a 20-minute talk. It has to show the three
  things the slides can't: the size of the market as one picture, a score you
  can open down to the quoted evidence, and weights that re-rank with no model
  call (ADR 0002). Everything else is on slides already.
- "Offline from recordings" holds by construction: the app reads the pipeline's
  outputs (`market.parquet`, `signals.parquet`, `regrade/`, `insights/`) and
  the recorded transcripts, and re-scores with `score.score`, which is pure.
  No `llm.py` import, no API key.
- Case data stays local (ADR 0003): the app runs on the author's laptop during
  a screen share. No Streamlit Community Cloud, no hosted copy.
- Logic stays in `src/icp_scout/` where it is tested; the app file only lays
  out widgets.

## 1. The app, four tabs

Config through `config.load` (`ICP_SCOUT_CONFIG`), data directory from
`ICP_SCOUT_DATA`, default `data/`. Loading is wrapped in `st.cache_data`.
Missing files show which `icp-scout` command to run, not a traceback.

| Tab | Shows | Built from |
|---|---|---|
| **Market** | All groups as points on lat/lon, in-segment groups highlighted, the researched ones by tier; funnel numbers as metrics above the map | `market.parquet`, `scored.parquet`, `funnel.json` |
| **Queue** | The ranked table: rank, name, score, tier, region, `reason_en`, queue rank; references marked "calibration". Filters for tier and region | `score.score` with the sidebar weights |
| **Lead** | One lead: score and tier, then per signal the value, `rationale_en`, every evidence quote in French with `quote_en` next to it and the link; the agent's `facts` and `notes_en`; headcount and its source | `signals.parquet`, `regrade/<group_id>.json`, `market.parquet` |
| **Research replay** (in the Lead tab) | The agent's recorded run for that lead, one step per click or on a timer: each search query, each page fetched (URL), then the signal record it ended with, quotes in French with `quote_en` next to them. Footer: searches, fetches, tokens and cost of this lead | the ledger line (`lead`, `purpose=research`) gives the recording key; the transcript from `$ICP_SCOUT_RECORDINGS/research/<key>.json` (`private/llm` for the case) |
| **Insights** | The six kept findings (F1, F2, F3, F5, F6, F7), one chart each with its headline | `data/insights/<id>.vl.json` via `st.vega_lite_chart` |

**Sidebar: the weight sliders.** One slider per signal from `icp.signals`
(0-5, step 1, default the config weight; decided by the author, 2026-10-01) and a reset button. On change:
`score.score` on a copy of the config with the new weights. The Queue tab
then shows a rank-change column against the config weights and one line
"N leads entered the top 50, N left". That line is what the demo is for.

**The map, offline.** An Altair point chart on lon/lat
(`equirectangular` projection, no tiles): it renders without network and
matches the deck's charts. About 18,000 points: grey for the market, colour
for in segment, tier colours on top for the researched 177. Load the
`dataviz` skill before writing it, and reuse the WP4 theme from
`insights.theme`.

## 2. Code

- `src/icp_scout/demo.py` (pure, tested):
  - `load(data_dir) -> DemoData`: frames, regrades, insight specs.
  - `with_weights(icp, weights) -> IcpConfig`: a copy with new weights
    (pydantic `model_copy`), weights of 0 allowed, all 0 rejected.
  - `rerank(icp, data, weights) -> DataFrame`: `score.score`, plus
    `rank_change` against the config weights.
  - `queue_moves(base, new, size) -> (entered, left)`.
  - `lead_card(data, group_id) -> dict`: everything the Lead tab shows.
  - `replay_steps(recordings_dir, ledger, group_id) -> list[Step]`: the last
    `research` ledger line for the lead, its recording, then
    `claude_code.tool_calls` / `tool_results` paired into steps (kind, query
    or URL) and a final step with the recorded signals. API-backend
    recordings (`content` blocks with `server_tool_use`) map the same way.
    `None` when the lead has no recording, and the app says so.
  - `map_frame(data) -> DataFrame` and `map_chart(frame)`.
- `app/streamlit_app.py`: tabs, widgets, `st.dataframe` with column config
  (score as a progress column, link column for evidence URLs). No logic.

## 3. Tests (synthetic, `config/icp.example.yaml`)

- `demo.py` on a small synthetic data dir (built in `conftest.py`, the WP3/WP4
  frames): new weights change the order, the config weights reproduce
  `scored.parquet`, all-zero weights are rejected, `queue_moves` counts,
  `lead_card` carries `quote_en` next to every quote; `replay_steps` on a
  synthetic transcript gives the steps in order and ends with the record, and
  returns `None` for a lead without a recording.
- One `streamlit.testing.v1.AppTest` smoke test: the app starts on the
  synthetic dir, all four tabs render with no exception, moving a slider
  changes the first row.

## 4. The click path (private)

`private/demo-script.md`, about 3 minutes:

1. Market tab: "17,986 groups from open data, 1,221 in segment, 177
   researched." Point at a regional cluster (F5). (30 s)
2. Queue tab: the top 10 and their reason lines. (30 s)
3. Lead tab: open the #1 lead, one signal, the French quote with its
   translation and the link. "The model found this; the rubric scored it."
   (45 s)
4. Replay: step through that lead's research, four or five clicks, ending
   on the record. "Two searches, four pages, about $0.20." (30 s)
5. Sidebar: drop the weight on product mix to 0, then raise growth to the
   top. "N leads change places in the top 50, with no model call." Reset.
   (45 s)

The Insights tab is a fallback if a slide chart needs a closer look, not
part of the path.

## Steps and time

1. `demo.py`: load, rerank, queue moves, lead card + tests (40 min)
2. App: Queue tab and sliders (30 min)
3. App: Lead tab (20 min)
4. `replay_steps` + test, replay panel in the Lead tab (25 min)
5. App: Market map and Insights tab, per the dataviz skill (30 min)
6. AppTest smoke test; check with Wi-Fi off (10 min)
7. Click path, one timed run, screen recording as a backup, build log (20 min)

## Risks

- Map tiles and CDN fonts fail offline: the Altair map needs neither. Check
  the app once with the network off before the talk.
- 18,000 points may render slowly: aggregate the grey market layer to a hex
  or grid count if the first render takes more than 2 s.
- A live demo can fail on stage: the screen recording from step 6 is the
  fallback; the deck links to it.
- Fetched pages are French with no translation, so the replay shows URLs
  only; the French the audience sees is the evidence quotes, each with
  `quote_en`.
- Time: if late, cut the Insights tab and the filters, then the replay's
  timer (keep the step list); never the sliders or the Lead tab (`docs/plan.md`: cut app polish, never the insights).

## Decided (author, 2026-10-01)

- The research replay is in, as the Lead tab's second half.
- Sliders run 0-5 in steps of 1.
