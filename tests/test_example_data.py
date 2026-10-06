"""The example dataset generator (fixtures/demo/make_demo.py): fictional, seeded, safe."""

import sys
from urllib.parse import urlparse

import pandas as pd
import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT / "fixtures" / "demo"))

import make_demo
import make_fixtures

from icp_scout import demo, insights

GOLDEN = ROOT / "fixtures" / "llm"
# The recorded Vallon lead cites the real public registry page; everything synthetic is .example.
REGISTRY_HOST = "annuaire-entreprises.data.gouv.fr"


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    out = tmp_path_factory.mktemp("example") / "data"
    make_demo.build(out, n_groups=600)
    return out


def hosts_ok(url) -> bool:
    return pd.isna(url) or urlparse(url).hostname.endswith((".example", REGISTRY_HOST))


def test_the_demo_loads_the_market(example):
    data = demo.load(example)
    assert len(data.market) == 600
    assert not data.scored.empty


def test_market_has_the_columns_of_the_real_file(example, tmp_path):
    make_fixtures.market(tmp_path)
    real = pd.read_parquet(tmp_path / "market.parquet")
    assert list(pd.read_parquet(example / "market.parquet").columns) == list(real.columns)


def test_every_finding_has_a_chart_spec(example):
    for f in insights.FINDINGS:
        assert (example / "insights" / f"{f.__name__}.vl.json").exists(), f.__name__


def test_recorded_leads_replay_and_synthetic_ones_do_not(example):
    data = demo.load(example)
    for gid in make_fixtures.GROUPS:
        assert demo.replay_steps(GOLDEN, data.ledger, gid) is not None, gid
    synthetic = next(g for g in data.scored["group_id"] if g.startswith("g0"))
    assert demo.replay_steps(GOLDEN, data.ledger, synthetic) is None


def test_everything_points_at_example_domains(example):
    signals = pd.read_parquet(example / "signals.parquet")
    urls = [e["url"] for ev in signals["evidence"] for e in ev]
    assert urls
    assert all(hosts_ok(u) for u in urls)
    assert all(hosts_ok(w) for w in pd.read_parquet(example / "market.parquet")["website"])


def test_every_quote_has_its_translation(example):
    signals = pd.read_parquet(example / "signals.parquet")
    items = [e for ev in signals["evidence"] for e in ev]
    assert items
    assert all(e["quote_en"].strip() for e in items)


def test_synthetic_sirens_cannot_be_real(example):
    market = pd.read_parquet(example / "market.parquet")
    synthetic = market[market["group_id"].str.startswith("g0")]
    assert not synthetic.empty
    assert all(s.startswith("000") for ms in synthetic["members"] for s in ms)


def test_the_same_seed_gives_the_same_scores(example, tmp_path):
    make_demo.build(tmp_path / "again", n_groups=600)
    pd.testing.assert_frame_equal(
        pd.read_parquet(example / "scored.parquet"),
        pd.read_parquet(tmp_path / "again" / "scored.parquet"),
    )


def test_a_second_run_replaces_the_first(tmp_path):
    out = tmp_path / "data"
    make_demo.build(out, n_groups=300)
    (out / "stale.txt").write_text("x")
    make_demo.build(out, n_groups=300)
    assert not (out / "stale.txt").exists()


def test_a_directory_without_the_marker_is_left_alone(tmp_path):
    (tmp_path / "market.parquet").write_bytes(b"real")
    with pytest.raises(FileExistsError, match="marker"):
        make_demo.build(tmp_path, n_groups=300)
    assert (tmp_path / "market.parquet").read_bytes() == b"real"


def test_the_app_opens_a_recorded_lead_from_its_link(example, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash

    monkeypatch.setenv("ICP_SCOUT_DATA", str(example))
    monkeypatch.setenv("ICP_SCOUT_RECORDINGS", str(GOLDEN))
    monkeypatch.setenv("ICP_SCOUT_CONFIG", str(ROOT / "config" / "icp.example.yaml"))
    app = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60)
    app.query_params["lead"] = "g900000010"
    app._page_hash = calc_hash("queue")
    app.run()
    assert not app.exception
    assert any("Brise Marine Energies" in m.value for m in app.markdown)


def test_full_size(tmp_path):
    out = tmp_path / "data"
    make_demo.build(out)
    market = pd.read_parquet(out / "market.parquet")
    scored = pd.read_parquet(out / "scored.parquet")
    assert len(market) == 6000
    assert len(scored) == 175
    queue = scored[scored["queue_rank"].notna()]
    assert len(queue) == 50
    assert "g900000010" in set(queue["group_id"])
