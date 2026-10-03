"""WP6. The SDR hand-off: a HubSpot-ready CSV (company + manager contact, with score,
tier, reason and evidence) and a 3-touch sequence per queued lead, drafted in the
outreach language with its translation next to it.

The model writes copy from what the research agent recorded: no web, no new facts.
It never sees the score or the tier (ADR 0002). Code checks flag what breaks a rule
(length, the formal address, a score in the copy); nothing is fixed. Nothing is sent:
people import the CSV and send.
"""

import csv
import json
import re
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError

from icp_scout.config import IcpConfig
from icp_scout.demo import display_name, why
from icp_scout.enrich.agent import _clean, _object
from icp_scout.group import directory_hosts, is_auditor, lead_key, website_host

PURPOSE = "sequence"
TOOL = "record_sequence"
EFFORT = "low"  # short copy from given facts
MAX_TOKENS = 8000
# Touch limits: words for the emails, characters for the LinkedIn note (its own cap).
EMAIL_1_WORDS, EMAIL_2_WORDS, LINKEDIN_CHARS = 90, 60, 300
DAYS = {"email_1": 0, "email_2": 3, "linkedin": 6}

LANGUAGES = {"fr": "French", "en": "English", "de": "German", "es": "Spanish",
             "it": "Italian", "nl": "Dutch"}  # fmt: skip
# Informal address words, by language: the copy must use the formal form.
INFORMAL = {"fr": {"tu", "ton", "ta", "tes", "toi"}, "de": {"du", "dich", "dir", "dein", "deine"}}
COUNTRIES = {"FR": "France", "DE": "Germany", "ES": "Spain", "IT": "Italy", "BE": "Belgium"}

# The register's manager roles, glossed for readers who don't read French.
ROLES_EN = {
    "gerant": "managing director",
    "president": "president",
    "president de sas": "president (of the SAS)",
    "directeur general": "CEO",
    "directeur general delegue": "deputy CEO",
    "administrateur": "board member",
    "president du conseil d administration": "chair of the board",
    "president du conseil d administration et directeur general": "chair and CEO",
    "president du conseil de surveillance": "chair of the supervisory board",
    "membre du conseil de surveillance": "supervisory board member",
    "president du directoire": "chair of the management board",
    "membre du directoire": "management board member",
    "gerant et associe indefiniment responsable": "managing director and general partner",
    "associe indefiniment responsable": "general partner",
    "liquidateur": "liquidator",
}


class Sequence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hook_evidence: int
    email_1_subject: str
    email_1_subject_en: str
    email_1_body: str
    email_1_body_en: str
    email_2_body: str
    email_2_body_en: str
    linkedin: str
    linkedin_en: str


# The queue and its contacts.


def queue(data_dir: str | Path) -> pd.DataFrame:
    """The queued leads of scored.parquet (config weights, as stored), best first, with
    their market row, the agent's website, and the group's head company."""
    data_dir = Path(data_dir)
    for name, command in [("scored.parquet", "score"), ("market.parquet", "source"),
                          ("companies.parquet", "source"), ("signals.parquet", "research")]:  # fmt: skip
        if not (data_dir / name).exists():
            raise FileNotFoundError(f"{data_dir / name} not found: run `icp-scout {command}` first")
    scored = pd.read_parquet(data_dir / "scored.parquet")
    q = scored[scored["queue_rank"].notna()].sort_values("queue_rank", kind="stable")
    market = pd.read_parquet(data_dir / "market.parquet").set_index("group_id")
    signals = pd.read_parquet(data_dir / "signals.parquet")
    agent_site = signals.drop_duplicates("group_id").set_index("group_id")["website"]
    companies = pd.read_parquet(data_dir / "companies.parquet")
    directories = directory_hosts(
        {c.siren: list(c.websites) for c in companies.itertuples() if c.websites is not None}
    )
    heads = {
        gid: max(g.itertuples(), key=lead_key)._asdict()
        for gid, g in companies[companies["group_id"].isin(q["group_id"])].groupby("group_id")
    }
    rows = []
    for r in q.to_dict("records"):
        gid = r["group_id"]
        m = market.loc[gid]
        rows.append({
            **r,
            "display_name": display_name(r["name"]),
            "members": list(m["members"]),
            "domain": own_domain([agent_site.get(gid), m.get("website")], directories) or "",
            "head": heads.get(gid),
        })  # fmt: skip
    return pd.DataFrame(rows)


