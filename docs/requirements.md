# Requirements

*Written for the case, before the presentation; `private/` is not in the public repo.*

Fixed in the kickoff interview, 2026-09-29. The case brief itself is in
`private/Case.md` (not committed).

## The task, in general terms

Source 50 target companies for a B2B software vendor in one country and
segment, score each 1-10 with explained logic, present the patterns to
leadership, and sketch a scalable outbound process for an SDR team.

## Two goals, in order

1. **Win the case.** A ~20-minute presentation to two founders, on a deck with
   a 2-3 minute live demo. They grade the approach, the assumptions and how
   prioritization and a scalable outbound motion are thought through, not
   only the list.
2. **A public portfolio repo.** Made public after the presentation, with the
   case company swapped for a fictional example config and synthetic data.

## Decisions

| Topic | Decision |
|---|---|
| Time budget | ~20 hours before the presentation (about a week from 2026-09-29) |
| Stack | Python 3.12 (the role asks for Python first) |
| Sourcing | The whole market from open data (ADEME RGE registry + recherche-entreprises), rule-based pre-score for all, agent research on a shortlist, 50 delivered (ADR 0001) |
| Scoring | Hybrid: the agent extracts signals with evidence, a weighted rubric in code computes 1-10 (ADR 0002) |
| Signals | Size fit, product mix (heat pumps and solar), growth/hiring, tech maturity/stack. Residential focus was considered and left out. |
| LLM runtime | Anthropic API, every answer recorded so the demo and CI replay offline; cost ledger |
| Evaluation | Cost per researched lead is reported. No hand-labelled accuracy set. |
| Demo | Streamlit: market map, ranked table, per-lead evidence, weight sliders that re-rank live |
| Deck | HTML slides artifact, charts from the pipeline's data |
| Outbound | Process sketched on slides (tiers, cadences, triggers, hand-offs), plus a working slice: HubSpot-ready CSV and an AI-drafted French opener per lead with an English translation (the author does not read French) |
| Public/private | Private repo now, public after the presentation; case-company content never committed (ADR 0003) |
| outreach-engine | Its patterns are reused, not its code (ADR 0004) |

## Out of scope

- An n8n workflow (strong match for the role, but over budget; mention it as the next step)
- Sending anything to anyone. The pipeline drafts; people send.
- Scraping LinkedIn.
