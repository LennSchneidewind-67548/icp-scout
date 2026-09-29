"""WP1. Pull certified installers from the ADEME RGE registry (data.ademe.fr, open data).

One row per qualification, so rows are grouped by SIRET and the set of domains
per company is kept: it is the product-mix signal. Filtered to
`market.rge_domains` from the ICP config.
"""
