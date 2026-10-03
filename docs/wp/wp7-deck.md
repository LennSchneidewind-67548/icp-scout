# WP7: The deck and the rehearsal

Budget: 2.5h, plus about 25 min proposed for the brand study (the author
decides). Planned 2026-10-03, local session.

**Done when:** a 16:9 English deck exists as a private Slides artifact, made
from the claude.ai "Slides" type, as `docs/requirements.md` asks ("HTML slides
artifact"). Its charts are drawn from `data/insights/*.vl.json`. A PDF export
sits in `private/deck/` as the offline backup. The talk has been timed twice
end to end, demo included, at 20 min or under, and the demo script's
"Timed run" section is filled in.

## Why this WP looks the way it does

- The case grades the approach, the assumptions, prioritization and the
  outbound motion, not only the list (`private/Case.md`). The slide order
  follows those four points, and the six WP4 findings are the evidence.
- The charts already exist as Vega-Lite specs. The deck draws them with
  vega-embed, the same specs the app shows (see the `insights.py` docstring).
  The only new chart work is restyling.
- The brand study gives direction, not something to copy. The deck takes one
  accent colour, a font close to the vendor's and its tone, and stays mostly
  white with a lot of space. The vendor's logo goes on the title slide only,
  if at all. The deck is about the vendor's market, and it should not look
  like a page copied from the vendor's site.
- Case content (ADR 0003): the brand study goes in `private/research/brand.md`
  and the deck in `private/deck/`. This doc names no colours or fonts. The
  deck goes to claude.ai only as a private artifact, never shared and never
  in git. The PDF is the backup if the network is down.

## 1. The brand study (`private/research/brand.md`, about 25 min)

Sources: the vendor's website (the home page, a product page, one blog or
customer page), read with WebFetch and Claude in Chrome. Chrome gives the
computed styles: CSS custom properties, `font-family`, the colours of the main
button and the headings. Then a press or media kit, if there is one, and the
LinkedIn banners. Write down:

- **Palette:** primary, secondary, neutrals and background as hex, and where
  each is used.
- **Typography:** the heading and body fonts, and the nearest Google Fonts
  match (an artifact may only load fonts from Google Fonts).
- **Layout and imagery:** density, corner radius, photos or illustrations,
  icon style.
- **Tone of voice:** three adjectives, and how a claim is phrased (numbers
  first? "you" or "we"?).
- **Deck tokens** derived from all of this: background, ink, muted text, one
  accent, one secondary colour for charts, the fonts. Each pair is checked
  for AA contrast.

The author reviews the tokens before any slide is built.

## 2. The storyline: 14 slides and an appendix

| # | Slide | Source | ~min |
|---|---|---|---|
| 1 | Title | | 0.25 |
| 2 | The answer first: 50 leads, how they were found, cost per lead | funnel, ledger | 1 |
| 3 | Approach: open data → group roll-up → pre-score → agent research → rubric → queue (diagram) | ADR 0001, 0002 | 1.5 |
| 4 | F1: the market is about 1,200 groups, not 19,000 companies | `f1_funnel` | 1.5 |
| 5 | F2: open data finds the segment but can't rank it | `f2_prescore` | 1.5 |
| 6 | Scoring: the model extracts signals with evidence, code computes the score; the weights come from the vendor research | ADR 0002, `private/research/rubric.md` | 1.5 |
| 7 | **Live demo** | `private/demo-script.md` | 3 |
| 8 | F7: the research step is lead enrichment too | `f7_websites` | 1 |
| 9 | F3: who to call first | `f3_tiers` | 1.5 |
| 10 | F6: what to say | `f6_product_mix` | 1 |
| 11 | F5: where | `f5_regions` | 1 |
| 12 | Outbound motion: tiers → cadence → triggers → hand-offs, with the HubSpot screenshot and one sequence (French with English) | WP6, `private/deck/*.png`, `data/export/sequences.md` | 2 |
| 13 | Assumptions and limits: headcount bands, our own rubric, n = 175, no accuracy set | `docs/plan.md`, `private/insights.md` | 1 |
| 14 | Next: research the whole segment (about $231), job postings as a trigger, n8n | F1, `docs/requirements.md` | 0.5 |
| A | Appendix: top 10 table, cost ledger, F4 size chart, a roll-up example | | — |

That is about 18.5 min, which leaves about 1.5 min of slack. Each slide gets one
headline that states its claim, and speaker notes with the numbers to say.
Every French text has its English translation next to it.

## 3. Build

- Create the artifact from the Slides `type_url` with the title "ICP Scout"
  (no company name in the title either) and follow the type's instructions,
  with the deck tokens from section 1.
- **Charts:** vega-embed from jsdelivr, each spec inlined from
  `data/insights/`. The accent goes in through vega-embed's `config` override
  when the chart is embedded, so `insights.theme` and the committed code stay
  neutral. Load the `dataviz` skill before restyling.
- **The diagram on slide 3:** load the `artifact-diagramming` skill.
- **Screenshots:** upload `private/deck/hubspot-*.png` as artifact assets.
- **PDF:** export and save as `private/deck/deck.pdf`, and check that the charts
  render in it.

## 4. The rehearsal

- **Run 1:** the full talk with the live demo, timed per section against the
  table. Cut or merge the slides that run over. Cut order: merge 13 into 14,
  then 10 into 9, then move slides to the appendix.
- **Run 2:** after the cuts, with Wi-Fi off for the demo. Fill in the "Timed
  run" section of `private/demo-script.md` (date, duration, a backup screen
  recording).
- Check that the numbers in the demo script match the data the deck uses (both
  as of 2026-10-01).

## Steps and time

1. Brand study → `private/research/brand.md`, the author reviews the tokens (25 min)
2. Storyline, headlines and speaker notes (30 min)
3. Build the artifact: charts, diagram, screenshots (50 min)
4. PDF export and fixes (10 min)
5. Two timed runs and the cuts (40 min)
6. Build log, "Built" section (10 min)

## Risks

- The deck borrows too much from the brand and looks like a page from the
  vendor's site. To prevent this, it takes one accent and one font, and
  everything else stays neutral.
- vega-embed doesn't render in the PDF export. Fallback: export PNGs with
  `vl-convert-python` (one-off, in `private/`, not a dependency) and
  embed the images.
- The talk runs long. The cut order is in section 4.
- The artifact is case content on claude.ai. It stays private, and the author
  can delete it after the talk.

## Decided (author, 2026-10-03)

- The deck and the talk are in English.
- The vendor's brand is a rough guide. The slides keep their own clean,
  minimal look.
