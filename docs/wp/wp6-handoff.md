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

- **Company:** name; Company Domain Name, the dedupe key, taken from the group's own `website` host only, never
  a directory; phone, street, city and postcode of the
  group's head company (largest headcount band, as in `group.py`);
  Country/Region; Number of Employees (`headcount`). The author creates these custom properties
  while mapping the columns: `icp_score`, `icp_tier`, `icp_queue_rank`,
  `icp_reason` (`reason_en`), `icp_evidence` (the top quote per signal, French
  and English and the URL), `icp_group_sirens`, `rge_email` (the public contact
  email from the RGE registry).
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

Input: `reason_en`, the signals with `rationale_en` and their evidence
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
- Stretch, cut first: the demo's Lead tab shows the sequence with its
  translation.

## 4. Tests (synthetic, `config/icp.example.yaml`)

On the WP5 `demo_dir` plus a synthetic `companies.parquet`, with a fake client
as in `tests/test_research.py`:

- The CSV has its header row, one row per queued lead and no references, and a UTF-8 BOM.
  It round-trips through `csv.DictReader` with the accents intact, and the domain is
  empty for a directory site.
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
- Time: if late, cut the demo tab, then `email_2` and the LinkedIn note (keep
  email 1). Never cut the CSV.

## Decided (author, 2026-10-02)

- Company and manager contact in one import.
- A 3-touch sequence (email, follow-up, LinkedIn note) instead of a single
  opener; budget +45 min.
- The author imports the case CSV into their own HubSpot account to check it.
