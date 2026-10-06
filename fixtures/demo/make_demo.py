"""Writes a full-size, clearly fictional example `data/` directory.

    python fixtures/demo/make_demo.py [out_dir]        # default data/example

Every company, site and quote is invented: names are syllable pseudo-words, SIRENs
start with 000 (no real one does), sites end in `.example`. The market is the 34
groups of the source fixtures plus synthetic ones up to `--groups` (6,000); three of
the 34 have recorded research that replays offline, the shortlisted synthetic groups
carry templated research, and the real `score` and `insights` steps run on top. The
files are the ones `icp-scout source`, `research`, `regrade`, `score` and `insights`
write, so the demo reads them unchanged. No model call, no network.

Run the demo on it (all three variables, because a `.env` may point elsewhere):

    ICP_SCOUT_CONFIG=config/icp.example.yaml ICP_SCOUT_DATA=data/example \
    ICP_SCOUT_RECORDINGS=fixtures/llm streamlit run app/streamlit_app.py

A directory that holds a `market.parquet` but not the `.example-data` marker this
script writes is never touched, so a wrong path can't overwrite real data.
"""

import argparse
import hashlib
import json
import random
import shutil
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "fixtures" / "llm"))

import make_fixtures

from icp_scout import config, funnel, insights, prefilter, research, score
from icp_scout.llm import read_ledger, write_json
from icp_scout.sources.sirene import BANDS, band_mid

MARKER = ".example-data"
COMMAND = (
    "ICP_SCOUT_CONFIG=config/icp.example.yaml ICP_SCOUT_DATA=data/example "
    "ICP_SCOUT_RECORDINGS=fixtures/llm streamlit run app/streamlit_app.py"
)

# City, latitude, longitude, INSEE region, department, weight (roughly by size).
CITIES = [
    ("Paris", 48.86, 2.35, "11", "75", 10), ("Lyon", 45.76, 4.84, "84", "69", 7),
    ("Marseille", 43.30, 5.37, "93", "13", 7), ("Toulouse", 43.60, 1.44, "76", "31", 5),
    ("Nice", 43.70, 7.26, "93", "06", 4), ("Nantes", 47.22, -1.55, "52", "44", 5),
    ("Montpellier", 43.61, 3.88, "76", "34", 4), ("Strasbourg", 48.57, 7.75, "44", "67", 3),
    ("Bordeaux", 44.84, -0.58, "75", "33", 5), ("Lille", 50.63, 3.06, "32", "59", 5),
    ("Rennes", 48.11, -1.68, "53", "35", 4), ("Reims", 49.26, 4.03, "44", "51", 2),
    ("Le Havre", 49.49, 0.11, "28", "76", 2), ("Saint-Étienne", 45.44, 4.39, "84", "42", 2),
    ("Toulon", 43.12, 5.93, "93", "83", 3), ("Grenoble", 45.19, 5.72, "84", "38", 3),
    ("Dijon", 47.32, 5.04, "27", "21", 2), ("Angers", 47.47, -0.55, "52", "49", 3),
    ("Nîmes", 43.84, 4.36, "76", "30", 2), ("Clermont-Ferrand", 45.78, 3.09, "84", "63", 2),
    ("Le Mans", 48.00, 0.20, "52", "72", 2), ("Aix-en-Provence", 43.53, 5.45, "93", "13", 2),
    ("Brest", 48.39, -4.49, "53", "29", 2), ("Tours", 47.39, 0.69, "24", "37", 2),
    ("Amiens", 49.89, 2.30, "32", "80", 1.5), ("Limoges", 45.83, 1.26, "75", "87", 1.5),
    ("Perpignan", 42.70, 2.90, "76", "66", 2), ("Metz", 49.12, 6.18, "44", "57", 1.5),
    ("Besançon", 47.24, 6.02, "27", "25", 1.5), ("Orléans", 47.90, 1.91, "24", "45", 2),
    ("Rouen", 49.44, 1.10, "28", "76", 2), ("Caen", 49.18, -0.37, "28", "14", 2),
    ("Nancy", 48.69, 6.18, "44", "54", 1.5), ("Avignon", 43.95, 4.81, "93", "84", 2),
    ("Poitiers", 46.58, 0.34, "75", "86", 1.5), ("La Rochelle", 46.16, -1.15, "75", "17", 1.5),
    ("Pau", 43.30, -0.37, "75", "64", 1.5), ("Ajaccio", 41.92, 8.74, "94", "2A", 0.7),
    ("Bastia", 42.70, 9.45, "94", "2B", 0.5), ("Quimper", 47.99, -4.10, "53", "29", 1),
    ("Annecy", 45.90, 6.13, "84", "74", 1.5), ("Valence", 44.93, 4.89, "84", "26", 1),
    ("Troyes", 48.30, 4.08, "44", "10", 1), ("Vannes", 47.66, -2.76, "53", "56", 1),
]  # fmt: skip
CITY = {c[0]: c for c in CITIES}
# The three recorded leads sit where their recordings say.
HOME = {"g900000010": "Quimper", "g900000060": "Grenoble", "g900000110": "Avignon"}

