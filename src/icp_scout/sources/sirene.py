"""WP1. Enrich companies with firmographics from recherche-entreprises.api.gouv.fr.

Headcount band (tranche_effectif_salarie), NAF code, creation date, number of
establishments, legal status. Joined on SIREN (first 9 digits of the SIRET).
Responses are cached on disk; the API is free and needs no key.

Also the second source: installers without RGE, found by a filtered register
search (NAF code, headcount band, an energy word in the name), and the person
search that finds other companies of the same manager (see group.py).
"""

import calendar
import re
import unicodedata
from dataclasses import dataclass, field

from icp_scout.config import SecondSource
from icp_scout.http import CachedClient
from icp_scout.sources.rge import RgeSite

URL = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25
# The API refuses page * per_page above this.
RESULT_CAP = 10000

# INSEE headcount bands: code -> (low, high) staff. "NN" or missing = unknown.
BANDS: dict[str, tuple[int, int]] = {
    "00": (0, 0), "01": (1, 2), "02": (3, 5), "03": (6, 9),
    "11": (10, 19), "12": (20, 49), "21": (50, 99), "22": (100, 199),
    "31": (200, 249), "32": (250, 499), "41": (500, 999), "42": (1000, 1999),
    "51": (2000, 4999), "52": (5000, 9999), "53": (10000, 10000),
}  # fmt: skip


def band_range(code: str | None) -> tuple[int, int] | None:
    return BANDS.get(code or "")


def band_mid(code: str | None) -> float | None:
    r = band_range(code)
    return None if r is None else (r[0] + r[1]) / 2


@dataclass
class Company:
    """One legal unit (SIREN): register firmographics plus its RGE establishments."""

    siren: str
    name: str
    source: str  # "rge" or "register"
    via: str  # "rge", "naf_search" or "manager"
    active: bool = True
    sirets: list[str] = field(default_factory=list)
    domains: set[str] = field(default_factory=set)
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    address: str | None = None
    postcode: str | None = None
    department: str | None = None
    region: str | None = None
    lat: float | None = None
    lon: float | None = None
    naf: str | None = None
    band: str | None = None
    band_year: str | None = None
    category: str | None = None
    created: str | None = None
    establishments_open: int | None = None
    revenue: float | None = None
    revenue_year: str | None = None
    managers: list[dict] = field(default_factory=list)
    group_id: str | None = None
    exclusion_reason: str | None = None


def lookup(client: CachedClient, siren: str) -> dict | None:
    """The register record of one SIREN, or None when the register doesn't have it."""
    body = client.get_json(URL, {"q": siren, "per_page": 1}, key=f"siren-{siren}")
    results = body.get("results") or []
    return results[0] if results and results[0].get("siren") == siren else None


def from_register(result: dict, source: str, via: str) -> Company:
    siege = result.get("siege") or {}
    revenue, revenue_year = latest_revenue(result.get("finances"))
    return Company(
        siren=result["siren"],
        name=result.get("nom_complet") or result.get("nom_raison_sociale") or "",
        source=source,
        via=via,
        active=result.get("etat_administratif") == "A",
        address=siege.get("adresse"),
        postcode=siege.get("code_postal"),
        department=siege.get("departement"),
        region=siege.get("region"),
        lat=_float(siege.get("latitude")),
        lon=_float(siege.get("longitude")),
        naf=result.get("activite_principale"),
        band=result.get("tranche_effectif_salarie"),
        band_year=result.get("annee_tranche_effectif_salarie"),
        category=result.get("categorie_entreprise"),
        created=result.get("date_creation"),
        establishments_open=result.get("nombre_etablissements_ouverts"),
        revenue=revenue,
        revenue_year=revenue_year,
        managers=list(result.get("dirigeants") or []),
    )


def attach_rge(company: Company, sites: list[RgeSite]) -> None:
    """Add a company's RGE establishments: domains and contact details."""
    for site in sorted(sites, key=lambda s: s.siret):
        company.sirets.append(site.siret)
        company.domains |= site.domains
        for values, value in [
            (company.phones, site.phone), (company.emails, site.email),
            (company.websites, site.website),
        ]:  # fmt: skip
            if value and value not in values:
                values.append(value)
        if company.lat is None:
            company.lat, company.lon = _float(site.lat), _float(site.lon)
    if not company.name and sites:
        company.name = sites[0].name


def latest_revenue(finances: dict | None) -> tuple[float | None, str | None]:
    years = sorted((y for y, f in (finances or {}).items() if (f or {}).get("ca") is not None))
    return (float(finances[years[-1]]["ca"]), years[-1]) if years else (None, None)


def bands_from(min_band: str) -> list[str]:
    """Every known band code at or above `min_band`."""
    return [code for code in BANDS if code >= min_band]


def register_search(
    client: CachedClient, second: SecondSource, limit: int | None = None
) -> tuple[list[dict], dict]:
    """Active companies with an installer NAF code, at least the minimum band, and an
    energy word in the name. Returns the matches and counts for the funnel."""
    stats = {"searched": 0, "name_match": 0, "truncated_bands": []}
    matches: list[dict] = []
    seen: set[str] = set()
    for band in bands_from(second.min_headcount_band):
        params = {
            "activite_principale": ",".join(second.naf_codes),
            "tranche_effectif_salarie": band,
            "etat_administratif": "A",
            "per_page": PER_PAGE,
        }
        page = 1
        while True:
            body = client.get_json(URL, {**params, "page": page})
            if page == 1:
                stats["searched"] += body.get("total_results", 0)
                if body.get("total_results", 0) > RESULT_CAP:
                    stats["truncated_bands"].append(band)
            for result in body.get("results") or []:
                if result["siren"] in seen:
                    continue
                seen.add(result["siren"])
                if name_matches(result.get("nom_complet") or "", second.name_keywords):
                    matches.append(result)
            if limit is not None and len(matches) >= limit:
                stats["name_match"] = len(matches[:limit])
                return matches[:limit], stats
            if page >= body.get("total_pages", 0) or page * PER_PAGE >= RESULT_CAP:
                break
            page += 1
    stats["name_match"] = len(matches)
    return matches, stats


def person_search(client: CachedClient, surname: str, first_names: str, birth: str) -> list[dict]:
    """Companies whose officers include this person (birth = "YYYY-MM"). The API matches
    loosely, so callers must check each result's officers themselves."""
    year, month = birth.split("-")
    last_day = calendar.monthrange(int(year), int(month))[1]
    params = {
        "nom_personne": surname,
        "prenoms_personne": first_names,
        "date_naissance_personne_min": f"{year}-{month}-01",
        "date_naissance_personne_max": f"{year}-{month}-{last_day}",
        "per_page": PER_PAGE,
    }
    return client.get_json(URL, params).get("results") or []


def normalize(text: str) -> str:
    """Upper case, no accents, only letters, digits and single spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split())


def name_matches(name: str, keywords: list[str]) -> bool:
    """True when one keyword appears in `name` as a whole word ("pac" not in "espace")."""
    padded = f" {normalize(name)} "
    return any(f" {normalize(k)} " in padded for k in keywords if normalize(k))


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