def own_domain(websites: list, directories: set[str]) -> str | None:
    """The first website host that isn't a directory. The agent's site comes first: it
    checked the site belongs to the group, and the registry's often has typos."""
    for url in websites:
        host = website_host(url) if isinstance(url, str) else None
        if host and host not in directories:
            return host
    return None


def contact(company: dict | None) -> dict | None:
    """The head company's first physical-person manager (auditors skipped), or None."""
    managers = json.loads((company or {}).get("managers") or "[]")
    for o in managers:
        if o.get("type_dirigeant") != "personne physique" or is_auditor(o):
            continue
        first = re.split(r"[\s,]+", (o.get("prenoms") or "").strip())[0]
        last = (o.get("nom") or "").split("(")[0].strip()
        if not last:
            continue
        role = o.get("qualite") or ""
        return {"first_name": _name(first), "last_name": _name(last), "role": role,
                "role_en": role_en(role)}  # fmt: skip
    return None


def _name(text: str) -> str:
    """Registry capitals to a name: "LE GALL" -> "Le Gall", "D'ARC" -> "D'Arc"."""
    return text.title() if text == text.upper() else text


def role_en(role: str) -> str:
    from icp_scout.sources.sirene import normalize

    return ROLES_EN.get(normalize(role).lower(), "") if role else ""


def split_address(address: str | None, postcode: str | None) -> tuple[str, str]:
    """ "8 RUE X 21000 DIJON" -> ("8 RUE X", "DIJON"), split on the postcode."""
    address = (address or "").strip()
    if postcode and f" {postcode} " in f" {address} ":
        street, _, city = f" {address} ".partition(f" {postcode} ")
        return street.strip(), city.strip()
    return address, ""


# The sequence: one call per lead.


def evidence_items(signals: list[dict]) -> list[dict]:
    """Every recorded evidence item of the lead's found signals, numbered from 1."""
    items = []
    for s in signals:
        if not s.get("found"):
            continue
        for e in s["evidence"]:
            items.append({"n": len(items) + 1, "signal": s["signal"], "quote": e["quote"],
                          "quote_en": e["quote_en"], "url": e["url"]})  # fmt: skip
    return items


def schema(icp: IcpConfig) -> dict:
    lang = language(icp.outreach.language)
    tr = language(icp.outreach.translate_to or "en")

    def text(what: str) -> dict:
        return {"type": "string", "description": f"{what}, in {lang}."}

    def translation(what: str) -> dict:
        return {"type": "string", "description": f"The {what}, translated to {tr}."}

    return _object({
        "hook_evidence": {"type": "integer",
                          "description": "The n of the evidence item email 1 opens on."},
        "email_1_subject": text("Subject line, at most 8 words"),
        "email_1_subject_en": translation("subject"),
        "email_1_body": text(f"Email 1 (day 0), at most {EMAIL_1_WORDS} words"),
        "email_1_body_en": translation("email 1 body"),
        "email_2_body": text(f"Email 2 (day 3), a follow-up, at most {EMAIL_2_WORDS} words"),
        "email_2_body_en": translation("email 2 body"),
        "linkedin": text(f"LinkedIn connection note (day 6), at most {LINKEDIN_CHARS} characters"),
        "linkedin_en": translation("LinkedIn note"),
    })  # fmt: skip


def language(code: str) -> str:
    return LANGUAGES.get(code, code)


