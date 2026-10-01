"""WP4: the findings in insights.py, on a small synthetic market and scored set."""

import json

import pandas as pd
import pytest

from icp_scout import cli, insights

# Example config: band 30-300, sweet spot 60-200, lines heat_pump and solar.
HP, PV = "heat_pump", "solar"

# group_id: (members, region, lines, registry website, headcount_mid, in segment, pre_score)
MARKET = {
    "g1": (["1", "2"], "75", [HP, PV], "https://a.example", 40.0, True, 1.0),
    "g2": (["3"], "75", [HP, PV], "https://b.example", 120.0, True, 0.9),
    "g3": (["4"], "84", [HP], None, 35.0, True, 0.9),
    "g4": (["5"], "84", [PV], "https://d.example", 70.0, True, 0.8),
    "g5": (["6"], "11", [HP], None, 10.0, False, 0.5),  # not researched
    "g6": (["7"], "84", [HP, PV], "https://f.example", 90.0, True, 0.7),  # the reference
}
# group_id: (size_fit, product_mix, growth, tech_maturity, headcount, score, tier, queue, ref)
SCORED = {
    "g2": (1.0, 1.0, 1.0, 1.0, 120, 10.0, "A", 1, False),
    "g4": (1.0, 0.5, 0.75, 0.5, 70, 8.2, "A", 2, False),
    "g1": (0.8, 1.0, 0.25, 1.0, 45, 7.5, "B", 3, False),
    "g3": (0.7, 0.5, 0.0, 0.0, 35, 5.0, "C", None, False),
    "g6": (1.0, 1.0, 1.0, 0.5, 90, 9.5, "A", None, True),
}
AGENT_SITES = {
    "g1": "https://www.a.example/",  # same host as the registry
    "g2": "https://other.example",  # different
    "g3": "https://c.example",  # found, registry had none
    "g4": None,  # none found
    "g6": "https://f.example",
}


def inputs() -> insights.Inputs:
    market = pd.DataFrame([
        {"group_id": g, "name": f"Group {g}", "members": m, "region": r, "product_lines": lines,
         "website": w, "headcount_mid": h, "in_segment": seg, "pre_score": pre,
         "pre_tech_maturity": 1.0 if w else 0.0, "link_reason": "same manager" if len(m) > 1
         else "", "shortlisted": g != "g5"}
        for g, (m, r, lines, w, h, seg, pre) in MARKET.items()
    ])  # fmt: skip
    scored = pd.DataFrame([
        {"group_id": g, "name": f"Group {g}", "size_fit": s, "product_mix": p, "growth": gr,
         "tech_maturity": t, "headcount": h, "headcount_source": "regrade", "score": sc,
         "tier": tier, "queue_rank": q, "is_reference": ref, "pre_score": MARKET[g][6]}
        for g, (s, p, gr, t, h, sc, tier, q, ref) in SCORED.items()
    ])  # fmt: skip
    scored["queue_rank"] = scored["queue_rank"].astype("Int64")
    signals = pd.DataFrame([{"group_id": g, "website": w} for g, w in AGENT_SITES.items()])
    # g1's two companies have 10-19 staff each: neither alone reaches 30.
    companies = pd.DataFrame([
        {"siren": "1", "group_id": "g1", "active": True, "band": "11"},
        {"siren": "2", "group_id": "g1", "active": True, "band": "11"},
        {"siren": "3", "group_id": "g2", "active": True, "band": "22"},
        {"siren": "4", "group_id": "g3", "active": True, "band": "12"},
        {"siren": "5", "group_id": "g4", "active": True, "band": "21"},
        {"siren": "6", "group_id": "g5", "active": True, "band": "11"},
        {"siren": "7", "group_id": "g6", "active": True, "band": "21"},
    ])  # fmt: skip
    funnel = {"stages": [
        {"id": "rge_rows", "label": "RGE registry rows", "count": 1000},
        {"id": "target_rows", "label": "Target qualifications", "count": 200},
        {"id": "active_companies", "label": "Active certified companies", "count": 8},
        {"id": "manager_expansion", "label": "+ same-manager companies", "count": 9,
         "detail": {"added": 1}},
        {"id": "groups", "label": "Groups", "count": 6},
    ]}  # fmt: skip
    return insights.Inputs(market, signals, scored, companies, funnel)


@pytest.fixture
def d():
    return inputs()


def test_f1_funnel_counts_and_the_roll_up(d, icp):
    f = insights.f1_funnel(d, icp)
    assert f.population == insights.MARKET
    counts = dict(zip(f.data["stage"], f.data["count"], strict=True))
    assert counts["RGE registry rows"] == 1000 and counts["Groups"] == 6
    assert counts["In segment (30-300 staff)"] == 5
    assert counts["Researched by the agent"] == 5 and counts["SDR queue"] == 3
    # g1 is in segment (40 staff) only because its two companies count together.
    assert list(f.tables["rolled_in"]["group_id"]) == ["g1"]
    assert "1 groups" in f.headline and "added 1 companies" in f.headline


