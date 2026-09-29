from pathlib import Path

import pytest

from icp_scout import config

EXAMPLE = Path(__file__).parent.parent / "config" / "icp.example.yaml"


def test_example_config_loads():
    icp = config.load(EXAMPLE)
    assert icp.segment.headcount_min < icp.segment.headcount_max
    assert {s.id for s in icp.signals} == {"size_fit", "product_mix", "growth", "tech_maturity"}
    assert all(s.definition for s in icp.signals)


def test_signal_definition_is_optional():
    signal = config.Signal(id="x", label="X", weight=1)
    assert signal.definition is None


def test_rejects_inverted_segment(tmp_path):
    raw = EXAMPLE.read_text(encoding="utf-8").replace("headcount_min: 30", "headcount_min: 500")
    bad = tmp_path / "icp.yaml"
    bad.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="headcount_min"):
        config.load(bad)