def system_prompt(icp: IcpConfig) -> str:
    lang = language(icp.outreach.language)
    tr = language(icp.outreach.translate_to or "en")
    formal = " Use the formal \"vous\", never \"tu\"." if icp.outreach.language == "fr" else (
        " Use the formal form of address." if icp.outreach.language in INFORMAL else "")  # fmt: skip
    return f"""\
You draft a 3-touch outreach sequence to one company for an SDR at \
{icp.vendor.name}, which sells: {" ".join(icp.vendor.pitch.split())}

You get what a research agent recorded about the company: a one-line reason it \
fits, its signals with verbatim evidence (quote, translation, URL), facts, and \
the role of the person you write to. You have no web access. Use only these \
facts; never invent a number, a name, a project or a claim about the company.

Write in {lang}.{formal} Plain, specific, peer to peer; no hype, no flattery.

- email_1 (day 0): a subject of at most 8 words, and a body of at most \
{EMAIL_1_WORDS} words. Open on one evidence item: use its quote's own words \
(it is in {lang} already), not a paraphrase of the English. Set hook_evidence \
to that item's n. Link it to one problem {icp.vendor.name} solves, then one \
low-commitment question.
- email_2 (day 3): a follow-up of at most {EMAIL_2_WORDS} words on a different \
signal's angle than email 1.
- linkedin (day 6): a connection note of at most {LINKEDIN_CHARS} characters, \
no link.

Each email starts with a plain greeting without a name and ends with one short \
opt-out line (the reader can say they don't want more emails); both count \
toward the limit. No signature: the sending tool adds it. Name \
{icp.vendor.name} at least once in the sequence.

Never mention a score, a tier, a ranking, a rubric or that the company was \
researched or selected.

Each *_en field is a faithful translation into {tr} of its {lang} field, as \
blunt as the original.

Answer with {TOOL} (or the structured output) only."""


def lead_message(lead: dict) -> str:
    body = {
        "company": lead["display_name"],
        "why_it_fits_en": why(lead["reason_en"]),
        "signals": [
            {"signal": s["signal"], "label": s.get("label"), "rationale_en": s["rationale_en"]}
            for s in lead["signals"] if s.get("found")
        ],
        "evidence": lead["evidence"],
        "facts": lead.get("facts"),
        "recipient_role": lead.get("role") or None,
    }  # fmt: skip
    return "Draft the sequence for this company. Recorded findings:\n\n" + json.dumps(
        _clean(body), ensure_ascii=False, indent=1
    )


def draft(icp: IcpConfig, llm, lead: dict) -> dict:
    """One call. `llm` is an llm.LLM or a claude_code.ClaudeCode. Returns status, result
    and flags."""
    from icp_scout.claude_code import ClaudeCode

    gid = lead["group_id"]
    out = {"group_id": gid, "name": lead["display_name"], "model": icp.research.model,
           "status": "failed", "reason": None, "result": None, "flags": []}  # fmt: skip
    prompt = lead_message(lead)
    if isinstance(llm, ClaudeCode):
        rec = llm.run(PURPOSE, gid, model=icp.research.model, effort=EFFORT,
                      system=system_prompt(icp), prompt=prompt, schema=schema(icp),
                      tools=[])  # fmt: skip
        answer = rec["result"].get("structured_output")
    else:
        tool = {"name": TOOL, "description": "Record the sequence. This is the answer.",
                "input_schema": schema(icp), "strict": True}  # fmt: skip
        response = llm.create(
            PURPOSE, gid, model=icp.research.model, max_tokens=MAX_TOKENS,
            system=system_prompt(icp), messages=[{"role": "user", "content": prompt}],
            tools=[tool], tool_choice={"type": "tool", "name": TOOL},
        )  # fmt: skip
        call = next((b for b in response["content"] if b.get("type") == "tool_use"), None)
        answer = call["input"] if call else None
    if answer is None:
        out["reason"] = "no answer"
        return out
    try:
        seq = Sequence.model_validate(answer).model_dump()
    except ValidationError as e:
        out["reason"] = f"invalid answer: {e.error_count()} errors"
        return out
    out.update(status="ok", result=seq, flags=checks(icp, seq, lead))
    return out


SCORE_WORDS = re.compile(
    r"\b(score|scoring|tier|rubri\w*)\b|\b\d+(?:[.,]\d+)?\s*/\s*10\b", re.IGNORECASE
)