FIRST = [
    "Val",
    "Ter",
    "Mor",
    "Sol",
    "Cal",
    "Bel",
    "Lor",
    "Ven",
    "Dur",
    "Aur",
    "Pel",
    "Mar",
    "Sa",
    "Ro",
    "Fel",
    "Nor",
    "Cor",
    "Lum",
    "Ar",
    "Tal",
    "Gri",
    "Vi",
    "Pa",
    "Ma",
    "Be",
    "Lo",
]
LAST = [
    "morin",
    "nelac",
    "vance",
    "dor",
    "ric",
    "lan",
    "vent",
    "teau",
    "gal",
    "mont",
    "ray",
    "bon",
    "line",
    "sier",
    "ford",
    "ac",
    "ier",
    "on",
    "et",
    "eur",
]
MIDDLE = ["ra", "le", "ni", "to", "ve", "mi", "do", "su", "ca", "fo", "ba", "re"]
TRADES = ["THERMIQUE", "SOLAIRE", "ÉNERGIES", "CLIMAT", "HABITAT"]

# INSEE band of one company: weights tuned so about one group in ten lands in 30-300.
BAND_WEIGHTS = {"01": 17, "02": 27, "03": 22, "11": 20, "12": 4.6, "21": 2.6, "22": 1.1,
                "31": 0.3, "32": 0.3, "41": 0.1, "NN": 2}  # fmt: skip
UNKNOWN_BAND = "NN"
LINK_KEYS = {"same manager": "manager", "same phone": "phone", "same website": "website",
             "same holding": "holding"}  # fmt: skip
LINES = {
    "heat_pump": ["Pompe à chaleur : chauffage"],
    "solar": ["Panneaux solaires photovoltaïques", "Chauffage et/ou eau chaude solaire"],
}
N_FORCED = 10  # leads with every signal at 1

# Templated evidence. Each French text has its English beside it.
SIZE_QUOTES = [
    ("Une équipe de {n} collaborateurs.", "A team of {n} staff."),
    ("{n} collaborateurs à votre service.", "{n} staff at your service."),
    ("Notre équipe compte {n} personnes à {city}.", "Our team has {n} people in {city}."),
    ("Entreprise de {n} salariés, installée à {city}.", "A company of {n} employees, based in {city}."),
]  # fmt: skip
MIX_BOTH = [
    ("Installation de pompes à chaleur et de panneaux photovoltaïques.",
     "Installation of heat pumps and solar PV panels."),
    ("Pompes à chaleur, photovoltaïque et solaire thermique : un seul installateur.",
     "Heat pumps, solar PV and solar thermal: one installer."),
    ("Nos métiers : chauffage thermodynamique et énergie solaire.",
     "Our trades: heat pump heating and solar energy."),
]  # fmt: skip
MIX_ONE = {
    "heat_pump": [("Pompes à chaleur et ballons thermodynamiques.",
                   "Heat pumps and heat pump water heaters."),
                  ("Pompes à chaleur air-eau et bornes de recharge.",
                   "Air-to-water heat pumps and EV chargers.")],
    "solar": [("Panneaux solaires et bornes de recharge.", "Solar panels and EV chargers."),
              ("Photovoltaïque et stockage par batterie.", "Solar PV and battery storage.")],
}  # fmt: skip
ROLES = [
    ("technicien installateur pompe à chaleur", "heat pump installation technician"),
    ("commercial terrain photovoltaïque", "field sales rep, solar PV"),
    ("chargé d'affaires", "account manager"),
    ("assistant administratif", "administrative assistant"),
    ("conducteur de travaux", "site supervisor"),
    ("technicien bureau d'études", "design office technician"),
]  # fmt: skip
GROWTH_QUOTES = [
    ("Nous recrutons : {role} (CDI, {city})",
     "We are hiring: {role_en} (permanent, {city})"),
    ("Offre d'emploi : {role}, {city}", "Job offer: {role_en}, {city}"),
]  # fmt: skip
BRANCH_QUOTE = ("Nouvelle agence ouverte à {city}.", "New branch opened in {city}.")
TECH_FULL = [
    ("Demandez votre devis gratuit en ligne : simulateur d'économies d'énergie.",
     "Ask for your free quote online: energy savings simulator."),
    ("Simulez votre installation solaire en 2 minutes.",
     "Simulate your solar installation in 2 minutes."),
    ("Formulaire de devis : type de logement, chauffage actuel, budget.",
     "Quote form: type of home, current heating, budget."),
]  # fmt: skip
TECH_PLAIN = ("Contactez-nous : formulaire de contact (nom, e-mail, message).",
              "Contact us: contact form (name, email, message).")  # fmt: skip


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "-".join(plain.lower().replace("'", "").split())


