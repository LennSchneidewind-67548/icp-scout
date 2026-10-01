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

    def to_dict(self, mode="python"):
        assert mode == "json", "a live response holds datetimes: use to_dict(mode='json')"
        return json.loads(json.dumps(self.message))


@pytest.fixture(scope="module")
def market_dir(tmp_path_factory):
    """data/ after `icp-scout source` on the source fixtures."""
    import sys

    sys.path.insert(0, str(ROOT / "fixtures" / "llm"))
    import make_fixtures  # imports this module, so not at the top

    data_dir = tmp_path_factory.mktemp("data")
    make_fixtures.market(data_dir)
    return data_dir


@pytest.fixture
def data_dir(market_dir, tmp_path):
    (tmp_path / "market.parquet").write_bytes((market_dir / "market.parquet").read_bytes())
    return tmp_path


# WP5: a small data/ for the demo, every file the app reads.

DEMO_IDS = ["size_fit", "product_mix", "growth", "tech_maturity"]
# group_id: (name, signal values in DEMO_IDS order or None if not researched, lat, lon,
# in segment). Config weights 3/3/2/2 put g2 first; size and product mix only put g1 first.
DEMO_GROUPS = {
    "g1": ("ALPHA SOLAIRE", [1, 1, 0, 0], 48.1, -1.7, True),
    "g2": ("BETA THERMIQUE", [0.5, 0.5, 1, 1], 45.8, 4.8, True),
    "g3": ("GAMMA ENERGIES", [1, 0, 1, 0], 43.6, 1.4, True),
    "g4": ("DELTA CLIM", None, 47.2, -1.6, True),
    "g5": ("EPSILON ELEC", None, 49.4, 1.1, False),
    "g6": ("ZETA OUTRE-MER", None, -21.1, 55.5, False),  # far off: not drawn
}
DEMO_KEY = "f" * 64  # the recording key of g1's research run


def demo_signal_rows() -> list[dict]:
    rows = []
    for gid, (name, values, *_rest) in DEMO_GROUPS.items():
        for sid, v in zip(DEMO_IDS, values or [], strict=False):
            found = v > 0
            ev = [{"quote": f"Texte {sid}", "quote_en": f"Text {sid}",
                   "url": f"https://{gid}.example/"}] if found else []  # fmt: skip
            rows.append({"group_id": gid, "name": name, "status": "ok", "signal": sid,
                         "value": float(v), "found": found, "rationale_en": f"Why {sid}",
                         "evidence": ev, "flags": [], "website": f"https://{gid}.example",
                         "notes_en": f"Notes on {name}", "reason": None})  # fmt: skip
    return rows


def demo_transcript() -> list[dict]:
    """g1's research run in the shape of the claude-code stream (French page text,
    English in the comments)."""

    def assistant(*blocks):
        return {"type": "assistant", "message": {"content": list(blocks)}}

    def result(tid, text):
        return {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": text}]}}  # fmt: skip

    record = {"website": "https://g1.example", "signals": {
        sid: {"value": 1.0, "found": True, "rationale_en": f"Why {sid}",
              "evidence": [{"quote": "Une equipe de 100 personnes",  # A team of 100 people
                            "quote_en": "A team of 100 people", "url": "https://g1.example/"}]}
        for sid in DEMO_IDS}, "facts": {}, "notes_en": ""}  # fmt: skip
    return [
        {"type": "system", "subtype": "init", "apiKeySource": "none"},
        assistant(
            {"type": "text", "text": "Starting with the website."},
            {
                "type": "tool_use",
                "id": "t1",
                "name": "WebFetch",
                "input": {"url": "https://g1.example/", "prompt": "Copy verbatim"},
            },
        ),
        result("t1", "Une equipe de 100 personnes"),  # A team of 100 people
        assistant(
            {
                "type": "tool_use",
                "id": "t2",
                "name": "WebSearch",
                "input": {"query": "ALPHA SOLAIRE recrutement"},
            }
        ),  # recruitment
        result("t2", "Pas de resultat"),  # No result
        assistant({"type": "tool_use", "id": "t3", "name": "StructuredOutput", "input": record}),
        {"type": "result", "subtype": "success", "usage": {}, "total_cost_usd": 0.12},
    ]


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory):
    import altair as alt
    import pandas as pd

    from icp_scout import score

    root = tmp_path_factory.mktemp("demo")
    d = root / "data"
    (d / "regrade").mkdir(parents=True)
    (d / "research").mkdir()
    (d / "insights").mkdir()
    pd.DataFrame([
        {"group_id": g, "name": name, "members": [g[1:]], "member_names": [name],
         "lat": lat, "lon": lon, "region": "84" if lon > 2 else "53", "in_segment": seg,
         "shortlisted": values is not None, "headcount_mid": 100.0, "pre_score": 0.5}
        for g, (name, values, lat, lon, seg) in DEMO_GROUPS.items()
    ]).to_parquet(d / "market.parquet", index=False)  # fmt: skip
    pd.DataFrame(demo_signal_rows()).to_parquet(d / "signals.parquet", index=False)
    (d / "regrade" / "g1.json").write_text(json.dumps({"group_id": "g1", "status": "ok",
        "result": {"headcount": 100, "headcount_basis_en": "The site says 100.",
                   "grades": {}, "phrases": {"size_fit": "~100 staff"}}}), encoding="utf-8")  # fmt: skip
    (d / "research" / "g1.json").write_text(json.dumps({"group_id": "g1", "status": "ok",
        "result": {"facts": {"headcount_stated": 100, "open_roles": [], "product_lines": [],
                             "tools_seen": []}}}), encoding="utf-8")  # fmt: skip
    (d / "funnel.json").write_text(json.dumps({"stages": []}), encoding="utf-8")
    spec = alt.Chart(pd.DataFrame({"x": [1], "y": [2]})).mark_bar().encode(x="x", y="y")
    (d / "insights" / "f1_funnel.vl.json").write_text(spec.to_json(), encoding="utf-8")
    ledger = {"lead": "g1", "purpose": "research", "key": DEMO_KEY, "backend": "claude-code",
              "model": "claude-opus-5-5", "input_tokens": 10, "cache_write_tokens": 100,
              "cache_read_tokens": 1000, "output_tokens": 50, "usd": 0.0,
              "notional_usd": 0.12}  # fmt: skip
    (d / "ledger.jsonl").write_text(json.dumps(ledger) + "\n", encoding="utf-8")
    rec = root / "recordings" / "research"
    rec.mkdir(parents=True)
    transcript = demo_transcript()
    (rec / f"{DEMO_KEY}.json").write_text(json.dumps({"request": {}, "transcript": transcript,
        "result": transcript[-1], "notional_usd": 0.12}), encoding="utf-8")  # fmt: skip
    score.run(config.load(ROOT / "config" / "icp.example.yaml"), d)
    return d
