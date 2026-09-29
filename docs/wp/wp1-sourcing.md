# WP1: Sourcing

Budget: 5.5h. Planned 2026-09-29, to be built in a remote session.

**Done when:** `icp-scout source` writes the market table, and the funnel
(market -> segment -> shortlist) is reportable with a count and a reason at
every stage.

## Rules for this session

- Read `CLAUDE.md`, `docs/requirements.md` and ADRs 0001-0003 first.
- **No case-company content** (ADR 0003). You can't see `private/` and don't
  need it. Build and test against `config/icp.example.yaml` only.
- Test fixtures are **synthetic**: fictional company names and made-up
  SIRETs, in the exact shape of the real API responses. No real registry rows
  in `fixtures/`.
- The leak check needs the `LEAK_TERMS` secret, so CI runs it, not you.
- Work on branch `wp1-sourcing`, push, open a PR, don't merge.
- Add the `docs/build-log.md` entry at the end (mode `remote`, author time TODO).

## What WP0 found (why this WP looks the way it does)

- One reference customer is a **holding with several installer subsidiaries**,
  each below the 30-staff floor. Filtered per company, the best-known fit
  would be dropped as "too small". So sister companies are **rolled up to
  group level before the size filter**.
- The other reference **isn't in the RGE registry at all** (commercial-PV
  roots, which need no RGE). So there's a **second source**: the company register,
  filtered by installer NAF codes and an energy-related name.
- Only ~29% of target RGE companies list their own website; ~55% list a
  certifier's profile page. A website shared by many companies is a directory, not a link between them.

## Data sources (checked live 2026-09-29)

Both are free and need no key.

**ADEME RGE registry**
`GET https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines`
- ~159k rows, **one row per qualification**. Cursor paging: follow `next`
  (`size` up to 10000). Filter with `qs=domaine:"..."` or by pulling and filtering locally.
- Fields: `siret, nom_entreprise, adresse, code_postal, commune, latitude,
  longitude, telephone, email, site_internet, domaine, meta_domaine,
  nom_qualification, organisme, lien_date_debut, lien_date_fin, particulier`.
- `domaine` values must match `market.rge_domains` exactly (they do for the example config).

**recherche-entreprises (company register)**
`GET https://recherche-entreprises.api.gouv.fr/search`
- Lookup by SIREN: `?q=<siren>&per_page=1`; check that `results[0].siren` matches.
- Filtered search: `activite_principale=43.22B,43.21A`,
  `tranche_effectif_salarie=12,21,22,31`, `etat_administratif=A`, `page`,
  `per_page` (max 25). Returns `total_results`, `total_pages`. Check for a
  result cap on deep pages.
- Useful fields per result: `siren, nom_complet, etat_administratif,
  tranche_effectif_salarie, annee_tranche_effectif_salarie,
  categorie_entreprise, activite_principale, date_creation,
  nombre_etablissements_ouverts, finances{year: {ca, resultat_net}}`,
  `siege{adresse, code_postal, departement, region, latitude, longitude}`, and
  `dirigeants[]`:
  - `type_dirigeant: "personne physique"`: `nom, prenoms, date_de_naissance` (YYYY-MM), `qualite`
  - `type_dirigeant: "personne morale"`: `siren, denomination, qualite`.
    **Auditors show up here** (`qualite` contains "Commissaire aux comptes").
    They must never link companies.
- Rate limit ~7 req/s: stay at 5/s, back off on 429.
- Person search for the group expansion: the API documents filters like
  `nom_personne`, `prenoms_personne`, `date_naissance_personne_min/max`.
  **Verify the names before relying on them.**

**Caching:** every HTTP response goes to `data/cache/<source>/<key>.json`
(`data/` is gitignored). Runs are resumable and a re-run makes no calls.
`--refresh` ignores the cache. The example domains cover ~20k SIRETs, so the
first full register join takes about an hour. Use `--limit N` while developing.

**If the sandbox blocks either host:** build everything against fixtures,
say so in the PR, and leave the full pull for the author to run locally.

## Pipeline

All in `src/icp_scout/`; the module stubs already exist.

1. **`sources/rge.py`**: pull rows for `market.rge_domains`, drop expired
   qualifications (`lien_date_fin` < today), group by SIRET. Per SIRET keep: name,
   the **set of domains** (product-mix signal), phone, email, website,
   address, lat/lon.
2. **`sources/sirene.py`**: join on SIREN (first 9 digits) via the register.
   Drop closed companies (`etat_administratif != "A"`, its own funnel stage).
