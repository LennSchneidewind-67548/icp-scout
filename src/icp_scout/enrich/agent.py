"""WP2. Research one shortlisted company and extract the rubric signals.

Reads the company's website (and web search where the site is thin), then
returns each signal from the ICP config as a value in [0, 1] with evidence
(quote + URL). It never produces the score: that is the rubric's job (ADR 0002).
"""
