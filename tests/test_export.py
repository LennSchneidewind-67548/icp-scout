import csv
import json
import shutil
import sys

import pandas as pd
import pytest
from conftest import ROOT, ScriptedClient

from icp_scout import cli, export, score

RECORDINGS = ROOT / "fixtures" / "llm"
sys.path.insert(0, str(RECORDINGS))
import make_fixtures

DIRECTORY = "https://annuaire-fictif.example/fiche"  # listed by 21 companies


def manager(nom, prenoms, qualite="Gérant", kind="personne physique"):
    return {"nom": nom, "prenoms": prenoms, "qualite": qualite, "type_dirigeant": kind}


def company(gid, siren, band, managers, websites=(), **extra):
    return {"siren": siren, "name": f"Company {siren}", "group_id": gid, "band": band,
            "domains": [], "websites": list(websites), "phones": ["01 23 45 67 89"],
            "emails": [f"contact@{gid}.example"], "address": "1 RUE DE LA GARE 75001 PARIS",
            "postcode": "75001", "managers": json.dumps(managers, ensure_ascii=False),
            **extra}  # fmt: skip


@pytest.fixture
def export_dir(demo_dir, tmp_path, icp):
    """The WP5 demo data plus companies.parquet. g3 ties g1 on score; g2's only website
    is a directory page; g3's head company has no physical-person manager."""
    d = tmp_path / "data"
    shutil.copytree(demo_dir, d)
    signals = pd.read_parquet(d / "signals.parquet")
    g3 = signals["group_id"] == "g3"
    for sid, v in zip(["size_fit", "product_mix", "growth", "tech_maturity"], [1, 1, 0, 0]):
        signals.loc[g3 & (signals["signal"] == sid), "value"] = float(v)
    signals.loc[signals["group_id"] == "g2", "website"] = DIRECTORY
    signals.to_parquet(d / "signals.parquet", index=False)
    score.run(icp, d)
    rows = [
        company("g1", "1", "12", [manager("COMMISSAIRE", "X", "Commissaire aux comptes titulaire"),
                                  manager("LEFÈVRE", "HÉLÈNE, MARIE", "Président de SAS")]),
        company("g1", "11", "21", [manager("DURAND", "PAUL")]),  # the larger: the head
        company("g2", "2", "21", [manager("MARTIN", "LÉA")], [DIRECTORY]),
        company("g3", "3", "21", [manager(None, None, "Président", "personne morale")]),
        *(company("gx", f"9{i:02d}", "11", [], [DIRECTORY]) for i in range(20)),
    ]  # fmt: skip
    pd.DataFrame(rows).to_parquet(d / "companies.parquet", index=False)
    return d


def canned(**over) -> dict:
    seq = {"hook_evidence": 1, "email_1_subject": "Objet", "email_1_subject_en": "Subject",
           "email_1_body": "Bonjour, vous recrutez. Helio Desk aide. Pas intéressé ? Dites-le.",
           "email_1_body_en": "Hello, you are hiring. Helio Desk helps. Not interested? Say so.",
           "email_2_body": "Bonjour, une relance.", "email_2_body_en": "Hello, a follow-up.",
           "linkedin": "Bonjour, ravi d'échanger.", "linkedin_en": "Hello, happy to connect."}  # fmt: skip
    return {**seq, **over}


def answer(seq: dict) -> dict:
    call = {"type": "tool_use", "id": "toolu_1", "name": export.TOOL, "input": seq}
    return make_fixtures.message(1, [call], "tool_use", {"input": 100, "output": 50})


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# The queue and the CSV


def test_csv_one_row_per_queued_lead_with_bom_and_accents(icp, export_dir, tmp_path):
    export.run(icp, export_dir, recordings_dir=tmp_path / "rec",
               client=ScriptedClient(lambda p: answer(canned())), log=lambda _: None)  # fmt: skip
    path = export_dir / "export" / "hubspot_companies.csv"
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = {r["icp_registry_name"]: r for r in read_csv(path)}
    scored = pd.read_parquet(export_dir / "scored.parquet").set_index("name")
    queued = scored[scored["queue_rank"].notna()]
    assert set(rows) == set(queued.index)
    assert list(read_csv(path)[0]) == export.COMPANY_COLUMNS

    alpha, gamma = rows["ALPHA SOLAIRE"], rows["GAMMA ENERGIES"]
    assert alpha["Company name"] == "Alpha Solaire"
    assert queued.loc["ALPHA SOLAIRE", "score"] == queued.loc["GAMMA ENERGIES", "score"]
    for name, row in [("ALPHA SOLAIRE", alpha), ("GAMMA ENERGIES", gamma)]:
        assert int(row["icp_queue_rank"]) == queued.loc[name, "queue_rank"]
    # The head company is the largest; its manager is the contact, in a second file keyed
    # by the company's domain. Beta's manager has no domain to be associated by.
    contacts = read_csv(export_dir / "export" / "hubspot_contacts.csv")
    assert contacts == [{"Company Domain Name": "g1.example", "First Name": "Paul",
                         "Last Name": "Durand", "Job Title": "Gérant"}]  # fmt: skip
    assert (alpha["Street Address"], alpha["City"], alpha["Postal Code"]) == (
        "1 RUE DE LA GARE",
        "Paris",
        "75001",
    )
    assert alpha["Company Domain Name"] == "g1.example"
    assert alpha["icp_group_sirens"] == "1"
    assert "«Texte size_fit» (Text size_fit) https://g1.example/" in alpha["icp_evidence"]
    assert alpha["seq_1_body"] == canned()["email_1_body"]
    assert "Pas intéressé" in alpha["seq_1_body"]  # accents survive the round trip
    assert rows["BETA THERMIQUE"]["Company Domain Name"] == ""  # a directory is no domain