def wchoice(rng: random.Random, weighted: dict | list[tuple]):
    items = list(weighted.items()) if isinstance(weighted, dict) else weighted
    return rng.choices([i[0] for i in items], [i[-1] for i in items])[0]


def build(out_dir: Path, n_groups: int = 6000, seed: int = 7) -> None:
    out_dir = Path(out_dir)
    if (out_dir / MARKER).exists():
        shutil.rmtree(out_dir)
    elif (out_dir / "market.parquet").exists():
        raise FileExistsError(
            f"{out_dir} holds a market.parquet but no {MARKER} marker: not generated data, "
            "so it is left alone. Pick another directory."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / MARKER).write_text("Generated by fixtures/demo/make_demo.py; safe to delete.\n")
    rng = random.Random(seed)
    icp = config.load(ROOT / "config" / "icp.example.yaml")

    # 1. The fixture market, as templates. 2. The three recorded leads, replayed.
    make_fixtures.market(out_dir)
    real = pd.read_parquet(out_dir / "market.parquet")
    real_companies = pd.read_parquet(out_dir / "companies.parquet")
    real_funnel = json.loads((out_dir / "funnel.json").read_text(encoding="utf-8"))
    research.run(icp, out_dir, mode="replay", recordings_dir=ROOT / "fixtures" / "llm",
                 group_ids=make_fixtures.GROUPS, log=lambda _: None)  # fmt: skip
    recorded = read_ledger(out_dir / "ledger.jsonl")

    # 3. The market: the real rows moved onto real cities, then the synthetic ones.
    cities = [(c[0], c[-1]) for c in CITIES]
    real_rows, real_homes = [], {}
    for row in real.to_dict("records"):
        city = CITY[HOME.get(row["group_id"]) or wchoice(rng, cities)]
        real_homes[row["group_id"]] = city
        row.update(place(rng, city))
        row["shortlisted"] = row["group_id"] in make_fixtures.GROUPS
        row["exclusion_reason"] = None if row["shortlisted"] else row["exclusion_reason"]
        real_rows.append(row)
    real_companies = real_companies.copy()
    for i, gid in enumerate(real_companies["group_id"]):
        if gid not in real_homes:  # a company that never made it into a group
            continue
        c = real_homes[gid]
        at = real_companies.index[i]
        real_companies.loc[at, ["lat", "lon", "region", "department"]] = [c[1], c[2], c[3], c[4]]

    templates = real[real["source"] != "register"].to_dict("records")
    single = [t for t in templates if len(t["members"]) == 1]
    multi = [t for t in templates if len(t["members"]) > 1]
    names: set[str] = set()
    rows, companies, extra = [], [], {}
    for i in range(n_groups - len(real)):
        row, members, info = synthetic_group(
            rng, icp, i, names, single, multi, cities, real_companies.iloc[0].to_dict()
        )
        rows.append(row)
        companies += members
        extra[row["group_id"]] = info

    # 4. The shortlist: synthetic rows only; the real rows keep the three recorded leads.
    prefilter.shortlist(rows, max(icp.prefilter.shortlist_size - 3, 0), icp.segment.headcount_max)
    by_group = {r["group_id"]: r for r in rows}
    for m in companies:
        m["exclusion_reason"] = by_group[m["group_id"]]["exclusion_reason"]
    market = pd.concat([pd.DataFrame(real_rows), pd.DataFrame(rows)], ignore_index=True)
    market = market[list(real.columns)]
    market.to_parquet(out_dir / "market.parquet", index=False)

    # 5-6. Synthetic research and regrades.
    shortlisted = sorted((r for r in rows if r["shortlisted"]), key=lambda r: -r["pre_score"])
    forced = [
        r["group_id"]
        for r in shortlisted
        if extra[r["group_id"]]["website"]
        and extra[r["group_id"]]["in_segment"]
        and len(r["product_lines"]) == 2
    ][:N_FORCED]
    for row in shortlisted:
        info = extra[row["group_id"]]
        found = researched(rng, icp, row, info, row["group_id"] in forced)
        write_json(out_dir / "research" / f"{row['group_id']}.json", found["research"])
        write_json(out_dir / "regrade" / f"{row['group_id']}.json", found["regrade"])
    research.write_signals(icp, out_dir)

    # 7. The ledger: one synthetic line per researched group; every `at` on the fixed clock.
    write_ledger(out_dir, rng, icp, recorded, [r["group_id"] for r in shortlisted])

    # 8. Companies and the funnel.
    allc = pd.concat([real_companies, pd.DataFrame(companies)], ignore_index=True)
    allc = allc[list(real_companies.columns)]
    allc.to_parquet(out_dir / "companies.parquet", index=False)
    write_funnel(out_dir, real_funnel, market, allc, icp)

    # 9. The real scoring and insights.
    scored = score.run(icp, out_dir)
    insights.run(icp, out_dir)

    # 10. One line.
    queue = int(scored["queue_rank"].notna().sum())
    print(f"{len(market):,} groups, {int(market['in_segment'].sum()):,} in segment, "
          f"{len(scored)} researched, {queue} in the queue.\nRun the demo:\n  {COMMAND}")  # fmt: skip


