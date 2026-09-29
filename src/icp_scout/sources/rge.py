"""WP1. Pull certified installers from the ADEME RGE registry (data.ademe.fr, open data).

One row per qualification, so rows are grouped by SIRET and the set of domains
per company is kept: it is the product-mix signal. Filtered to
`market.rge_domains` from the ICP config.
"""

from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qsl, urlsplit

from icp_scout.http import CachedClient

URL = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"
PAGE_SIZE = 10000
FIELDS = [
    "siret", "nom_entreprise", "adresse", "code_postal", "commune", "latitude", "longitude",
    "telephone", "email", "site_internet", "domaine", "lien_date_debut", "lien_date_fin",
]  # fmt: skip


@dataclass
class RgeSite:
    """One certified establishment (SIRET) with every active target qualification it holds."""

    siret: str
    name: str
    domains: set[str] = field(default_factory=set)
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    address: str | None = None
    postcode: str | None = None
    commune: str | None = None
    lat: float | None = None
    lon: float | None = None

    @property
    def siren(self) -> str:
        return self.siret[:9]


def total_rows(client: CachedClient) -> int:
    """Rows in the whole registry, every domain: the top of the funnel."""
    return client.get_json(URL, {"size": 0}, key="total")["total"]


def fetch_rows(client: CachedClient, domains: list[str]) -> list[dict]:
    """Every registry row whose domain is one of `domains` (cursor paging)."""
    query = "domaine:(" + " OR ".join(f'"{d}"' for d in domains) + ")"
    params = {"size": PAGE_SIZE, "qs": query, "select": ",".join(FIELDS)}
    rows, seen = [], set()
    while True:
        page = client.get_json(URL, params)
        rows.extend(page.get("results", []))
        if not page.get("results") or not page.get("next"):
            break
        # `next` carries the query and the cursor. Its parameters are passed on
        # explicitly: httpx drops a URL's own query string when params are given.
        params = dict(parse_qsl(urlsplit(page["next"]).query))
        if params.get("after") in seen:
            raise RuntimeError(f"RGE paging repeats cursor {params.get('after')}")
        seen.add(params.get("after"))
    # The search is full-text; keep exact domain matches only.
    wanted = set(domains)
    return [r for r in rows if r.get("domaine") in wanted]


def is_active(row: dict, today: date) -> bool:
    end = row.get("lien_date_fin")
    return not end or end >= today.isoformat()


def group_by_siret(rows: list[dict]) -> dict[str, RgeSite]:
    """Merge qualification rows into one record per SIRET; the first non-empty value wins."""
    sites: dict[str, RgeSite] = {}
    for row in rows:
        siret = (row.get("siret") or "").replace(" ", "")
        if len(siret) != 14 or not siret.isdigit():
            continue
        site = sites.setdefault(siret, RgeSite(siret=siret, name=row.get("nom_entreprise") or ""))
        site.domains.add(row["domaine"])
        for attr, key in [
            ("phone", "telephone"), ("email", "email"), ("website", "site_internet"),
            ("address", "adresse"), ("postcode", "code_postal"), ("commune", "commune"),
            ("lat", "latitude"), ("lon", "longitude"),
        ]:  # fmt: skip
            if getattr(site, attr) is None and row.get(key) not in (None, ""):
                setattr(site, attr, row[key])
    return sites
