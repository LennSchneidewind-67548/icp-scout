"""Writes the synthetic sourcing fixtures: `python fixtures/sources/make_fixtures.py`.

Fictional companies in the exact shape of the two APIs' responses. Every SIREN
is made up and fails the Luhn check that real SIRENs pass, so none can be a real
company. Each company exists to exercise one rule of the WP1 pipeline.

French words in the data, for reviewers who don't read French:
"Pompe à chaleur : chauffage" = heat pump: heating; "Panneaux solaires
photovoltaïques" = solar PV panels; "Chauffage et/ou eau chaude solaire" =
solar heating and/or hot water; "Pompe à chaleur : eau chaude sanitaire" =
heat pump: domestic hot water (not a target domain); "Gérant" = managing
director; "Président" = chairman; "Commissaire aux comptes titulaire /
suppléant" = statutory auditor / deputy auditor; "rue" = street.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
PAC = "Pompe à chaleur : chauffage"
PV = "Panneaux solaires photovoltaïques"
ST = "Chauffage et/ou eau chaude solaire"
PAC_ECS = "Pompe à chaleur : eau chaude sanitaire"
ACTIVE, EXPIRED = "2029-06-30", "2024-01-31"
DIRECTORY = "https://www.annuaire-fictif.example/entreprises/"


def luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def fake_siren(n: int) -> str:
    """A 9-digit number that fails Luhn, so it can't be a real SIREN."""
    siren = f"9{n:07d}0"
    return siren if not luhn_ok(siren) else siren[:-1] + "1"


def person(nom, prenoms, born, qualite="Gérant"):
    return {
        "nom": nom,
        "prenoms": prenoms,
        "annee_de_naissance": born[:4],
        "date_de_naissance": born,
        "qualite": qualite,
        "nationalite": None,
        "type_dirigeant": "personne physique",
    }


def entity(siren, denomination, qualite="Président"):
    return {
        "siren": siren,
        "denomination": denomination,
        "qualite": qualite,
        "type_dirigeant": "personne morale",
    }


AUDITOR = entity(fake_siren(900), "CABINET VERIF COMPTES", "Commissaire aux comptes titulaire")
AUDITOR_PERSON = person("MARTEL", "JEAN", "1960-01", "Commissaire aux comptes suppléant")
DURANDAL = person("DURANDAL (DURANDAL)", "AURÉLIE MARIE", "1975-03")
DURANDAL_SPELT = person("DURANDAL", "Aurelie", "1975-03", "Président")
DURANDAL_OTHER = person("DURANDAL", "AURELIE", "1980-07")
HOLDING = fake_siren(2)  # the second company below

