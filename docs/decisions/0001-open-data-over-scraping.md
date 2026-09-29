# ADR 0001: Source the market from open registries, not scraping or lists

Status: accepted, 2026-09-29

## Decision

The market comes from two French public sources: the ADEME RGE registry
(every certified energy-renovation installer, with qualification domains,
website, email and phone) and recherche-entreprises.api.gouv.fr (headcount
band, NAF code, establishments). Both are free and need no key.

## Why

- **Completeness is the argument.** Fifty hand-picked companies answer the
  brief; the whole certified market shows the outbound motion scales, and it
  makes market-level insights possible.
- **Certification is a qualification signal.** RGE status is what lets an
  installer's customers get state subsidies, so nearly every serious heat-pump
  or solar installer holds one.
- **No scraping, no terms-of-service risk.** Company websites are read only
  for the shortlist.

## Consequences

- One RGE row per qualification: rows are grouped by SIRET before anything else.
- Headcount is a band, not a number. The size signal is scored on bands.
- The approach carries over to other countries only where a comparable
  registry exists. That limit belongs in the README.