def place(rng: random.Random, city: tuple) -> dict:
    """A point around a city centre, with its region and department."""
    _, lat, lon, region, dept, _ = city
    return {"lat": round(lat + rng.gauss(0, 0.25), 4), "lon": round(lon + rng.gauss(0, 0.25), 4),
            "region": region, "department": dept}  # fmt: skip


def pseudo_name(rng: random.Random, taken: set[str]) -> str:
    while True:
        word = rng.choice(FIRST) + rng.choice(MIDDLE) * (rng.random() < 0.6) + rng.choice(LAST)
        if word not in taken:
            taken.add(word)
            return word.upper()


def synthetic_group(rng, icp, i, taken, single, multi, cities, shared):
    """One synthetic market row, its companies, and the facts the research needs."""
    n_members = 2 if rng.random() < 0.1 else 1
    template = rng.choice(multi if n_members > 1 else single)
    gid = f"g0{i:08d}"
    word = pseudo_name(rng, taken)
    trades = rng.sample(TRADES, n_members)
    member_names = [f"{word} {t}" for t in trades]
    base = i * 2
    sirens = [f"000{base + k:06d}" for k in range(n_members)]
    city = CITY[wchoice(rng, cities)]
    bands = [wchoice(rng, BAND_WEIGHTS) for _ in range(n_members)]
    known = [b for b in bands if b != UNKNOWN_BAND]
    unknown = int(not known)
    low = sum(BANDS[b][0] for b in known)
    high = sum(BANDS[b][1] for b in known)
    mid = sum(band_mid(b) for b in known)
    flags = prefilter.size_flags(mid, unknown, icp.segment.headcount_min, icp.segment.headcount_max)

    lines = list(LINES) if rng.random() < 0.4 else [rng.choice(list(LINES))]
    lines = [k for k in LINES if k in lines]
    domains = sorted({d for k in lines for d in (LINES[k] if k == "heat_pump"
                      else rng.sample(LINES[k], rng.choice([1, 2])))})  # fmt: skip
    site_slug = slug(member_names[0])
    website = f"https://{site_slug}.example" if rng.random() < 0.7 else None
    growing = rng.random() < 0.3
    created = (f"{rng.choice([2025, 2026])}-{rng.randint(1, 8):02d}-{rng.randint(1, 28):02d}"
               if growing else f"{rng.randint(1998, 2022)}-{rng.randint(1, 12):02d}-"
               f"{rng.randint(1, 28):02d}")  # fmt: skip
    values = {
        "size_fit": 1.0 if flags["in_segment"] else 0.5 if flags["near_band"] else 0.0,
        "product_mix": len(lines) / len(icp.market.product_lines),
        "growth": 1.0 if growing else 0.0,
        "tech_maturity": 1.0 if website else 0.0,
    }
    where = place(rng, city)
    row = dict(template)
    row.update(
        group_id=gid, name=member_names[0], members=sirens, member_names=member_names,
        domains=domains, product_lines=lines, website=website,
        headcount_low=low, headcount_mid=float(mid), headcount_high=high,
        headcount_unknown=unknown,
        revenue=float(round(max(mid, 3) * rng.uniform(70_000, 130_000), -3)),
        created=created,
        pre_size_fit=values["size_fit"], pre_product_mix=values["product_mix"],
        pre_growth=values["growth"], pre_tech_maturity=values["tech_maturity"],
        pre_score=round(prefilter.pre_score(values, icp), 4),
        shortlisted=False, exclusion_reason=None, **flags, **where,
    )  # fmt: skip
    if n_members > 1:
        reason = rng.choice(list(LINK_KEYS))
        row.update(link_reason=reason, link_keys=[f"{LINK_KEYS[reason]}:{gid}"])
    else:
        row.update(link_reason="", link_keys=[])
    company_template = {
        k: shared[k] for k in ("naf", "band_year", "category", "revenue_year", "managers")
    }
    members = []
    for k, siren in enumerate(sirens):
        postcode = f"{'20' if city[4].startswith('2') and not city[4].isdigit() else city[4]}000"
        members.append({
            **company_template,
            "siren": siren, "name": member_names[k], "source": template["source"], "via": "rge",
            "active": True, "sirets": [f"{siren}00001"],
            "domains": domains if k == 0 else domains[:1],
            "phones": [f"02 00 00 {rng.randint(10, 99)} {rng.randint(10, 99)}"],
            "emails": [f"contact@{site_slug}.example"],
            "websites": [website] if website and k == 0 else [],
            "address": f"{rng.randint(1, 99)} RUE DU COMMERCE {postcode} {city[0].upper()}",
            "postcode": postcode, "department": where["department"], "region": where["region"],
            "lat": where["lat"], "lon": where["lon"],
            "band": bands[k], "created": created,
            "establishments_open": float(2 if growing and k == 0 else 1),
            "revenue": row["revenue"] / n_members, "group_id": gid, "exclusion_reason": None,
        })  # fmt: skip
    info = {"website": website, "city": city[0], "slug": site_slug, "lines": lines,
            "growing": growing, "in_segment": flags["in_segment"], "mid": mid}  # fmt: skip
    return row, members, info


