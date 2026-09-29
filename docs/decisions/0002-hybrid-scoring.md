# ADR 0002: The agent extracts signals; a rubric in code computes the score

Status: accepted, 2026-09-29

## Decision

The agent returns each rubric signal as a value in [0, 1] with evidence (a
quote and a URL). The score is `1 + 9 x weighted mean`, with weights from the
ICP config. The model never outputs the score.

## Why

- **The brief asks for the logic behind the score.** A rubric can be read off
  a slide; a model's number cannot.
- **Weights are business assumptions** that the audience may disagree with.
  Changing them re-ranks instantly, with no model call, live in the demo.
- **Evidence makes each score checkable** by an SDR in seconds.

## Consequences

- Signal definitions must be precise enough for consistent extraction.
- An extraction error moves one signal, not the whole score.