def test_a_lead_without_a_physical_person_manager_still_gets_its_row(icp, export_dir):
    leads = export.queue(export_dir)
    assert export.contact(leads.set_index("group_id").loc["g3", "head"]) is None
    rows = export.hubspot_rows(icp, export.leads_for_drafting(icp, export_dir, leads), {})
    g3 = next(r for r in rows if r["icp_registry_name"] == "GAMMA ENERGIES")
    assert g3["First Name"] == g3["Last Name"] == "" and g3["Company name"] == "Gamma Energies"
    assert g3 not in export.contact_rows(rows)  # HubSpot rejects a contact with no name


def test_contact_skips_auditors_and_takes_the_first_given_name():
    head = {"managers": json.dumps([manager("AUDIT", "A", "Commissaire aux comptes suppléant"),
                                    manager("LE GALL", "JEAN, MARIE", "Président de SAS")])}  # fmt: skip
    assert export.contact(head) == {"first_name": "Jean", "last_name": "Le Gall",
                                    "role": "Président de SAS",
                                    "role_en": "president (of the SAS)"}  # fmt: skip


# The sequence


def lead(**over) -> dict:
    evidence = [{"n": 1, "signal": "growth", "quote": "Nous recrutons", "quote_en": "We are hiring",
                 "url": "https://x.example/"}]  # fmt: skip
    return {"group_id": "g1", "display_name": "Alpha Solaire", "reason_en": "9.1 A | ~100 staff",
            "score": 9.1, "signals": [], "evidence": evidence, "facts": None, "role": "Gérant",
            **over}  # fmt: skip


def test_draft_validates_a_canned_answer_and_never_shows_the_score(icp, tmp_path):
    from icp_scout.llm import LLM

    client = ScriptedClient(lambda p: answer(canned()))
    out = export.draft(icp, LLM(tmp_path, "record", client=client), lead())
    assert out["status"] == "ok" and out["flags"] == [] and out["result"] == canned()
    prompt = client.requests[0]["messages"][0]["content"]
    assert "9.1" not in prompt and "~100 staff" in prompt and "Nous recrutons" in prompt


def test_draft_fails_an_answer_that_does_not_validate(icp, tmp_path):
    from icp_scout.llm import LLM

    bad = canned()
    del bad["linkedin_en"]
    client = ScriptedClient(lambda p: answer(bad))
    out = export.draft(icp, LLM(tmp_path, "record", client=client), lead())
    assert out["status"] == "failed" and out["reason"].startswith("invalid answer")


def test_checks_flag_length_informal_address_bad_hook_score_and_no_vendor(icp):
    flags = export.checks(icp, canned(linkedin="x" * 301, email_2_body="Tu veux voir ?",
                                      hook_evidence=4), lead())  # fmt: skip
    assert flags == ["linkedin: 301 characters (limit 300)", "hook_evidence 4 is no evidence item",
                     "informal address: tu"]  # fmt: skip
    assert "a score or tier in the copy" in export.checks(
        icp, canned(email_2_body="Votre note : 9,1/10."), lead()
    )
    assert "Helio Desk not named" in export.checks(icp, canned(email_1_body="Bonjour."), lead())
    long = canned(email_1_body=" ".join(["mot"] * 91) + " Helio Desk")
    assert export.checks(icp, long, lead())[0] == "email_1_body: 93 words (limit 90)"


# CLI and the committed recordings


def test_export_offline_without_a_recording_fails_with_the_miss(export_dir, tmp_path):
    with pytest.raises(SystemExit, match="--offline: no recording for sequence"):
        cli.main(["--data-dir", str(export_dir), "export", "--offline",
                  "--recordings", str(tmp_path / "empty")])  # fmt: skip


def test_the_sample_export_replays_offline(data_dir, market_dir):
    """Fails when the prompt or the fixtures changed: re-run make_fixtures.py."""
    shutil.copy(market_dir / "companies.parquet", data_dir)
    groups = [a for g in make_fixtures.GROUPS for a in ("--group", g)]
    cli.main(["--data-dir", str(data_dir), "research", "--offline",
              "--recordings", str(RECORDINGS), *groups])  # fmt: skip
    cli.main(["--data-dir", str(data_dir), "score"])
    cli.main(["--data-dir", str(data_dir), "export", "--offline",
              "--recordings", str(RECORDINGS)])  # fmt: skip
    for name in ("hubspot_companies.csv", "hubspot_contacts.csv", "sequences.md"):
        written = (data_dir / "export" / name).read_bytes()
        assert written == (ROOT / "fixtures" / "export" / name).read_bytes(), name
