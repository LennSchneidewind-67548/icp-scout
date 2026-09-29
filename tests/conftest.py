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


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """The author's .env may point at the private case config: tests never read it."""
    from icp_scout import cli

    monkeypatch.setattr(cli, "load_env", lambda *a, **k: None)
    monkeypatch.delenv("ICP_SCOUT_CONFIG", raising=False)
    monkeypatch.delenv("ICP_SCOUT_RECORDINGS", raising=False)


@pytest.fixture
def fake_apis():
    return FakeApis()


@pytest.fixture
def icp():
    return config.load(ROOT / "config" / "icp.example.yaml")


@pytest.fixture
def sirens():
    return load("sirens.json")


class ScriptedClient:
    """Stands in for `anthropic.Anthropic()`: answers `beta.messages.stream(...)` from a
    script, in the shape of `message.to_dict()`. `script(params)` returns the answer."""

    def __init__(self, script):
        self.script = script
        self.requests = []
        self.beta = self
        self.messages = self

    def stream(self, **params):
        self.requests.append(json.loads(json.dumps(params)))
        return _Stream(self.script(params))


class _Stream:
    def __init__(self, message: dict):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self

    def to_dict(self):
        return json.loads(json.dumps(self.message))