# key, name, NAF, band, managers, address, extra register fields, RGE sites
# (domains, phone, website, qualification end). No sites = not in the RGE registry.
COMPANIES = [
    # Inside the band on its own, both product lines, own website, two establishments.
    (
        "brise",
        "BRISE MARINE ENERGIES",
        "43.22B",
        "21",
        [person("KERJEAN", "YANN", "1970-05")],
        "4 QUAI DES EMBRUNS 29200 BREST",
        {"nombre_etablissements_ouverts": 2},
        [
            ({PAC, PV}, "02 98 00 00 01", "https://www.brise-marine.example", ACTIVE),
            ({ST, PAC_ECS}, "02 98 00 00 02", "www.brise-marine.example/agence", ACTIVE),
        ],
    ),
    # A holding (not RGE) with three RGE subsidiaries of 10-19 staff each.
    (
        "holding",
        "GROUPE LUMEN HOLDING",
        "70.10Z",
        "01",
        [person("LUMEN", "PAUL", "1968-09")],
        "1 PLACE DU PHARE 44000 NANTES",
        {},
        [],
    ),
    (
        "lumen_o",
        "LUMEN CHAUFFAGE OUEST",
        "43.22B",
        "11",
        [entity(HOLDING, "GROUPE LUMEN HOLDING"), AUDITOR],
        "10 RUE DU LEVANT 35000 RENNES",
        {},
        [({PAC}, "02 99 00 00 10", None, ACTIVE)],
    ),
    (
        "lumen_e",
        "LUMEN SOLAIRE EST",
        "43.21A",
        "11",
        [entity(HOLDING, "GROUPE LUMEN HOLDING")],
        "20 RUE DU COUCHANT 67000 STRASBOURG",
        {},
        [({PV}, "03 88 00 00 20", None, ACTIVE)],
    ),
    (
        "lumen_s",
        "LUMEN THERMIE SUD",
        "43.22B",
        "11",
        [entity(HOLDING, "GROUPE LUMEN HOLDING")],
        "30 RUE DU MIDI 13001 MARSEILLE",
        {},
        [({PAC, ST}, "04 91 00 00 30", None, ACTIVE)],
    ),
    # Same physical-person manager, spelled two ways; a non-RGE sister only the
    # person search finds; a property company of the same person (wrong NAF);
    # a namesake born in another month.
    (
        "vallon_t",
        "VALLON THERMIQUE",
        "43.22B",
        "11",
        [DURANDAL],
        "5 CHEMIN DU VALLON 38000 GRENOBLE",
        {},
        [({PAC}, "04 76 00 00 40", None, ACTIVE)],
    ),
    (
        "vallon_p",
        "VALLON PHOTOVOLTAIQUE",
        "43.21A",
        "11",
        [DURANDAL_SPELT],
        "7 CHEMIN DU VALLON 38000 GRENOBLE",
        {},
        [({PV}, "04 76 00 00 41", None, ACTIVE)],
    ),
    (
        "vallon_s",
        "VALLON SERVICES CHAUFFAGE",
        "43.22B",
        "11",
        [DURANDAL],
        "9 CHEMIN DU VALLON 38000 GRENOBLE",
        {},
        [],
    ),
    (
        "vallon_sci",
        "SCI LES TILLEULS DU VALLON",
        "68.20B",
        None,
        [DURANDAL],
        "9 CHEMIN DU VALLON 38000 GRENOBLE",
        {},
        [],
    ),
    (
        "namesake",
        "ATELIERS DURANDAL",
        "43.22B",
        "11",
        [DURANDAL_OTHER],
        "3 RUE HAUTE 21000 DIJON",
        {},
        [({PAC}, "03 80 00 00 42", None, ACTIVE)],
    ),
    # Same phone, written two ways.
    (
        "cap",
        "CAP HORIZON SOLAIRE",
        "43.21A",
        "12",
        [person("ROCHE", "LUC", "1981-02")],
        "2 RUE DU SOLEIL 84000 AVIGNON",
        {},
        [({PV}, "04 90 11 22 33", None, ACTIVE)],
    ),
    (
        "horizon",
        "HORIZON POSE",
        "43.22B",
        "01",
        [person("ROCHE", "ANNE", "1983-04")],
        "8 RUE DU SOLEIL 84000 AVIGNON",
        {},
        [({PAC}, "+33 4 90 11 22 33", None, ACTIVE)],
    ),
    # Same own website.
    (
        "eco_a",
        "ECOTHERM ARTOIS",
        "43.22B",
        "11",
        [person("LEFORT", "MARC", "1972-06")],
        "1 RUE D'ARRAS 62000 ARRAS",
        {},
        [({PAC}, "03 21 00 00 50", "https://ecotherm.example", ACTIVE)],
    ),
    (
        "eco_f",
        "ECOTHERM FLANDRES",
        "43.22B",
        "11",
        [person("DEWAELE", "SOPHIE", "1979-11")],
        "2 RUE DE LILLE 59000 LILLE",
        {},
        [({PAC}, "03 20 00 00 51", "http://www.ecotherm.example/nord", ACTIVE)],
    ),
    # Same address, two companies: linked.
    (
        "bleu_c",
        "ATELIER BLEU CHALEUR",
        "43.22B",
        "12",
        [person("BLEU", "ALAIN", "1966-08")],
        "12 RUE DES FICTIFS 59000 LILLE",
        {},
        [({PAC}, "03 20 00 00 60", None, ACTIVE)],
    ),
    (
        "bleu_s",
        "ATELIER BLEU SOLAIRE",
        "43.21A",
        "03",
        [person("AZUR", "CLAIRE", "1990-10")],
        "12 rue des Fictifs 59000 Lille",
        {},
        [({PV}, "03 20 00 00 61", None, ACTIVE)],
    ),
    # Two companies with the same auditors (a firm and a person): never linked.
    (
        "rivage",
        "RIVAGE CLIM",
        "43.22B",
        "12",
        [person("MARIN", "LEA", "1985-01"), AUDITOR, AUDITOR_PERSON],
        "3 BOULEVARD DE LA MER 06000 NICE",
        {},
        [({PAC}, "04 93 00 00 70", None, ACTIVE)],
    ),
    (
        "pic",
        "PIC SOLAIRE",
        "43.21A",
        "12",
        [person("MONT", "HUGO", "1977-12"), AUDITOR, AUDITOR_PERSON],
        "4 ROUTE DU COL 65000 TARBES",
        {},
        [({PV}, "05 62 00 00 71", None, ACTIVE)],
    ),
    # Dropped: closed, qualification expired (it comes back through the second
    # source: an installer NAF, 20-49 staff, an energy word), not in the register.
    (
        "closed",
        "ANCIEN CHAUFFAGE",
        "43.22B",
        "12",
        [person("VIEUX", "ROGER", "1950-01")],
        "1 RUE DU PASSE 75011 PARIS",
        {"etat_administratif": "C"},
        [({PAC}, "01 40 00 00 80", None, ACTIVE)],
    ),
    (
        "expired",
        "PERIME ENERGIE",
        "43.22B",
        "12",
        [person("FIN", "JULES", "1965-03")],
        "2 RUE DU PASSE 75011 PARIS",
        {},
        [({PAC}, "01 40 00 00 81", None, EXPIRED)],
    ),
    ("missing", None, None, None, [], None, {}, [({PV}, "01 40 00 00 82", None, ACTIVE)]),
    # Headcount unknown, and above the band.
    (
        "unknown",
        "MYSTERE SOLAIRE",
        "43.21A",
        "NN",
        [person("NUIT", "EVA", "1988-05")],
        "5 IMPASSE DU BROUILLARD 29000 QUIMPER",
        {},
        [({PV}, "02 98 00 00 90", None, ACTIVE)],
    ),
    (
        "giga",
        "GIGAWATT INSTALLATIONS",
        "43.21A",
        "41",
        [person("GRAND", "VICTOR", "1960-07")],
        "100 AVENUE DE LA PUISSANCE 92000 NANTERRE",
        {"nombre_etablissements_ouverts": 12},
        [({PV, PAC}, "01 41 00 00 91", "https://gigawatt.example", ACTIVE)],
    ),
    # Second source: not RGE, installer NAF, 20-49 staff, energy word, created recently.
    (
        "nordwatt",
        "NORDWATT PHOTOVOLTAÏQUE",
        "43.21A",
        "12",
        [person("NORD", "IDA", "1992-02")],
        "6 RUE DU VENT 80000 AMIENS",
        {"date_creation": "2025-11-02"},
        [],
    ),
    # Register search hits that must not enter: "pac" inside "espace", no energy word.
    (
        "espace",
        "ESPACE BATIMENT CONFORT",
        "43.22B",
        "12",
        [person("CUBE", "TOM", "1974-09")],
        "7 RUE DU MUR 45000 ORLEANS",
        {},
        [],
    ),
    (
        "plomb",
        "PLOMBERIE GENERALE DU CENTRE",
        "43.22B",
        "12",
        [person("TUBE", "ZOE", "1971-03")],
        "8 RUE DU TUYAU 18000 BOURGES",
        {},
        [],
    ),
]

