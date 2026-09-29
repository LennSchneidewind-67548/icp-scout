# ADR 0004: Reuse outreach-engine's patterns, not its code

Status: accepted, 2026-09-29

## Decision

outreach-engine (the author's TypeScript job-search pipeline) has the same
shape: source, pre-filter, score, agent research, hand-off. Its patterns are
reimplemented here in Python: one LLM door with schema validation, a cost
ledger, answers recorded for offline replay, and ADRs. No code is copied.

## Why

- Its ~9k lines are coupled to job postings, its SQLite schema and a
  subscription-based agent runtime. Untangling them costs more than writing
  the few hundred lines this project needs.
- The role asks for Python.
- Two repos with the same architecture in two languages are better portfolio
  evidence than one repo split across two.
