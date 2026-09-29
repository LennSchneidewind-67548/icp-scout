# icp-scout

Map a whole market from open data, research the shortlist with an agent,
score it with a rubric you can read, and hand SDRs a ranked queue.

```
open registries -> market table -> pre-filter -> agent research -> rubric score -> SDR hand-off
   (RGE, SIRENE)     (every firm)    (no LLM)      (shortlist)      (1-10, tiers)   (CSV + openers)
```

The example config targets heat-pump and solar installers in France for a
fictional software vendor. Everything specific to a vendor (market, segment,
reference customers, signals and their weights) lives in one YAML file, so
pointing it at another ICP is a config change, not a code change.

## Status

Sourcing (WP1) works: `icp-scout source` pulls the market, rolls sister
companies up to groups and pre-filters a shortlist. The other stages land one
work package at a time (`docs/plan.md`).

## Design choices worth reading

- **The whole market, not a list** (ADR 0001). Public registries give every
  certified installer; the agent only spends money on the shortlist.
- **The model extracts, the rubric scores** (ADR 0002). Every score comes
  from signals with quoted evidence and weights anyone can change.
- **It states what it costs.** Every model call goes to a cost ledger;
  cost per researched lead is reported.
- **It drafts, people send.** Nothing is sent to anyone.

## Run it

```sh
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -e ".[dev]"
pytest
icp-scout show-config
icp-scout source --limit 200   # a sample; the full first pull takes about an hour
icp-scout funnel               # market -> segment -> shortlist, with the reason at each stage
```

`source` caches every HTTP response under `data/cache/`, so a re-run makes no
calls. `--offline` reads the cache only; `--refresh` fetches again. It writes
`data/companies.parquet` (one row per company), `data/market.parquet` (one row
per group, with pre-score, segment flags and the reason for every exclusion)
and `data/funnel.json`.

## License

MIT