3. **Second source** (`sirene.register_search()`): filtered search by
   `market.second_source.naf_codes`, a band at or above
   `min_headcount_band`, active only; keep results whose name contains one of
   `name_keywords` as a whole word (case- and accent-insensitive, so "pac" doesn't match "espace"). Deduplicate against the RGE set; the rest
   are tagged `source="register"` with an empty domain set.
4. **Group roll-up** (new `group.py`, union-find over SIRENs), **before** the
   size filter. Link two companies when they share:
   - a physical-person manager: normalized surname + first names + birth month;
   - a legal-entity manager (the parent or holding) whose `qualite` is **not** an auditor;
   - a normalized phone number;
   - a website domain, unless the domain appears on more than 20 SIRENs
     (a certifier or directory page), which never links;
   - a normalized address, only when at most 3 companies share it (business centers).

   Each group keeps the list of keys that joined it, so every roll-up can be
   explained ("same manager + same phone").

   **Expansion:** for companies with at least 10 staff that are below
   `headcount_min` alone, look up other companies of the same physical-person
   manager in the register. This finds holdings and non-RGE sisters. Cap the
   number of calls (config or constant) and cache them.
5. **Headcount from bands**: map INSEE band codes to (low, high):
   `00` 0, `01` 1-2, `02` 3-5, `03` 6-9, `11` 10-19, `12` 20-49, `21` 50-99,
   `22` 100-199, `31` 200-249, `32` 250-499, `41` 500-999, `42` 1000-1999, and so
   on; `NN` or missing = unknown. Group headcount = sum of lows, sum of highs,
   sum of midpoints, plus how many members are unknown. **In segment** when the
   midpoint sum is in `[headcount_min, headcount_max]`. Flag `near_band` when
   it's within half the band's width outside.
6. **`prefilter.py`**: a rule-based pre-score per in-segment group, no LLM,
   weighted with the rubric weights from the config so it approximates the
   final score:
   - size: 1 inside the band, 0.5 near it;
   - product mix: product lines covered by the group's RGE domains
     (via `market.product_lines`); register-source groups get 0.5 (unknown,
     resolved by the agent in WP2);
   - tech: own website that isn't a directory domain;
   - growth: more than one open establishment, or a member created in the last 24 months.

   Shortlist = the top `prefilter.shortlist_size` (default 175). Every
   excluded row keeps an `exclusion_reason`.
7. **Funnel** (`funnel.py`): RGE rows -> active target qualifications ->
   SIRETs -> SIRENs -> active companies -> + register source -> groups -> in
   segment -> shortlist. Written to `data/funnel.json`, printed by `icp-scout funnel`.

## Config changes

All optional, with defaults, so existing configs still load. Update
`config/icp.example.yaml` and `tests/test_config.py`.

```yaml
market:
  product_lines:          # product line -> RGE domains that prove it
    heat_pump: ["Pompe à chaleur : chauffage"]
    solar: ["Panneaux solaires photovoltaïques", "Chauffage et/ou eau chaude solaire"]
  second_source:
    naf_codes: ["43.21A", "43.22B"]
    name_keywords: ["solaire", "photovoltaïque", "énergie", "energie", "pac", "thermique"]
    min_headcount_band: "11"
prefilter:
  shortlist_size: 175
```

(French terms: "Pompe à chaleur : chauffage" = heat pump: heating; "Panneaux
solaires photovoltaïques" = solar PV panels; "Chauffage et/ou eau chaude
solaire" = solar heating and/or hot water; name keywords = solar,
photovoltaic, energy, heat pump (abbr.), thermal.)

## Outputs

- `data/companies.parquet`: one row per SIREN with the source fields and its `group_id`.
- `data/market.parquet`: one row per group: `group_id`, name (largest
  member), member SIRENs, link keys, domains, product lines, website,
  department, region, lat/lon, headcount low/mid/high/unknown count, latest revenue
  (summed), earliest creation date, `source` (rge / register / both),
  `pre_score`, `in_segment`, `near_band`, `shortlisted`, `exclusion_reason`.
- `data/funnel.json`: ordered stages with counts.
- Add `pyarrow` to the dependencies.
- CLI: `icp-scout source [--limit N] [--offline] [--refresh]` and `icp-scout funnel`.
  `--offline` reads the cache only (or fixtures in tests) and fails on a cache miss.

## Tests

httpx `MockTransport` over synthetic fixtures in `fixtures/sources/`:
- RGE rows grouped by SIRET, expired qualifications dropped.
- Band math, including unknown bands.
- Grouping by manager, by holding, by phone, by website.
- **An auditor shared by two companies doesn't link them.**
- **A directory domain shared by many companies doesn't link them.**
- A synthetic holding whose members are each under the band but together
  inside it ends up in the segment and on the shortlist.
- A non-RGE company enters via the second source.
- The funnel never grows from one stage to the next.
- `icp-scout source --offline` end to end on fixtures.

`ruff check .` and `pytest` green.

## Order and time

| Step | Budget |
|---|---|
| RGE pull + cache | 0.75h |
| Register join | 1h |
| Group roll-up + expansion | 1.5h |
| Second source | 0.75h |
| Pre-filter, funnel, CLI | 1h |
| Tests, cleanup, PR | 0.5h |

If time runs short: keep grouping within the pulled set, drop the manager
expansion, and say so in the PR.

## Author acceptance (local, after the PR)

1. Add the new config keys to `private/icp.yaml`.
2. `ICP_SCOUT_CONFIG=private/icp.yaml icp-scout source` (full pull, ~1h first run).
3. Both reference customers appear as in-segment groups: the holding through
   the roll-up, the other through the second source. Ideally both are shortlisted.
4. Note the funnel numbers in `private/` for the deck; run the leak check.

## Assumptions to state on the slides

- Headcount bands are coarse and can be years old.
- A group is inferred from shared managers and contact details, not a legal consolidation.
- The second source only finds companies whose NAF code and name look like an installer.
