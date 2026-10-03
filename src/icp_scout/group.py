"""WP1. Roll sister companies up to group level, before the size filter.

A holding's installer subsidiaries can each sit below the segment's headcount
floor while the group sits inside it. Companies are linked (union-find over
SIRENs) when they share:

- a physical-person manager: surname + first given name + birth month;
- a legal-entity manager (the holding), or one is the other's manager;
- a phone number;
- a website domain, unless more than DIRECTORY_MIN_SIRENS - 1 companies list it
  (a certifier's profile page or a directory);
- an address, only when at most MAX_SHARED_ADDRESS companies share it (business centers).

Auditors ("commissaire aux comptes") are listed among officers but never link.
Every group keeps the keys that joined it, so each roll-up can be explained.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from icp_scout.http import CachedClient
from icp_scout.sources import sirene
from icp_scout.sources.sirene import Company, band_mid, band_range, normalize

DIRECTORY_MIN_SIRENS = 21
MAX_SHARED_ADDRESS = 3
# Manager lookups in the register, at most. Each is cached, so a re-run is free.
EXPANSION_MAX_CALLS = 2000
# Staff a company needs on its own to be worth a manager lookup.
EXPANSION_MIN_STAFF = 10
# NAF codes an expansion hit may have: construction trades (43.*) and holdings.
# A manager's restaurant or property company would inflate the group's headcount.
EXPANSION_NAF_PREFIXES = ("43.", "64.20", "70.10")
AUDITOR = "COMMISSAIRE AUX COMPTES"

KEY_LABELS = {
    "manager": "same manager",
    "holding": "same holding",
    "phone": "same phone",
    "website": "same website",
    "address": "same address",
}


def is_auditor(officer: dict) -> bool:
    return AUDITOR in normalize(officer.get("qualite") or "")


def person_key(officer: dict) -> str | None:
    """Surname + first given name + birth month, or None if any is missing."""
    if officer.get("type_dirigeant") != "personne physique" or is_auditor(officer):
        return None
    surname = normalize((officer.get("nom") or "").split("(")[0])
    first = normalize((officer.get("prenoms") or "").replace(",", " ")).split(" ")[0]
    birth = officer.get("date_de_naissance") or ""
    if not surname or not first or len(birth) != 7:
        return None
    return f"{surname}|{first}|{birth}"


def entity_key(officer: dict) -> str | None:
    if officer.get("type_dirigeant") != "personne morale" or is_auditor(officer):
        return None
    if officer.get("siren"):
        return officer["siren"]
    name = normalize(officer.get("denomination") or "")
    return f"name:{name}" if name else None


def phone_key(phone: str | None) -> str | None:
    digits = "".join(c for c in phone or "" if c.isdigit())
    if digits.startswith("0033"):
        digits = "0" + digits[4:]
    elif digits.startswith("33") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits if len(digits) == 10 and digits.startswith("0") else None


def website_host(url: str | None) -> str | None:
    url = (url or "").strip().lower()
    if not url:
        return None
    host = urlsplit(url if "://" in url else "http://" + url).hostname or ""
    host = host.removeprefix("www.")
    return host if "." in host else None


def link_keys(company: Company) -> set[str]:
    """Every key this company could be linked by, before the sharing limits."""
    keys = {f"holding:{company.siren}"}  # so a holding in the set joins its subsidiaries
    for officer in company.managers:
        if pk := person_key(officer):
            keys.add(f"manager:{pk}")
        if ek := entity_key(officer):
            keys.add(f"holding:{ek}")
    keys |= {f"phone:{p}" for p in map(phone_key, company.phones) if p}
    keys |= {f"website:{h}" for h in map(website_host, company.websites) if h}
    if company.address:
        keys.add(f"address:{normalize(company.address)}")
    return keys


def directory_hosts(websites_by_siren: dict[str, list[str]]) -> set[str]:
    """Hosts listed by at least DIRECTORY_MIN_SIRENS companies: directories, not websites."""
    counts: dict[str, int] = defaultdict(int)
    for urls in websites_by_siren.values():
        for host in {website_host(u) for u in urls} - {None}:
            counts[host] += 1
    return {h for h, n in counts.items() if n >= DIRECTORY_MIN_SIRENS}


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def assign_groups(companies: list[Company], directories: set[str]) -> dict[str, list[str]]:
    """Set `group_id` on every company; return the keys that joined each group."""
    members: dict[str, set[str]] = defaultdict(set)
    for c in companies:
        for key in link_keys(c):
            members[key].add(c.siren)
    uf = UnionFind(c.siren for c in companies)
    used: list[str] = []
    for key, sirens in members.items():
        kind, value = key.split(":", 1)
        if len(sirens) < 2:
            continue
        if kind == "website" and value in directories:
            continue
        if kind == "address" and len(sirens) > MAX_SHARED_ADDRESS:
            continue
        first, *rest = sorted(sirens)
        for other in rest:
            uf.union(first, other)
        used.append(key)
    for c in companies:
        c.group_id = "g" + uf.find(c.siren)
    keys: dict[str, list[str]] = defaultdict(list)
    for key in sorted(used):
        keys["g" + uf.find(next(iter(members[key])))].append(key)
    return keys


def expansion_candidates(companies: list[Company], headcount_min: int) -> list[dict]:
    """Physical-person managers of companies with some staff but below the floor alone,
    largest company first, each person once."""
    ranked = sorted(
        (
            c
            for c in companies
            if c.active
            and (band_range(c.band) or (0, 0))[0] >= EXPANSION_MIN_STAFF
            and band_mid(c.band) < headcount_min
        ),
        key=lambda c: (-band_mid(c.band), c.siren),
    )
    people, seen = [], set()
    for c in ranked:
        for officer in c.managers:
            pk = person_key(officer)
            if pk and pk not in seen:
                seen.add(pk)
                people.append(officer)
    return people


def expand_by_manager(
    client: CachedClient, companies: list[Company], headcount_min: int, max_calls: int
) -> tuple[list[Company], dict]:
    """Look up other companies of the same managers: holdings and non-RGE sisters."""
    known = {c.siren for c in companies}
    found: list[Company] = []
    stats = {"lookups": 0, "hits": 0, "skipped_naf": 0, "closed": 0}
    for officer in expansion_candidates(companies, headcount_min)[:max_calls]:
        stats["lookups"] += 1
        pk = person_key(officer)
        surname, first, birth = pk.split("|")
        for result in sirene.person_search(client, surname, first, birth):
            if result.get("siren") in known:
                continue
            # The API matches loosely: keep only exact person matches.
            if pk not in {person_key(o) for o in result.get("dirigeants") or []}:
                continue
            if not (result.get("activite_principale") or "").startswith(EXPANSION_NAF_PREFIXES):
                stats["skipped_naf"] += 1
                continue
            if result.get("etat_administratif") != "A":
                stats["closed"] += 1
                continue
            known.add(result["siren"])
            found.append(sirene.from_register(result, source="register", via="manager"))
    stats["hits"] = len(found)
    return found, stats


def lead_key(c) -> tuple:
    """Largest headcount band, then a certified domain, then the lowest SIREN. `c` is a
    Company or a row of companies.parquet."""
    return (band_mid(c.band) or -1, len(c.domains) > 0, -int(c.siren))


@dataclass
class Group:
    group_id: str
    members: list[Company]
    keys: list[str] = field(default_factory=list)

    @property
    def lead(self) -> Company:
        """The largest member names the group."""
        return max(self.members, key=lead_key)

    @property
    def headcount(self) -> dict:
        known = [band_range(c.band) for c in self.members if band_range(c.band)]
        return {
            "headcount_low": sum(lo for lo, _ in known),
            "headcount_mid": sum((lo + hi) / 2 for lo, hi in known),
            "headcount_high": sum(hi for _, hi in known),
            "headcount_unknown": len(self.members) - len(known),
        }

    @property
    def source(self) -> str:
        sources = {c.source for c in self.members}
        return "both" if len(sources) > 1 else sources.pop()

    @property
    def link_reason(self) -> str:
        kinds = dict.fromkeys(k.split(":", 1)[0] for k in self.keys)
        return " + ".join(KEY_LABELS[k] for k in kinds)


def build_groups(companies: list[Company], keys: dict[str, list[str]]) -> list[Group]:
    by_id: dict[str, list[Company]] = defaultdict(list)
    for c in companies:
        by_id[c.group_id].append(c)
    return [
        Group(gid, sorted(ms, key=lambda c: c.siren), keys.get(gid, []))
        for gid, ms in sorted(by_id.items())
    ]