def checks(icp: IcpConfig, seq: dict, lead: dict) -> list[str]:
    """Rule breaks in a valid sequence, as flags. Nothing is fixed."""
    flags = []
    for field, limit in [("email_1_body", EMAIL_1_WORDS), ("email_2_body", EMAIL_2_WORDS)]:
        if (n := len(seq[field].split())) > limit:
            flags.append(f"{field}: {n} words (limit {limit})")
    if (n := len(seq["linkedin"])) > LINKEDIN_CHARS:
        flags.append(f"linkedin: {n} characters (limit {LINKEDIN_CHARS})")
    if seq["hook_evidence"] not in {e["n"] for e in lead["evidence"]}:
        flags.append(f"hook_evidence {seq['hook_evidence']} is no evidence item")
    copy = [seq[f] for f in ("email_1_subject", "email_1_body", "email_2_body", "linkedin")]
    words = {w.lower() for text in copy for w in re.findall(r"\w+", text)}
    if informal := sorted(words & INFORMAL.get(icp.outreach.language, set())):
        flags.append(f"informal address: {', '.join(informal)}")
    score = lead.get("score")
    shown = {f"{score:.1f}", f"{score:.1f}".replace(".", ",")} if score is not None else set()
    if any(SCORE_WORDS.search(t) or any(s in t for s in shown) for t in copy):
        flags.append("a score or tier in the copy")
    if not any(icp.vendor.name.lower() in t.lower() for t in copy):
        flags.append(f"{icp.vendor.name} not named")
    return flags


# The files.


def hubspot_rows(icp: IcpConfig, leads: pd.DataFrame, drafts: dict[str, dict]) -> list[dict]:
    """One row per queued lead: the company, its manager as a contact, the sequence."""
    labels = {s.id: s.label for s in icp.signals}
    rows = []
    for lead in leads.to_dict("records"):
        head = lead["head"] or {}
        person = contact(head) or {}
        street, city = split_address(head.get("address"), head.get("postcode"))
        seq = (drafts.get(lead["group_id"]) or {}).get("result") or {}
        evidence = [
            f"{labels.get(s['signal'], s['signal'])}: «{s['evidence'][0]['quote']}» "
            f"({s['evidence'][0]['quote_en']}) {s['evidence'][0]['url']}"
            for s in lead["signals"] if s.get("found") and len(s["evidence"])
        ]  # fmt: skip
        headcount = lead.get("headcount")
        rows.append({
            "Company name": lead["display_name"],
            "Company Domain Name": lead["domain"],
            "Company phone": _first(head.get("phones")),
            "Street Address": street,
            "City": city.title() if city == city.upper() else city,
            "Postal Code": head.get("postcode") or "",
            "Country/Region": COUNTRIES.get(icp.market.country, icp.market.country),
            "Number of Employees": "" if pd.isna(headcount) else str(round(headcount)),
            "icp_score": f"{lead['score']:.2f}",
            "icp_tier": lead["tier"],
            "icp_queue_rank": str(int(lead["queue_rank"])),
            "icp_reason": lead["reason_en"],
            "icp_evidence": "\n".join(evidence),
            "icp_group_sirens": "; ".join(lead["members"]),
            "rge_email": _first(head.get("emails")),
            "icp_registry_name": lead["name"],
            "seq_1_subject": seq.get("email_1_subject", ""),
            "seq_1_body": seq.get("email_1_body", ""),
            "seq_2_body": seq.get("email_2_body", ""),
            "seq_3_linkedin": seq.get("linkedin", ""),
            "First Name": person.get("first_name", ""),
            "Last Name": person.get("last_name", ""),
            "Job Title": person.get("role", ""),
        })  # fmt: skip
    return rows


def _first(values) -> str:
    values = [] if values is None else list(values)
    return values[0] if values else ""


# Which object and property each column maps to on HubSpot's import screen.
COLUMN_MAP = {
    "Company name": ("Company", "Name"),
    "Company Domain Name": ("Company", "Company Domain Name (the dedupe key)"),
    "Company phone": ("Company", "Phone Number"),
    "Street Address": ("Company", "Street Address"),
    "City": ("Company", "City"),
    "Postal Code": ("Company", "Postal Code"),
    "Country/Region": ("Company", "Country/Region"),
    "Number of Employees": ("Company", "Number of Employees"),
    "icp_score": ("Company", "new property, number"),
    "icp_tier": ("Company", "new property, single-line text"),
    "icp_queue_rank": ("Company", "new property, number"),
    "icp_reason": ("Company", "new property, multi-line text"),
    "icp_evidence": ("Company", "new property, multi-line text"),
    "icp_group_sirens": ("Company", "new property, single-line text"),
    "rge_email": ("Company", "new property, single-line text"),
    "icp_registry_name": ("Company", "new property, single-line text"),
    "seq_1_subject": ("Company", "new property, single-line text"),
    "seq_1_body": ("Company", "new property, multi-line text"),
    "seq_2_body": ("Company", "new property, multi-line text"),
    "seq_3_linkedin": ("Company", "new property, multi-line text"),
    "First Name": ("Contact", "First Name"),
    "Last Name": ("Contact", "Last Name"),
    "Job Title": ("Contact", "Job Title"),
}


