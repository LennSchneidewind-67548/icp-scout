# WP6: The SDR hand-off

Budget: 1.75h (the planned 1h, plus 45 min for a 3-touch sequence instead of a
single opener; author, 2026-10-02). Planned 2026-10-02, local session.

**Done when:** `icp-scout export` writes `data/export/hubspot.csv` (the 50
queued leads, one row each: the company, plus its manager as a contact) and
`data/export/sequences.md` (per lead, three touches in French, each with its
English translation next to it). It runs offline from recordings. The author has
imported the CSV into HubSpot once with no row errors and has read 10 sequences
in translation.

## Why this WP looks the way it does

- The case asks for a scalable outbound motion. The slides sketch the process
  (tiers, cadence, triggers). This WP is the working slice: the queue lands in
  a CRM with the reason and the evidence attached, ready for an SDR.
- Every touch opens on a fact the agent recorded with a quote and a URL. There
  is no new research and no web access. The model writes the copy. It never sees the score
  and never states one (ADR 0002).
- One model call per lead, as in the regrade pass (`enrich/regrade.py`), with the same
  two backends (`claude-code` on the subscription, $0 API; `api` through
  `llm.LLM`). Recordings go under `$ICP_SCOUT_RECORDINGS/sequence/`
  (`private/llm` for the case).
- People send; the pipeline drafts (`docs/requirements.md`, out of scope).
  Nothing is sent and nothing goes to the HubSpot API: the author
  imports the CSV by hand.

## 1. The HubSpot CSV (`data/export/hubspot.csv`)