def researched(rng, icp, row, info, forced: bool) -> dict:
    """The research JSON and the regrade JSON for one shortlisted synthetic group."""
    gid, city, site = row["group_id"], info["city"], info["website"]
    base = site or f"https://annuaire-fictif.example/{info['slug']}"
    seg = icp.segment
    n_lines = len(row["product_lines"])
    if forced:
        n = rng.randint(45, 260)
        value = {"size_fit": 1, "product_mix": 1, "growth": 1, "tech_maturity": 1}
    else:
        lo, hi = (seg.headcount_min, seg.headcount_max) if info["in_segment"] else (0, 999)
        n = int(min(max(round(row["headcount_mid"] * rng.uniform(0.85, 1.15)), lo), hi))
        u = rng.random()
        grow = (1 if u < 0.55 else 0.5 if u < 0.8 else 0) if info["growing"] else \
            (1 if u < 0.2 else 0.5 if u < 0.35 else 0)  # fmt: skip
        u = rng.random()
        tech = (1 if u < 0.5 else 0.5 if u < 0.9 else 0) if site else 0
        value = {
            "size_fit": 1 if info["in_segment"] else 0.5 if n >= 15 else 0,
            "product_mix": (1 if rng.random() < 0.9 else 0.5) if n_lines == 2
            else (0.5 if rng.random() < 0.35 else 0),
            "growth": grow, "tech_maturity": tech,
        }  # fmt: skip

    def quote(pair, url, **fill):
        return {"quote": pair[0].format(**fill), "quote_en": pair[1].format(**fill), "url": url}

    role, role_en = rng.choice(ROLES)
    roles = rng.sample(ROLES, 2)
    fill = {"n": n, "city": city, "role": role, "role_en": role_en}
    ev: dict[str, list[dict]] = {k: [] for k in value}
    if value["size_fit"]:
        for pair in rng.sample(SIZE_QUOTES, 1 + (rng.random() < 0.3)):
            ev["size_fit"].append(quote(pair, base, **fill))
    if value["product_mix"] == 1:
        ev["product_mix"].append(quote(rng.choice(MIX_BOTH), base))
    elif value["product_mix"]:
        ev["product_mix"].append(quote(rng.choice(MIX_ONE[row["product_lines"][0]]), base))
    if value["growth"]:
        pairs = [rng.choice(GROWTH_QUOTES)] if value["growth"] == 0.5 else \
            [GROWTH_QUOTES[0], rng.choice([GROWTH_QUOTES[1], BRANCH_QUOTE])]  # fmt: skip
        for pair, (r, r_en) in zip(pairs, roles, strict=False):
            ev["growth"].append(quote(pair, f"{base}/recrutement", city=city, role=r, role_en=r_en))
    if value["tech_maturity"] == 1:
        ev["tech_maturity"].append(quote(rng.choice(TECH_FULL), f"{base}/devis"))
    elif value["tech_maturity"]:
        ev["tech_maturity"].append(quote(TECH_PLAIN, base))

    why = {
        "size_fit": {1: f"The site states {n} staff, inside the {seg.headcount_min}-"
                        f"{seg.headcount_max} band.",
                     0.5: f"About {n} staff, near the band.", 0: "Far below the band."},
        "product_mix": {1: "Installs both heat pumps and solar PV.",
                        0.5: "One line plus an adjacent one.", 0: "A single line."},
        "growth": {1: "Open roles and a recent branch.", 0.5: "One weak sign of growth.",
                   0: "No job ads or new sites found."},
        "tech_maturity": {1: "An online quote form on its own site.",
                          0.5: "Own website with a plain contact form.", 0: "No own website found."},
    }  # fmt: skip
    signals = {
        k: {"value": v, "found": bool(ev[k]), "rationale_en": why[k][v], "evidence": ev[k]}
        for k, v in value.items()
    }
    result = {
        "website": site,
        "signals": signals,
        "facts": {
            "product_lines": row["product_lines"],
            "headcount_stated": n if site else None,
            "open_roles": [r_en for _, r_en in roles] if value["growth"] else [],
            "tools_seen": [],
        },
        "notes_en": f"Synthetic example in {city}.",
    }
    research_json = {"group_id": gid, "name": row["name"], "model": icp.research.model,
                     "calls": 1, "status": "ok", "reason": None, "flags": [],
                     "result": result}  # fmt: skip

    g = value["growth"]
    if g == 1:
        grade = rng.choice([1, 1, 0.75] if forced else [1, 0.75])
    else:
        grade = rng.choice([0.5, 0.25, 0.75]) if g == 0.5 else 0
    mix_words = {2: "heat pumps and solar PV", 1: "one line plus extras"}[min(n_lines, 2)]
    phrases = {
        "size_fit": f"{n} staff stated on the site",
        "product_mix": mix_words,
        "growth": rng.choice([f"hiring in {city}", "open installer roles", "a new branch"]),
        "tech_maturity": rng.choice(["online quote form", "quote simulator on the site"]),
    }
    regrade_json = {
        "group_id": gid, "status": "ok",
        "result": {
            "headcount": n,
            "headcount_basis_en": (f"The site states {n} staff." if site
                                   else f"Registry bands add up to about {n}."),
            "grades": {"growth": {"value": grade,
                                  "basis_en": f"Graded {grade} on the evidence found."}},
            "phrases": phrases,
        },
    }  # fmt: skip
    return {"research": research_json, "regrade": regrade_json}


