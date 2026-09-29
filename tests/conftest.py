"""A fake of both open-data APIs over the synthetic fixtures in fixtures/sources/."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from icp_scout import config
from icp_scout.sources.sirene import normalize

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "fixtures" / "sources"
TODAY = date(2026, 9, 29)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeApis:
    """Answers like data.ademe.fr and recherche-entreprises.api.gouv.fr; counts calls."""

    def __init__(self):
        self.pages = [load("rge_lines_page1.json"), load("rge_lines_page2.json")]
        self.register = load("register.json")
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        p = dict(request.url.params)
        if request.url.host == "data.ademe.fr":
            if p.get("size") == "0":
                return httpx.Response(200, json={"total": 1000, "results": []})
            return httpx.Response(200, json=self.pages[1 if "after" in p else 0])
        if request.url.host == "recherche-entreprises.api.gouv.fr":
            return self.search(p)
        return httpx.Response(404)

    def search(self, p: dict) -> httpx.Response:
        pool = self.register
        if "q" in p:
            pool = [r for r in pool if r["siren"] == p["q"]]
        elif "activite_principale" in p:
            nafs = p["activite_principale"].split(",")
            bands = p["tranche_effectif_salarie"].split(",")
            pool = [
                r for r in pool
                if r["activite_principale"] in nafs and r["tranche_effectif_salarie"] in bands
                and r["etat_administratif"] == p.get("etat_administratif", "A")
            ]  # fmt: skip
        elif "nom_personne" in p:
            pool = [r for r in pool if any(self.person_hit(d, p) for d in r["dirigeants"])]
        else:
            return httpx.Response(400, json={"erreur": "no search parameter"})
        per_page, page = int(p.get("per_page", 10)), int(p.get("page", 1))
        return httpx.Response(200, json={
            "results": pool[(page - 1) * per_page : page * per_page],
            "total_results": len(pool),
            "page": page,
            "per_page": per_page,
            "total_pages": -(-len(pool) // per_page),
        })  # fmt: skip

    @staticmethod
    def person_hit(officer: dict, p: dict) -> bool:
        # Loose, like the real API: substring on names, a birth date range.
        born = (officer.get("date_de_naissance") or "") + "-15"
        return (
            officer.get("type_dirigeant") == "personne physique"
            and normalize(p["nom_personne"]) in normalize(officer["nom"])
            and normalize(p["prenoms_personne"]) in normalize(officer["prenoms"])
            and p["date_naissance_personne_min"] <= born <= p["date_naissance_personne_max"]
        )


@pytest.fixture
def fake_apis():
    return FakeApis()


@pytest.fixture
def icp():
    return config.load(ROOT / "config" / "icp.example.yaml")


@pytest.fixture
def sirens():
    return load("sirens.json")