One file, two objects (HubSpot's "one file, multiple objects" import). UTF-8
with a BOM so Excel shows the accents, comma-separated, quoted cells.

- **Company:** name, as the demo shows it (`demo.display_name`: title-cased, no
  repeated bracketed alias), because an SDR copies it into an email; Company Domain Name, the dedupe key, taken from the group's own `website` host only, never
  a directory; phone, street, city and postcode of the
  group's head company (largest headcount band, as in `group.py`);
  Country/Region; Number of Employees (`headcount`). The author creates these custom properties
  while mapping the columns: `icp_score`, `icp_tier`, `icp_queue_rank`,
  `icp_reason` (`reason_en`), `icp_evidence` (the top quote per signal, French
  and English and the URL), `icp_group_sirens`, `rge_email` (the public contact
  email from the RGE registry), `icp_registry_name` (the raw registry name).
  `icp_queue_rank` is `queue_rank` from `scored.parquet` as stored, never
  re-ranked, so it carries the WP3 tie-break (signals with evidence, then the
  raw name) and matches the demo's queue place; the top leads tie at 10.0.
- **Config weights only:** the export reads the queue as scored with the
  config weights. The demo's weight sliders are for the talk and do not reach
  the CSV.
- **Contact:** the head company's first physical-person manager, from
  `companies.parquet` `managers` (`type_dirigeant == "personne physique"`,
  auditors skipped with `group.is_auditor`): first name, last name, job title
  (`qualite`, with an English gloss in `sequences.md`). No email is invented.
  With no such manager, the contact columns stay empty and the company still
  imports.
- **Sequence:** company properties `seq_1_subject`, `seq_1_body`, `seq_2_body`,
  `seq_3_linkedin`, in French only, for sending. The English is in
  `sequences.md`.
- A column map at the top of `sequences.md` says which HubSpot property each
  column maps to, for the import screen.

## 2. The sequence: one call per lead

Input: the company's `display_name`, `reason_en`, the signals with `rationale_en` and their evidence
(`quote`, `quote_en`, `url`), the agent's `facts`, the vendor `pitch`, the
manager's role. Output against a strict schema, validated with pydantic as in the regrade pass:

| Touch | Day | Limit | Content |
|---|---|---|---|
| `email_1` | 0 | subject + 90 words | Opens on one evidence item, named by its index (`hook_evidence`) |
| `email_2` | 3 | 60 words | A follow-up on a second signal's angle |
| `linkedin` | 6 | 300 characters (LinkedIn's limit) | Connection note |

Each touch has an `*_en` field with its English translation, written in the same call. The copy is in
`outreach.language` with the formal *vous*, has an opt-out line in each email, and states no score, tier,
ranking or fact outside the input.

**Code checks** produce flags, not failures, as in research: word and character limits;
`hook_evidence` points at an existing evidence item; no "tu", "ton" or "ta"; no
score or tier in the copy; the vendor name appears at least once. The run
output lists flagged leads, and `sequences.md` marks them.

## 3. Code

- `src/icp_scout/export.py` (pure where it can be, tested):
  - `queue(data_dir) -> DataFrame`: the queued rows of `scored.parquet`, joined
    to `market.parquet` and the head company in `companies.parquet`.
  - `contact(company) -> dict | None`: manager to first name, last name, role.
  - `schema(icp)`, `system_prompt(icp)`, `lead_message(...)`,
    `draft(icp, llm, lead) -> dict`, written like `enrich/regrade.py` (reusing `_object` and
    `_clean` from `enrich/agent.py`).
  - `checks(seq, lead) -> list[str]`: the flags above.
  - `hubspot_rows(...)`, `write_csv(...)`, `write_sequences_md(...)`.
  - `run(icp, data_dir, mode, recordings_dir)`: drafts the 50 in a thread pool
    and writes `data/export/`.
- `cli.py`: `icp-scout export [--offline] [--recordings]`, through
  `recordings_dir()`, which already refuses to record case data under
  `fixtures/`.
- Config: nothing new. It uses `outreach.language` and `translate_to`, `research.model`
  and `backend`, with low effort (short copy).
- Stretch, cut first: the demo's lead pane gets a third view, Signals |
  Research replay | Sequence, showing the three touches with their translation.

## 4. Tests (synthetic, `config/icp.example.yaml`)

On the WP5 `demo_dir` plus a synthetic `companies.parquet`, with a fake client
as in `tests/test_research.py`:

- The CSV has its header row, one row per queued lead and no references, and a UTF-8 BOM.
  It round-trips through `csv.DictReader` with the accents intact, and the domain is
  empty for a directory site. The name column is `display_name`, the raw name is in
  `icp_registry_name`, and `icp_queue_rank` equals `queue_rank` for two leads tied on score.
- A lead with no physical-person manager still gets a company row.
- `draft` validates a canned answer. `checks` flags an over-long LinkedIn
  note, a "tu" and a `hook_evidence` that points at no evidence item.
- `--offline` with no recording fails with the `RecordingMiss` message.
- The synthetic recordings live under `fixtures/llm/` (fictional companies), so
  the public repo can show a sample export.

## 5. The run on the case

`ICP_SCOUT_CONFIG=private/icp.yaml icp-scout export --recordings private/llm`
on the subscription backend: 50 calls and no API money. The author reads 10 sequences in
English and pastes 3 French ones into a translator, to check the agent's own
translation against an independent one.

## 6. The author's import

A free HubSpot account: Import, one file with two objects (Companies and Contacts). The
`icp_*` and `seq_*` properties are created while mapping the columns. Done when the import shows 0 errors and 50
companies, the contacts are associated and the accents are intact. A screenshot goes in the
deck. The case data then sits in the author's HubSpot account. Delete the import after the talk.

## Steps and time

1. `queue`, `contact`, the CSV writer + tests (25 min)
2. Sequence schema, prompt, `draft`, `checks` + tests (30 min)
3. CLI, `sequences.md`, the run on the case (20 min)
4. Author: read 10, translator check, HubSpot import (20 min)
5. Build log, "Built" section (10 min)

## Risks

- The touches restate the agent's English rationale in French and lose the
  hook. Against this, the prompt gives the French evidence verbatim, and the translator check
  catches drift.
- The agent's own translation is kinder than its French. The independent
  translator check on 3 sequences catches that.
- HubSpot rejects the two-object file. The fallback is two files (companies by domain, then
  contacts with the company domain), about 10 min.
- A lead with no own website has no domain, so HubSpot can't dedupe it on a
  second import. The run output lists those rows. A first import is unaffected.
- Personal data: the manager names come from the public company register and stay in
  `data/` and the author's CRM. B2B prospecting relies on legitimate interest, with an
  opt-out line in every email.
- Time: if late, cut the demo's Sequence view, then `email_2` and the LinkedIn note (keep
  email 1). Never cut the CSV.

## Decided (author, 2026-10-02)

- Company and manager contact in one import.
- A 3-touch sequence (email, follow-up, LinkedIn note) instead of a single
  opener; budget +45 min.
- The author imports the case CSV into their own HubSpot account to check it.
- After the WP5 redesign: the CSV and the copy use `display_name`, and the raw
  name goes in `icp_registry_name`. The stretch goal is a Sequence view in the
  lead pane, since the Lead tab is gone.

## Built (2026-10-02, local session)

Steps 1-4 done; the stretch (a Sequence view in the demo) is cut.

- `src/icp_scout/export.py` as planned, `icp-scout export [--offline] [--recordings]`,
  8 tests in `tests/test_export.py` on a copy of the WP5 `demo_dir` plus a synthetic
  `companies.parquet`.
- **Sample export committed:** `fixtures/llm/make_fixtures.py` now also replays the
  three fictional groups' research, scores them and drafts their sequences from a
  scripted client. The recordings are in `fixtures/llm/sequence/`, the output in
  `fixtures/export/`. A test replays the whole chain offline and compares the files
  byte for byte, so a prompt change fails CI until the fixtures are re-made.
- **Changed from the plan:**
  - The domain is the agent's `website` host first, the registry's second. In the
    case queue the two disagreed for 13 of 50 leads, and the registry's were often
    typos or an older site; the agent had checked the site belongs to the group.
    Either is dropped when it is a directory (listed by 21+ companies, as in
    `group.py`). 4 leads have no registry website at all.
  - The head company uses `group.lead_key`, factored out of `Group.lead`, so the
    export and the roll-up pick the same company.
  - The evidence is numbered across signals (`n` from 1) and only found signals
    are sent; `hook_evidence` points at that `n`. The `reason_en` sent to the
    model has its leading "score tier |" stripped (`demo.why`).
  - Each email starts with a plain greeting and has no signature: HubSpot adds
    the sender's. The opt-out line counts toward the word limit.
  - The column headers name their object ("Company phone") because one file holds
    two objects; `sequences.md` maps each column to its HubSpot property.
  - Registry roles get an English gloss from a small table (`ROLES_EN`, the 15
    commonest); an unknown role shows without one.
- **Case run:** 50 of 50 drafted on the subscription backend in about 45 min, $0 API
  ($2.08 notional). 5 leads are flagged, all for going 1 to 4 words over a limit;
  no informal address, no score in the copy, every hook points at real evidence.
  All 50 have a domain.
- **Open: 23 of 50 leads have no contact.** The head company of 18 is managed only
  by a legal entity (a holding), whose own managers aren't in `companies.parquet`;
  for 5, the only physical persons are auditors. Taking the first physical-person
  manager of any group member would fill 6 of the 23. The other 17 would need a
  register lookup of the holding.
- **To watch when reading:** a draft can state a general pain point as if it were
  a fact about the company (one said quotes "are often redone by hand"). The prompt
  forbids invented facts, not such claims.
- **The import (author, 2026-10-03): 50 companies, 27 contacts associated, 0 errors**,
  but only in two files. The one-file import failed on the 23 rows with no contact,
  because HubSpot rejects a contact with no name. `icp-scout export` now writes
  `hubspot_companies.csv` (imported first, one object) and `hubspot_contacts.csv`
  (the leads with a contact: Company Domain Name, mapped to the Company, plus
  the contact's columns; imported second, as two objects). The domain matches
  the existing company and associates the contact. A contact whose company has
  no domain is left out.
- **The 23 without a contact stay without one** (author): no fallback.
- **Author's read:** 10 sequences in English and 3 through an independent translator;
  both pass. The copy is repetitive across leads: most sequences lean on the same
  "combined quote (*devis*) with subsidies" angle.
