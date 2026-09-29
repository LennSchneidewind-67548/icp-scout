"""WP3. The rubric: signals -> 1-10 score -> tier. Pure, deterministic, no LLM.

score = 1 + 9 x weighted mean of signal values, weights from the ICP config.
Re-scoring after a weight change needs no model call, which is what makes the
live weight sliders in the app possible.
"""