# HubSpot rejects a contact row with no name, so the contacts go in a second file:
# only the leads with a manager, each with its company's domain, which matches the
# company imported first and associates the two.
CONTACT_COLUMNS = ["First Name", "Last Name", "Job Title"]
COMPANY_COLUMNS = [c for c in COLUMN_MAP if c not in CONTACT_COLUMNS]


def contact_rows(rows: list[dict]) -> list[dict]:
    """The rows with a contact and a domain to associate it by."""
    return [r for r in rows if r["Company Domain Name"] and (r["First Name"] or r["Last Name"])]


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    """UTF-8 with a BOM so Excel shows the accents; every cell quoted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, quoting=csv.QUOTE_ALL,
                                extrasaction="ignore")  # fmt: skip
        writer.writeheader()
        writer.writerows(rows)


def write_sequences_md(icp: IcpConfig, path: Path, leads: pd.DataFrame,
                       drafts: dict[str, dict]) -> None:  # fmt: skip
    lang = language(icp.outreach.language)
    tr = language(icp.outreach.translate_to or "en")
    lines = [
        f"# Outreach sequences for {icp.vendor.name}",
        "",
        (
            f"Drafted by the model in {lang} from the recorded evidence, with a {tr} "
            "translation under each touch. Nothing has been sent. Touches: email 1 (day 0), "
            "email 2 (day 3), LinkedIn connection note (day 6)."
        ),
        "",
        "## HubSpot column map",
        "",
        (
            "Two imports. First `hubspot_companies.csv`, one object (Companies); create "
            "the new properties while mapping. Then `hubspot_contacts.csv`, one file with two "
            "objects (Contacts and Companies): map `Company Domain Name` to the Company, "
            "which matches the company imported first and associates the contact."
        ),
        "",
        "| Column | Object | Property |",
        "|---|---|---|",
        *(f"| `{c}` | {o} | {p} |" for c, (o, p) in COLUMN_MAP.items()),
        "",
    ]
    for lead in leads.to_dict("records"):
        out = drafts.get(lead["group_id"]) or {}
        person = contact(lead["head"])
        lines += [
            f"## {int(lead['queue_rank'])}. {lead['display_name']}",
            "",
            f"- Score {lead['score']:.1f}, tier {lead['tier']}: {why(lead['reason_en'])}",
            f"- Domain: {lead['domain'] or '(none: HubSpot cannot dedupe this row or associate its contact)'}",
        ]
        if person:
            gloss = f" ({person['role_en']})" if person["role_en"] else ""
            lines.append(f"- Contact: {person['first_name']} {person['last_name']}, "
                         f"{person['role'] or 'no role given'}{gloss}")  # fmt: skip
        else:
            lines.append("- Contact: no physical-person manager in the register")
        if out.get("flags"):
            lines.append(f"- **Flagged:** {'; '.join(out['flags'])}")
        lines.append("")
        seq = out.get("result")
        if not seq:
            lines += [f"*No sequence: {out.get('reason') or 'not drafted'}.*", ""]
            continue
        hook = next((e for e in lead["evidence"] if e["n"] == seq["hook_evidence"]), None)
        if hook:
            lines += [f"Hook: «{hook['quote']}» ({hook['quote_en']}) {hook['url']}", ""]
        for title, fr, en in [
            (f"Email 1, day 0: {seq['email_1_subject']}", "email_1_body", "email_1_body_en"),
            ("Email 2, day 3", "email_2_body", "email_2_body_en"),
            ("LinkedIn, day 6", "linkedin", "linkedin_en"),
        ]:
            lines += [f"### {title}", ""]
            if fr == "email_1_body":
                lines += [f"*Subject ({tr}): {seq['email_1_subject_en']}*", ""]
            lines += [_quote(seq[fr]), "", f"*{tr}:*", "", _quote(seq[en]), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _quote(text: str) -> str:
    return "\n".join(f"> {line}".rstrip() for line in text.splitlines())


# `icp-scout export`


def leads_for_drafting(icp: IcpConfig, data_dir: Path, q: pd.DataFrame) -> pd.DataFrame:
    """Add each lead's signals, numbered evidence, facts and contact role."""
    from icp_scout.research import _row

    labels = {s.id: s.label for s in icp.signals}
    signals = pd.read_parquet(data_dir / "signals.parquet")
    signals = signals[signals["status"] == "ok"]
    order = {s.id: i for i, s in enumerate(icp.signals)}
    q = q.copy()
    q["signals"] = [
        sorted(({**_row(r), "evidence": [_row(e) for e in r["evidence"]],
                 "label": labels.get(r["signal"])}
                for r in signals[signals["group_id"] == gid].to_dict("records")),
               key=lambda s: order.get(s["signal"], 99))
        for gid in q["group_id"]
    ]  # fmt: skip
    q["evidence"] = [evidence_items(s) for s in q["signals"]]
    q["facts"] = [_facts(data_dir, gid) for gid in q["group_id"]]
    q["role"] = [(contact(h) or {}).get("role") for h in q["head"]]
    return q


