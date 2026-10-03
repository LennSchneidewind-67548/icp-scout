"""Writes the synthetic model recordings: `python fixtures/llm/make_fixtures.py`.

The research agent runs in record mode against a scripted client that answers
in the exact shape of a Messages API response (`message.to_dict()`), so the
recordings carry the same keys a live run would. Re-run this after any change
to the prompt, the tools or the config: the keys change with them.

Three fictional groups from fixtures/sources/, each exercising one path:
- BRISE MARINE ENERGIES: clean; the server pauses mid-research (`pause_turn`),
  so the lead is two calls.
- VALLON THERMIQUE: no website; growth and tech maturity are not found.
- CAP HORIZON SOLAIRE: one piece of evidence cites a page that was never
  retrieved (flagged `unverified_url`).

Every company, site and page is made up (`.example` domains). French quotes
carry their English translation in `quote_en`, and in the comments below.

WP6: the three groups are then scored and exported. The sequences come from
`SEQUENCES` (French, the English in each `*_en` field); the sample export is
copied to fixtures/export/.
"""

import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from conftest import TODAY, FakeApis, ScriptedClient

from icp_scout import config, export, research, score, sourcing
from icp_scout.enrich import agent
from icp_scout.enrich.agent import REGISTRY_URL, TOOL
from icp_scout.llm import LLM

HERE = Path(__file__).parent
MODEL = "claude-opus-5-5"
GROUPS = ["g900000010", "g900000060", "g900000110"]
CLOCK = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def message(n: int, content: list[dict], stop: str, usage: dict) -> dict:
    return {
        "id": f"msg_synthetic_{n:04d}",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "stop_details": None,
        "usage": {
            "input_tokens": usage.get("input", 0),
            "cache_creation_input_tokens": usage.get("write", 0),
            "cache_read_input_tokens": usage.get("read", 0),
            "output_tokens": usage.get("output", 0),
            "server_tool_use": {
                "web_search_requests": usage.get("searches", 0),
                "web_fetch_requests": usage.get("fetches", 0),
            },
            "service_tier": "standard",
        },
    }


def thinking() -> dict:
    return {"type": "thinking", "thinking": "", "signature": "synthetic-signature"}


def text(t: str) -> dict:
    return {"type": "text", "text": t}


def search(n: str, query: str, results: list[tuple[str, str]]) -> list[dict]:
    return [
        {"type": "server_tool_use", "id": f"srvtoolu_{n}", "name": "web_search",
         "input": {"query": query}},
        {"type": "web_search_tool_result", "tool_use_id": f"srvtoolu_{n}", "content": [
            {"type": "web_search_result", "url": url, "title": title,
             "encrypted_content": "c3ludGhldGlj", "page_age": None}
            for url, title in results
        ]},
    ]  # fmt: skip


def fetch(n: str, url: str, title: str, page: str) -> list[dict]:
    return [
        {"type": "server_tool_use", "id": f"srvtoolu_{n}", "name": "web_fetch",
         "input": {"url": url}},
        {"type": "web_fetch_tool_result", "tool_use_id": f"srvtoolu_{n}", "content": {
            "type": "web_fetch_result", "url": url, "retrieved_at": "2026-09-29T12:00:00Z",
            "content": {"type": "document", "title": title, "citations": None,
                        "source": {"type": "text", "media_type": "text/plain", "data": page}},
        }},
    ]  # fmt: skip