def write_ledger(out_dir, rng, icp, recorded, group_ids) -> None:
    """Synthetic research lines beside the replayed ones, all on the fixed clock."""
    per_lead: dict[str, float] = {}
    for line in recorded:
        per_lead[line["lead"]] = per_lead.get(line["lead"], 0.0) + line["usd"]
    mean = sum(per_lead.values()) / len(per_lead)
    lines = list(recorded)
    for gid in group_ids:
        usd = round(max(mean * rng.gauss(1, 0.25), mean * 0.3), 4)
        lines.append({
            "at": "", "lead": gid, "purpose": "research",
            "key": hashlib.sha256(f"synthetic-{gid}".encode()).hexdigest(),
            "model": icp.research.model,
            "input_tokens": int(rng.gauss(3300, 600)), "cache_write_tokens": 2400,
            "cache_read_tokens": rng.choice([0, 2400]), "output_tokens": int(rng.gauss(1200, 250)),
            "web_searches": rng.randint(1, 3), "web_fetches": rng.randint(0, 3),
            "usd": usd, "replayed": False,
        })  # fmt: skip
    at = make_fixtures.CLOCK.isoformat(timespec="seconds")
    with (out_dir / "ledger.jsonl").open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps({**line, "at": at}, ensure_ascii=False) + "\n")


