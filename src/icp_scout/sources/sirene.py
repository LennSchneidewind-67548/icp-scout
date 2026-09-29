"""WP1. Enrich companies with firmographics from recherche-entreprises.api.gouv.fr.

Headcount band (tranche_effectif_salarie), NAF code, creation date, number of
establishments, legal status. Joined on SIREN (first 9 digits of the SIRET).
Responses are cached on disk; the API is free and needs no key.
"""