def record(n: str, answer: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_{n}", "name": TOOL, "input": answer}


def signal(value, rationale, *evidence) -> dict:
    return {
        "value": value,
        "found": bool(evidence),
        "rationale_en": rationale,
        "evidence": [{"quote": q, "quote_en": en, "url": u} for q, en, u in evidence],
    }


# BRISE MARINE ENERGIES: clean, with a pause_turn.
BRISE = "https://www.brise-marine.example"
BRISE_HOME = (
    "Brise Marine Energies, installateur RGE a Quimper depuis 2010. Pompes a chaleur "
    "air-eau et panneaux solaires photovoltaiques pour particuliers et professionnels. "
    "Demandez votre devis gratuit en ligne : simulateur d'economies d'energie. "
    "Une equipe de 70 techniciens et conseillers."
)  # Brise Marine Energies, RGE installer in Quimper since 2010. Air-to-water heat
# pumps and solar PV panels for homes and businesses. Ask for your free quote
# online: energy savings simulator. A team of 70 technicians and advisers.
BRISE_JOBS = (
    "Nous recrutons : technicien installateur pompe a chaleur (CDI, Quimper), "
    "commercial terrain photovoltaique (CDI, Brest)."
)  # We are hiring: heat pump installation technician (permanent, Quimper), field
# sales rep for solar PV (permanent, Brest).


def brise(call: int) -> tuple[list[dict], str, dict]:
    if call == 0:
        return [
            thinking(),
            text("I'll start with the website the registry lists."),
            *fetch("b1", BRISE, "Brise Marine Energies", BRISE_HOME),
            {"type": "server_tool_use", "id": "srvtoolu_b2", "name": "web_search",
             "input": {"query": "Brise Marine Energies recrutement Quimper"}},
        ], "pause_turn", {"input": 1850, "write": 2400, "output": 310, "fetches": 1}  # fmt: skip
    answer = {
        "website": BRISE,
        "signals": {
            "size_fit": signal(
                1, "The site states a team of 70, inside the 30-300 band.",
                ("Une equipe de 70 techniciens et conseillers.",
                 "A team of 70 technicians and advisers.", BRISE),
            ),
            "product_mix": signal(
                1, "Installs both air-to-water heat pumps and solar PV.",
                ("Pompes a chaleur air-eau et panneaux solaires photovoltaiques",
                 "Air-to-water heat pumps and solar PV panels", BRISE),
            ),
            "growth": signal(
                1, "Two open permanent roles, in installation and in sales.",
                ("Nous recrutons : technicien installateur pompe a chaleur (CDI, Quimper)",
                 "We are hiring: heat pump installation technician (permanent, Quimper)",
                 f"{BRISE}/recrutement"),
            ),
            "tech_maturity": signal(
                1, "Online quote request and a savings simulator on its own site.",
                ("Demandez votre devis gratuit en ligne : simulateur d'economies d'energie.",
                 "Ask for your free quote online: energy savings simulator.", BRISE),
            ),
        },
        "facts": {"product_lines": ["heat_pump", "solar"], "headcount_stated": 70,
                  "open_roles": ["heat pump installation technician", "field sales rep, solar PV"],
                  "tools_seen": []},
        "notes_en": "Single company, founded 2010, hiring in Quimper and Brest.",
    }  # fmt: skip
    return [
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_b2", "content": [
            {"type": "web_search_result", "url": f"{BRISE}/recrutement",
             "title": "Recrutement - Brise Marine Energies", "encrypted_content": "c3ludGhldGlj",
             "page_age": None},
        ]},
        *fetch("b3", f"{BRISE}/recrutement", "Recrutement", BRISE_JOBS),
        thinking(),
        record("b4", answer),
    ], "tool_use", {"input": 3900, "read": 2400, "output": 1450, "searches": 1, "fetches": 1}  # fmt: skip


# VALLON THERMIQUE: no website found; two signals not found.
def vallon(call: int) -> tuple[list[dict], str, dict]:
    registry = REGISTRY_URL.format(siren="900000060")
    answer = {
        "website": None,
        "signals": {
            "size_fit": signal(
                0.5, "Three companies of 10-19 staff each: about 30-57 together, "
                "at the lower edge of the band.",
                ("Tranche d'effectif salarie : 10 a 19 salaries",
                 "Headcount band: 10 to 19 employees", registry),
            ),
            "product_mix": signal(
                1, "The group is certified for both heat pumps and solar PV.",
                ("Pompe a chaleur : chauffage ; Panneaux solaires photovoltaiques",
                 "Heat pump: heating; solar PV panels", registry),
            ),
            "growth": signal(0, "No job ads or new sites found."),
            "tech_maturity": signal(0, "No own website found."),
        },
        "facts": {"product_lines": ["heat_pump", "solar"], "headcount_stated": None,
                  "open_roles": [], "tools_seen": []},
        "notes_en": "Three companies with one manager; no web presence found. A namesake "
                    "in another region was ruled out.",
    }  # fmt: skip
    return [
        thinking(),
        *search("v1", "Vallon Thermique Grenoble pompe a chaleur", [
            ("https://annuaire-fictif.example/vallon-thermique-38000", "Vallon Thermique - annuaire"),
            ("https://vallon-thermique-lyon.example", "Vallon Thermique Lyon"),
        ]),
        record("v2", answer),
    ], "tool_use", {"input": 2600, "write": 2400, "output": 1100, "searches": 1}  # fmt: skip


# CAP HORIZON SOLAIRE: one quote cites a page that was never retrieved.
CAP = "https://www.caphorizon-solaire.example"
CAP_HOME = (
    "Cap Horizon Solaire, votre installateur a Avignon : photovoltaique, pompes a chaleur "
    "et bornes de recharge. 35 collaborateurs a votre service."
)  # Cap Horizon Solaire, your installer in Avignon: solar PV, heat pumps and EV
# chargers. 35 staff at your service.