def write_funnel(out_dir, real_funnel, market, companies, icp) -> None:
    """The fixture run's stages and wording, with counts that fit the combined market."""
    active = int(companies["active"].sum())
    groups = len(market)
    multi = int((market["members"].map(len) > 1).sum())
    in_seg, near = int(market["in_segment"].sum()), int(market["near_band"].sum())
    seg = icp.segment
    sirens = round(active * 1.06)
    sirets = round(sirens * 1.12)
    active_rows = round(sirets * 1.08)
    target = round(active_rows * 1.03)
    added = {"register_source": round(active * 0.05), "manager_expansion": round(active * 0.025)}
    counts = {
        "rge_rows": round(target * 22.2), "target_rows": target, "active_rows": active_rows,
        "sirets": sirets, "sirens": sirens, "active_companies": active,
        "register_source": active + added["register_source"],
        "manager_expansion": active + sum(added.values()),
        "groups": groups, "segment": in_seg + near,
        "shortlist": int(market["shortlisted"].sum()),
    }  # fmt: skip
    reasons = {
        "active_rows": f"dropped {target - active_rows:,} expired",
        "active_companies": f"dropped {sirens - active:,} closed or not in the register",
        "register_source": f"+{added['register_source']:,} with NAF {', '.join(icp.market.second_source.naf_codes)}, "
                           "an energy word in the name, not in RGE",
        "manager_expansion": f"+{added['manager_expansion']:,} other companies of the same managers",
        "groups": f"{active + sum(added.values()):,} companies rolled up; {multi:,} groups have "
                  "several members",
        "segment": f"{in_seg:,} with {seg.headcount_min}-{seg.headcount_max} staff (sum of band "
                   f"midpoints), {near:,} near it",
        "shortlist": f"top {icp.prefilter.shortlist_size} by rule-based pre-score",
    }  # fmt: skip
    f = funnel.Funnel(meta=real_funnel["meta"])
    for s in real_funnel["stages"]:
        detail = dict(s["detail"])
        if s["id"] in added:
            detail["added"] = added[s["id"]]
        if s["id"] == "groups":
            detail["multi_member"] = multi
        if s["id"] == "segment":
            detail.update(in_segment=in_seg, near_band=near)
        f.add(s["id"], s["label"], counts[s["id"]], reasons.get(s["id"], s["reason"]),
              s["kind"], **detail)  # fmt: skip
    f.write(out_dir / "funnel.json")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("out_dir", nargs="?", default="data/example", type=Path)
    p.add_argument("--groups", type=int, default=6000)
    a = p.parse_args()
    try:
        build(a.out_dir, a.groups)
    except FileExistsError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