def _facts(data_dir: Path, gid: str) -> dict | None:
    path = data_dir / "research" / f"{gid}.json"
    if not path.exists():
        return None
    return (json.loads(path.read_text("utf-8")).get("result") or {}).get("facts")


def run(icp: IcpConfig, data_dir, *, mode: str = "record", recordings_dir="fixtures/llm",
        client=None, runner=None, log=print) -> dict[str, dict]:  # fmt: skip
    """Draft a sequence per queued lead; write data/export/hubspot_companies.csv,
    hubspot_contacts.csv and sequences.md."""
    from concurrent.futures import ThreadPoolExecutor

    from icp_scout.claude_code import ClaudeCode, UsageLimit
    from icp_scout.llm import LLM

    data_dir = Path(data_dir)
    leads = leads_for_drafting(icp, data_dir, queue(data_dir))
    r, ledger = icp.research, data_dir / "ledger.jsonl"
    if r.backend == "claude-code":
        extra = {"runner": runner} if runner else {}
        llm = ClaudeCode(recordings_dir, mode, ledger, max_utilization=r.max_utilization, **extra)
    else:
        llm = LLM(recordings_dir, mode, ledger, client=client)

    def one(lead: dict) -> dict | None:
        try:
            return draft(icp, llm, lead)
        except UsageLimit as e:
            log(f"  {lead['group_id']}: usage limit ({e}); re-run later to resume.")
            return None

    log(f"Drafting {len(leads)} sequences ({mode}, {r.model}, {r.backend}) ...")
    with ThreadPoolExecutor(r.concurrency) as pool:
        drafts = {o["group_id"]: o for o in pool.map(one, leads.to_dict("records")) if o}
    out_dir = data_dir / "export"
    rows = hubspot_rows(icp, leads, drafts)
    write_csv(out_dir / "hubspot_companies.csv", rows, COMPANY_COLUMNS)
    contacts = ["Company Domain Name", *CONTACT_COLUMNS]
    write_csv(out_dir / "hubspot_contacts.csv", contact_rows(rows), contacts)
    write_sequences_md(icp, out_dir / "sequences.md", leads, drafts)

    ok = [d for d in drafts.values() if d["status"] == "ok"]
    log(f"Done: {len(ok)} of {len(leads)} sequences drafted; written to {out_dir}/")
    for label, names in [
        ("Not drafted", [f"{x['display_name']} ({(drafts.get(x['group_id']) or {}).get('reason') or 'usage limit'})"
                         for x in leads.to_dict("records")
                         if (drafts.get(x["group_id"]) or {}).get("status") != "ok"]),
        ("Flagged", [f"{d['name']}: {'; '.join(d['flags'])}" for d in ok if d["flags"]]),
        ("No domain (HubSpot can't dedupe on a re-import; the contact is left out)",
         list(leads.loc[leads["domain"] == "", "display_name"])),
    ]:  # fmt: skip
        if names:
            log(f"{label} ({len(names)}):")
            log("\n".join(f"  {n}" for n in names))
    return drafts