def cap(call: int) -> tuple[list[dict], str, dict]:
    answer = {
        "website": CAP,
        "signals": {
            "size_fit": signal(
                1, "The site states 35 staff, inside the band.",
                ("35 collaborateurs a votre service.", "35 staff at your service.", CAP),
            ),
            "product_mix": signal(
                1, "Installs solar PV and heat pumps, plus EV chargers.",
                ("photovoltaique, pompes a chaleur et bornes de recharge",
                 "solar PV, heat pumps and EV chargers", CAP),
            ),
            "growth": signal(0, "No job ads or new sites found."),
            "tech_maturity": signal(
                1, "An online solar simulator.",
                ("Simulez votre installation solaire en 2 minutes",
                 "Simulate your solar installation in 2 minutes", f"{CAP}/simulateur"),
            ),
        },
        "facts": {"product_lines": ["solar", "heat_pump", "ev_chargers"],
                  "headcount_stated": 35, "open_roles": [], "tools_seen": []},
        "notes_en": "Two companies sharing a phone number: the installer and a fitting company.",
    }  # fmt: skip
    return [
        thinking(),
        *search("c1", "Cap Horizon Solaire Avignon", [(CAP, "Cap Horizon Solaire")]),
        *fetch("c2", CAP, "Cap Horizon Solaire", CAP_HOME),
        record("c3", answer),
    ], "tool_use", {"input": 3100, "write": 2400, "output": 1200, "searches": 1, "fetches": 1}  # fmt: skip


SCRIPTS = {"BRISE MARINE ENERGIES": brise, "VALLON THERMIQUE": vallon, "CAP HORIZON SOLAIRE": cap}


def script(params: dict) -> dict:
    first = params["messages"][0]["content"]
    name = next(n for n in SCRIPTS if f'"group_name": "{n}"' in first)
    call = sum(m["role"] == "assistant" for m in params["messages"])
    content, stop, usage = SCRIPTS[name](call)
    return message(len(SCRIPTS) * call + list(SCRIPTS).index(name), content, stop, usage)


def market(data_dir: Path) -> None:
    """The WP1 pipeline on the source fixtures, as the research tests run it."""
    icp = config.load(ROOT / "config" / "icp.example.yaml")
    transport = httpx.MockTransport(FakeApis())
    sourcing.run(icp, data_dir, today=TODAY, rate_per_s=0, log=lambda _: None,
                 transport=transport)  # fmt: skip


# WP6: one 3-touch sequence per group, as the model would answer. French copy; the
# English is in each *_en field.