# 21 small companies whose only website is a directory profile page. Four of them
# sit in one business center, which is too crowded an address to link them.
for i in range(1, 22):
    address = (
        "1 AVENUE DU CENTRE D'AFFAIRES 69003 LYON" if i <= 4 else f"{i} RUE DES ARTISANS 69007 LYON"
    )
    COMPANIES.append(
        (f"artisan{i:02d}", f"ARTISAN FICTIF {i:02d}", "43.22B", "01",
         [person(f"ARTISAN{i:02d}", "PIERRE", "1980-01")], address, {},
         [({PAC}, f"04 72 00 01 {i:02d}", f"{DIRECTORY}artisan-fictif-{i:02d}", ACTIVE)])
    )  # fmt: skip


def register_record(n, siren, name, naf, band, managers, address, extra):
    postcode = address.split()[-2]
    record = {
        "siren": siren,
        "nom_complet": name,
        "nom_raison_sociale": name,
        "sigle": None,
        "nombre_etablissements": 1,
        "nombre_etablissements_ouverts": 1,
        "siege": {
            "activite_principale": naf,
            "adresse": address.upper(),
            "code_postal": postcode,
            "departement": postcode[:2],
            "region": "99",
            "etat_administratif": "A",
            "est_siege": True,
            "latitude": f"{45 + n / 100:.6f}",
            "longitude": f"{2 + n / 100:.6f}",
            "siret": siren + "00012",
            "tranche_effectif_salarie": band,
        },
        "activite_principale": naf,
        "categorie_entreprise": "PME",
        "date_creation": "2010-04-01",
        "dirigeants": managers,
        "etat_administratif": "A",
        "nature_juridique": "5710",
        "section_activite_principale": "F",
        "tranche_effectif_salarie": band,
        "annee_tranche_effectif_salarie": "2023" if band not in (None, "NN") else None,
        "finances": {"2023": {"ca": 1000000 + n * 1000, "resultat_net": 50000}},
    }
    record.update(extra)
    return record


