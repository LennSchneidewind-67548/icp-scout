from pathlib import Path

import pytest
import yaml

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


def test_example_config_has_the_sourcing_keys():
    icp = config.load(EXAMPLE)
    assert set(icp.market.product_lines) == {"heat_pump", "solar"}
    for domains in icp.market.product_lines.values():
        assert set(domains) <= set(icp.market.rge_domains)
    assert icp.market.second_source.naf_codes == ["43.21A", "43.22B"]
    assert icp.market.second_source.min_headcount_band == "11"
    assert icp.prefilter.shortlist_size == 175
    assert icp.research == config.Research()


def test_example_config_has_the_research_keys():
    r = config.load(EXAMPLE).research
    assert (r.model, r.effort, r.max_searches, r.max_fetches) == ("claude-opus-5-5", "medium", 5, 6)
    assert (r.budget_usd, r.concurrency) == (60, 4)


def test_sourcing_keys_are_optional(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for key in ["product_lines", "second_source"]:
        del raw["market"][key]
    del raw["prefilter"]
    del raw["research"]
    old = tmp_path / "icp.yaml"
    old.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    icp = config.load(old)
    assert icp.market.product_lines == {} and icp.market.second_source is None
    assert icp.prefilter.shortlist_size == 175
    assert icp.research == config.Research()


def test_rejects_a_product_line_domain_outside_rge_domains(tmp_path):
    raw = EXAMPLE.read_text(encoding="utf-8").replace(
        'heat_pump: ["Pompe à chaleur : chauffage"]', 'heat_pump: ["Pompe a chaleur"]'
    )
    bad = tmp_path / "icp.yaml"
    bad.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="product_lines"):
        config.load(bad)