SEQUENCES = {
    "Brise Marine Energies": {
        "hook_evidence": 3,
        "email_1_subject": "Vos recrutements de techniciens PAC",
        "email_1_subject_en": "Your heat pump technician hiring",
        "email_1_body": (
            "Bonjour,\n\nVous écrivez « Nous recrutons : technicien installateur pompe a "
            "chaleur ». Chaque nouveau technicien, ce sont plus de devis à chiffrer. Helio Desk réunit CRM, "
            "dimensionnement et devis au même endroit. Comment vos devis sont-ils faits "
            "aujourd'hui ?\n\nSi ce n'est pas le sujet, dites-le-moi et je n'écrirai plus."
        ),
        "email_1_body_en": (
            'Hello,\n\nYou write "We are hiring: heat pump installation technician". Every '
            "new technician means more quotes to price. Helio Desk brings CRM, system sizing and "
            "quoting into one place. How are your quotes done today?\n\nIf this isn't a "
            "topic for you, tell me and I won't write again."
        ),
        "email_2_body": (
            "Bonjour,\n\nVous posez du photovoltaïque et des pompes à chaleur : deux "
            "dimensionnements, un seul devis avec Helio Desk. Un échange de 15 minutes ?"
            "\n\nUn simple « non » suffit pour ne plus recevoir de message."
        ),
        "email_2_body_en": (
            "Hello,\n\nYou install solar PV and heat pumps: two system sizings, one quote "
            'with Helio Desk. A 15-minute call?\n\nA simple "no" is enough to stop '
            "these messages."
        ),
        "linkedin": (
            "Bonjour, je travaille chez Helio Desk, un outil de devis pour installateurs "
            "PAC et solaire. J'ai vu vos recrutements : ravi d'échanger."
        ),
        "linkedin_en": (
            "Hello, I work at Helio Desk, a quoting tool for heat pump and solar "
            "installers. I saw your hiring: happy to connect."
        ),
    },
    "Vallon Thermique": {
        "hook_evidence": 2,
        "email_1_subject": "Pompes à chaleur et devis",
        "email_1_subject_en": "Heat pumps and quotes",
        "email_1_body": (
            "Bonjour,\n\nVotre entreprise est certifiée RGE pour les pompes à chaleur. "
            "Helio Desk aide les installateurs à passer de la visite au devis signé plus "
            "vite. Est-ce un sujet pour vous ?\n\nSi non, dites-le-moi et je n'écrirai plus."
        ),
        "email_1_body_en": (
            "Hello,\n\nYour company is RGE-certified for heat pumps. Helio Desk helps "
            "installers go from the site visit to a signed quote faster. Is this a topic "
            "for you?\n\nIf not, tell me and I won't write again."
        ),
        "email_2_body": (
            "Bonjour,\n\nUn devis PAC demande un dimensionnement précis. Helio Desk le "
            "calcule à partir de la visite. Je vous montre en 15 minutes ?\n\nUn « non » "
            "suffit pour ne plus recevoir de message."
        ),
        "email_2_body_en": (
            "Hello,\n\nA heat pump quote needs a precise system sizing. Helio Desk works it "
            'out from the site visit. Shall I show you in 15 minutes?\n\nA "no" is '
            "enough to stop these messages."
        ),
        "linkedin": (
            "Bonjour, je travaille chez Helio Desk, un outil pour installateurs de pompes à "
            "chaleur. Ravi d'échanger avec vous."
        ),
        "linkedin_en": (
            "Hello, I work at Helio Desk, a tool for heat pump installers. Happy to connect "
            "with you."
        ),
    },
    "Cap Horizon Solaire": {
        "hook_evidence": 2,
        "email_1_subject": "Votre activité solaire",
        "email_1_subject_en": "Your solar business",
        "email_1_body": (
            "Bonjour,\n\nVous installez des panneaux photovoltaïques. Helio Desk réunit le "
            "suivi des prospects, l'étude et le devis dans un seul outil. Combien de devis "
            "faites-vous par mois ?\n\nSi ce n'est pas le sujet, dites-le-moi et je "
            "n'écrirai plus."
        ),
        "email_1_body_en": (
            "Hello,\n\nYou install solar PV panels. Helio Desk brings lead follow-up, the "
            "system study and the quote into one tool. How many quotes do you do a month?"
            "\n\nIf this isn't a topic for you, tell me and I won't write again."
        ),
        "email_2_body": (
            "Bonjour,\n\nVotre simulateur solaire en ligne amène des demandes : Helio "
            "Desk les range dans un CRM sans ressaisie. Un échange de 15 minutes ?\n\nUn « non » "
            "suffit pour ne plus recevoir de message."
        ),
        "email_2_body_en": (
            "Hello,\n\nYour online solar simulator brings in requests: Helio Desk files "
            'them in a CRM with no re-typing. A 15-minute call?\n\nA "no" is enough to stop '
            "these messages."
        ),
        "linkedin": (
            "Bonjour, je travaille chez Helio Desk, un outil de devis pour installateurs "
            "solaires. Ravi d'échanger."
        ),
        "linkedin_en": (
            "Hello, I work at Helio Desk, a quoting tool for solar installers. Happy to connect."
        ),
    },
}


def sequence_script(params: dict) -> dict:
    prompt = params["messages"][0]["content"]
    name = next(n for n in SEQUENCES if f'"company": "{n}"' in prompt)
    n = list(SEQUENCES).index(name)
    call = {"type": "tool_use", "id": f"toolu_seq_{n}", "name": export.TOOL,
            "input": SEQUENCES[name]}  # fmt: skip
    return message(100 + n, [call], "tool_use", {"input": 2000, "output": 600})


def sample_export(icp, data_dir: Path) -> None:
    """Research (replayed), score and export the three groups; copy the sample export."""
    research.run(icp, data_dir, mode="replay", recordings_dir=HERE, group_ids=GROUPS,
                 log=lambda _: None)  # fmt: skip
    score.run(icp, data_dir)
    drafts = export.run(icp, data_dir, mode="record", recordings_dir=HERE,
                        client=ScriptedClient(sequence_script), log=print)  # fmt: skip
    sample = ROOT / "fixtures" / "export"
    sample.mkdir(exist_ok=True)
    for name in ("hubspot_companies.csv", "hubspot_contacts.csv", "sequences.md"):
        (sample / name).write_bytes((data_dir / "export" / name).read_bytes())
    print(f"{len(drafts)} sequences, sample export in {sample.relative_to(ROOT)}")


def main() -> None:
    icp = config.load(ROOT / "config" / "icp.example.yaml")
    out = HERE / "research"
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(HERE / "sequence", ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        market(Path(tmp))
        client = ScriptedClient(script)
        llm = LLM(HERE, "record", client=client, clock=lambda: CLOCK)
        leads = research.shortlist(Path(tmp), GROUPS, None)
        for lead in leads:
            result = agent.research(icp, llm, lead)
            print(lead["group_id"], result["status"], [f["code"] for f in result["flags"]])
        sample_export(icp, Path(tmp))
    print(f"{len(list(out.glob('*.json')))} recordings in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