def main():
    register, rows, index = [], [], {}
    for n, (key, name, naf, band, managers, address, extra, sites) in enumerate(COMPANIES, 1):
        siren = fake_siren(n)
        index[key] = siren
        if name:
            register.append(register_record(n, siren, name, naf, band, managers, address, extra))
        street, postcode, commune = (address or "1 RUE INCONNUE 75001 PARIS").rsplit(" ", 2)
        for s, (domains, phone, website, end) in enumerate(sites, 1):
            for domain in sorted(domains):
                rows.append({
                    "siret": f"{siren}{s:05d}",
                    "nom_entreprise": name or "ENTREPRISE DISPARUE",
                    "adresse": street.title(),
                    "code_postal": postcode,
                    "commune": commune,
                    "latitude": 45.0 + n / 100,
                    "longitude": 2.0 + n / 100,
                    "telephone": phone,
                    "email": f"contact@{key}.example",
                    "site_internet": website,
                    "domaine": domain,
                    "lien_date_debut": "2022-01-01",
                    "lien_date_fin": end,
                    "_score": None,
                })  # fmt: skip
    assert len(set(index.values())) == len(index) and HOLDING == index["holding"]
    assert not any(luhn_ok(siren) for siren in index.values())
    half = len(rows) // 2
    base = "https://data.ademe.fr/data-fair/api/v1/datasets/fictif000000/lines"
    pages = [
        {"total": len(rows), "next": f"{base}?size=10000&qs=fixture&after=1%2C{half}",
         "results": rows[:half]},
        {"total": len(rows), "results": rows[half:]},
    ]  # fmt: skip
    write("rge_lines_page1.json", pages[0])
    write("rge_lines_page2.json", pages[1])
    write("register.json", register)
    write("sirens.json", index)


def write(name, body):
    (HERE / name).write_text(
        json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
