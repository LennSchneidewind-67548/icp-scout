# ADR 0003: Case-company content is never committed

Status: accepted, 2026-09-29

## Decision

Everything specific to the case company (the brief, the real ICP config,
research notes, the scored list, the deck) lives in `private/`, which is
gitignored from the first commit. The repo ships a fictional example config.

## Why

The repo goes public after the presentation. If nothing specific was ever
committed, going public needs no history rewrite and cannot leak anything.

## Consequences

- `private/` is not backed up by git; the author backs it up.
- Code must never hard-code the company, the market or the references.
  Everything comes from the ICP config.