def test_f2_leaves_references_out_of_the_correlation(d, icp):
    f = insights.f2_prescore(d, icp)
    assert f.population == insights.RESEARCHED
    assert len(f.data) == 5 and f.data["is_reference"].sum() == 1  # charted, marked
    levels = f.tables["by_level"].set_index("pre_score")
    assert levels["groups"].sum() == 4  # leads only
    assert levels.loc[0.9, "groups"] == 2 and levels.loc[0.9, "tier_a"] == 0.5
    assert "References sit at pre-score rank" in f.headline


def test_f3_signals_by_real_headcount(d, icp):
    f = insights.f3_tiers(d, icp)
    bands = f.data.set_index("headcount_band")
    assert bands.loc["30-59", "groups"] == 2  # g1 (45), g3 (35); the reference is left out
    assert bands.loc["30-59", "growth"] == pytest.approx(0.12, abs=0.01)
    assert bands.loc["100-199", "growth"] == 1.0
    assert "size_fit" not in f.data.columns  # the size curve sets it: not a finding
    tiers = f.tables["by_tier"].set_index("tier")
    assert tiers.loc["A", "groups"] == 2 and tiers.loc["A", "median_headcount"] == 95
    assert "2 of 4 researched leads are below the 60-200 sweet spot" in f.headline


def test_f4_appendix_has_no_chart(d, icp):
    f = insights.f4_size_appendix(d, icp)
    assert f.chart is None
    assert f.data.set_index("group_id").loc["g1", "ratio"] == pytest.approx(45 / 40, abs=0.01)


def test_f5_regions(d, icp):
    f = insights.f5_regions(d, icp)
    r = f.data.set_index("region")
    assert r.loc["84", "region_name"] == "Auvergne-Rhône-Alpes"
    assert r.loc["84", "in_segment"] == 3 and r.loc["84", "researched"] == 2  # not the ref
    assert r.loc["75", "queue"] == 2 and r.loc["75", "tier_a_rate"] == 0.5
    assert "11" not in r.index  # no in-segment group there


def test_f6_product_mix_labels_and_shares(d, icp):
    icp = icp.model_copy(deep=True)
    icp.market.line_labels = {HP: "heat pumps", PV: "solar"}
    f = insights.f6_product_mix(d, icp)
    shares = f.data.groupby("population")["share"].sum()
    assert shares.round(3).eq(1).all()
    market = f.data[f.data["population"] == "Market"].set_index("mix")
    assert market.loc["heat pumps + solar", "groups"] == 3
    assert market.loc["heat pumps only", "groups"] == 2
    researched = f.data[f.data["population"] == "Researched"]
    assert researched["groups"].sum() == 4  # leads only
    assert "Market 50%" in f.headline


def test_mix_label_order_and_unknown(icp):
    assert insights.mix_label([PV, HP], icp) == "heat_pump + solar"
    assert insights.mix_label([], icp) == "unknown (no certification)"


def test_f7_website_status(d, icp):
    f = insights.f7_websites(d, icp)
    status = f.data.set_index("group_id")["website_status"]
    assert status["g1"] == insights.SAME
    assert status["g2"] == insights.DIFFERENT
    assert status["g3"] == insights.FOUND
    assert status["g4"] == insights.NONE
    assert "For 2 of 5 researched groups" in f.headline


@pytest.mark.parametrize("finding", insights.FINDINGS, ids=lambda f: f.__name__)
def test_chart_specs_are_vega_lite_with_their_encodings(d, icp, finding):
    f = finding(d, icp)
    spec = json.loads(f.chart.to_json())
    assert spec["$schema"].startswith("https://vega.github.io/schema/vega-lite/")
    assert spec["title"]["text"] and spec["title"]["subtitle"]
    layers = spec.get("layer", [spec])
    assert {"x", "y"} <= set(layers[0]["encoding"])
    # Every encoded field is a column of the data the spec carries.
    columns = {k for rows in spec["datasets"].values() for row in rows for k in row}
    fields = {
        enc["field"]
        for layer in layers
        for enc in layer.get("encoding", {}).values()
        if isinstance(enc, dict) and "field" in enc
    }
    assert fields and fields <= columns


def test_cli_writes_tables_and_specs(d, tmp_path, capsys):
    d.market.to_parquet(tmp_path / "market.parquet")
    d.signals.to_parquet(tmp_path / "signals.parquet")
    d.scored.to_parquet(tmp_path / "scored.parquet")
    d.companies.to_parquet(tmp_path / "companies.parquet")
    (tmp_path / "funnel.json").write_text(json.dumps(d.funnel), encoding="utf-8")
    cli.main(["--data-dir", str(tmp_path), "insights"])
    out = tmp_path / "insights"
    for f in insights.FINDINGS:  # each finding's id is its function's name
        assert (out / f"{f.__name__}.csv").exists() and (out / f"{f.__name__}.vl.json").exists()
    assert (out / "f4_size.csv").exists() and not (out / "f4_size.vl.json").exists()
    assert "f1_funnel" in capsys.readouterr().out


def test_cli_without_data(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        cli.main(["--data-dir", str(tmp_path), "insights"])
