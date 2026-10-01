# WP3: Rubric, tiers and the SDR queue

Budget: 1.5h. Planned 2026-10-01, local session.

**Done when:** `icp-scout score` turns `data/signals.parquet` into a ranked
table with score, tier and a one-line reason per lead, the top 50 is decided
by the rubric and not by the pre-rank, and changing a weight re-ranks with no
model call.

## Why this WP looks the way it does

WP2 left the rubric saturated: 13 distinct scores over 177 leads, 73 of them
at 9.55 or above for 50 slots. The cut falls inside a tie, so the pre-rank
decides 20 places, and the pre-rank doesn't predict the agent's score
(Spearman -0.07). Size and product mix are 1 for most leads; growth and tech
do the separating, on a three-step scale.

Decision (author, 2026-10-01): **finer signals**, not a smarter tie-break.
Grade growth on five steps and score headcount by its distance from a sweet
spot inside the segment band.

## 1. A regrade pass over the recorded evidence (one small call per lead)

The agent's evidence is already recorded; re-researching the web is not
needed. A new `purpose="regrade"` call per lead, no tools, gets the WP2
evidence and rationale for `size_fit` and `growth` and returns:

- `headcount_estimate`: the group's headcount as a number, from the quoted
  evidence ("over 40 staff", "300 employees") or the registry band, plus
  which one it used. `null` if neither.
- `growth`: one of 0, 0.25, 0.5, 0.75, 1 against the finer definition below,
  with the index of the evidence item it rests on. It may not cite anything
  outside the recorded evidence.
- `phrase_en` per signal: at most 10 words, for the reason line.

Same backend, model and recordings directory as WP2 (`claude-code` on the
subscription for the case, so no API money), effort `low`, no tools;
recorded, replays offline. The agent's `facts` (stated headcount, open roles)
go in with the evidence. The
model still never outputs a score (ADR 0002): it grades one signal against a
written scale, as before.

Finer growth scale. It goes into a new `grades` key on the signal, not into
`definition`: the definitions are part of the research prompt, so changing
one would invalidate every WP2 recording.

| Value | Meaning |
|---|---|
| 1 | Two or more current openings in sales, planning, admin or install, or a dated site/entity opening in the last 24 months |
| 0.75 | One current opening in those roles, or an undated "recent" opening with a second sign |
| 0.5 | Openings only in other roles (roofer, stove fitter), or undated/unverifiable postings, or an undated branch opening |
| 0.25 | A generic "we're recruiting" with no roles, or postings older than 12 months |
| 0 | No evidence found |

## 2. Headcount by distance from the sweet spot (code, no model)

New optional config key, with the band edges from `segment`:

```yaml
segment:
  headcount_min: 30
  headcount_max: 300
  sweet_spot: [60, 200]   # value 1 inside; linear down to edge_value at the band edges
  edge_value: 0.6         # 60-200 decided by the author, 2026-10-01
```

`size_fit = 1` inside the sweet spot, falling linearly to `edge_value` at
`headcount_min` and `headcount_max`. Outside the band the agent's 0 / 0.5
stays. Headcount source: the regrade's `headcount_estimate`, else the
registry midpoint. Argument for the shape: pricing is per seat, so value
grows with the office team, and very large groups are more likely to run an
ERP already (to argue on a slide; numbers are the author's call).

Caveat: 101 of 177 researched groups sit in the registry band 20-49, so the
registry alone can't separate them; the agent's quoted headcount is what
makes this signal finer.

## 3. `score.py`: real code

- `score(signals, market, icp) -> DataFrame`: one row per group with the four
  signal values, `score = 1 + 9 x weighted mean`, tier from `tiers`, rank.
- Residual ties: broken by the number of signals backed by evidence, then by
  name for a stable order. **Never the pre-rank.** The command prints how many
  top-50 places a tie-break still decided.
- `reason_en`: one line built in code from the phrases and values, e.g.
  `9.4 A · PV + heat pumps · ~120 staff (sweet spot) · 2 open sales roles ·
  weakest: plain contact form`.
- Pure and deterministic; the regrade results are read from
  `data/regrade/<group_id>.json`, so weight changes need no model call (the
  app's sliders).
- `icp-scout score` writes `data/scored.parquet` and prints the top 50 and the
  tie-break count. `icp-scout regrade` runs the pass (`--offline` replays).

## 4. References

Decided (author, 2026-10-01): **calibration, not queue.** Scored and ranked
like every lead, marked `is_reference` (config `reference_sirens`), shown with
their rank, but never given one of the `queue.size` SDR places.

## 5. Tests (synthetic, `config/icp.example.yaml`)

- Score formula, weights, tiers; a weight change re-ranks.
- Sweet-spot curve: inside, at the edges, outside the band, no headcount.
- Tie-break order never uses the pre-rank.
- Reason line format; references excluded from the 50.
- Regrade replays from a synthetic recording.

## Steps and time

1. Config keys + finer growth definition (15 min)
2. Regrade pass, prompt, recording, run on 177 leads (35 min, mostly waiting)
3. `score.py` + CLI + tests (30 min)
4. Re-rank, compare with `rerank-175.csv`, findings + build log (10 min)

## Risks

- The regrade uses plan usage (177 short calls, no tools). The 7-day cap of
  0.7 stays in force.
- The finer growth grade rests on the WP2 evidence. Where the agent recorded
  one quote, the regrade can't find a second; that's an honest limit.
