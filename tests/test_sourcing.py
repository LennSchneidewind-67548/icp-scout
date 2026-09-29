import json
from itertools import pairwise

import httpx
import pandas as pd
import pytest
from conftest import ROOT, TODAY, FakeApis, load

from icp_scout import cli, config, group, sourcing
from icp_scout.http import CachedClient
from icp_scout.sources import rge, sirene
from icp_scout.sources.sirene import band_mid, band_range, name_matches

SIRENS = load("sirens.json")


def run_on_fixtures(data_dir, fake=None, **kwargs):
    icp = config.load(ROOT / "config" / "icp.example.yaml")
    fake = fake or FakeApis()
    kwargs.setdefault("transport", httpx.MockTransport(fake))
    return sourcing.run(icp, data_dir, today=TODAY, rate_per_s=0, log=lambda _: None, **kwargs)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    funnel = run_on_fixtures(data_dir)
    market = pd.read_parquet(data_dir / "market.parquet")
    companies = pd.read_parquet(data_dir / "companies.parquet")
    return funnel, market, companies


def group_of(out, key):
    _, market, companies = out
    gid = companies.set_index("siren").loc[SIRENS[key], "group_id"]
    return market.set_index("group_id").loc[gid]


def same_group(out, a, b):
    companies = out[2].set_index("siren")
    return companies.loc[SIRENS[a], "group_id"] == companies.loc[SIRENS[b], "group_id"]


# RGE rows


def test_rge_rows_grouped_by_siret_and_expired_dropped():
    rows = load("rge_lines_page1.json")["results"] + load("rge_lines_page2.json")["results"]
    rows = [r for r in rows if r["domaine"] in {"Pompe à chaleur : chauffage",
            "Panneaux solaires photovoltaïques", "Chauffage et/ou eau chaude solaire"}]  # fmt: skip
    active = [r for r in rows if rge.is_active(r, TODAY)]
    sites = rge.group_by_siret(active)

    brise = [s for s in sites.values() if s.siren == SIRENS["brise"]]
    assert len(brise) == 2  # two establishments
    first = next(s for s in brise if s.siret.endswith("00001"))
    assert first.domains == {"Pompe à chaleur : chauffage", "Panneaux solaires photovoltaïques"}
    assert first.phone == "02 98 00 00 01"
    assert not any(s.siren == SIRENS["expired"] for s in sites.values())


def test_rge_pull_follows_the_cursor_and_keeps_exact_domains(tmp_path, fake_apis):
    client = CachedClient("rge", tmp_path, rate_per_s=0, transport=httpx.MockTransport(fake_apis))
    rows = rge.fetch_rows(client, ["Pompe à chaleur : chauffage"])
    sirets = {r["siret"][:9] for r in rows}
    assert SIRENS["brise"] in sirets and SIRENS["artisan21"] in sirets  # both pages
    assert {r["domaine"] for r in rows} == {"Pompe à chaleur : chauffage"}
    assert fake_apis.calls == 2


# Bands


def test_band_math():
    assert band_range("11") == (10, 19)
    assert band_mid("12") == 34.5
    assert band_mid("00") == 0
    assert band_range("NN") is None and band_range(None) is None and band_mid("NN") is None


def test_group_headcount_sums_members_and_counts_unknowns():
    members = [
        sirene.Company(siren="1", name="a", source="rge", via="rge", band="11"),
        sirene.Company(siren="2", name="b", source="rge", via="rge", band="12"),
        sirene.Company(siren="3", name="c", source="rge", via="rge", band="NN"),
    ]
    assert group.Group("g1", members).headcount == {
        "headcount_low": 30,
        "headcount_mid": 49.0,
        "headcount_high": 68,
        "headcount_unknown": 1,
    }


def test_unknown_headcount_is_neither_in_nor_near_the_segment(out):
    row = group_of(out, "unknown")
    assert row.headcount_unknown == 1
    assert not row.in_segment and not row.near_band
    assert row.exclusion_reason == "headcount unknown"
    assert group_of(out, "giga").exclusion_reason == "above the segment"


# Keys


def test_person_key_normalizes_spelling_and_needs_the_birth_month():
    a = {"type_dirigeant": "personne physique", "nom": "DURANDAL (DURANDAL)",
         "prenoms": "AURÉLIE MARIE", "date_de_naissance": "1975-03"}  # fmt: skip
    b = {**a, "nom": "Durandal", "prenoms": "Aurelie"}
    assert group.person_key(a) == group.person_key(b) == "DURANDAL|AURELIE|1975-03"
    assert group.person_key({**a, "date_de_naissance": None}) is None


def test_phone_and_website_normalization():
    assert group.phone_key("+33 4 90 11 22 33") == group.phone_key("04.90.11.22.33") == "0490112233"
    assert group.phone_key("12") is None
    assert group.website_host("http://www.Ecotherm.example/nord") == "ecotherm.example"
    assert group.website_host("ecotherm.example") == "ecotherm.example"


def test_name_keywords_match_whole_words_only():
    keywords = ["solaire", "photovoltaïque", "énergie", "pac"]
    assert name_matches("NORDWATT PHOTOVOLTAIQUE", keywords)
    assert name_matches("Sud Énergie", ["energie"])
    assert name_matches("SARL PAC ET CLIM", keywords)
    assert not name_matches("ESPACE BATIMENT CONFORT", keywords)


# Grouping


def test_grouping_by_holding(out):
    assert same_group(out, "lumen_o", "lumen_e") and same_group(out, "lumen_o", "lumen_s")
    assert "same holding" in group_of(out, "lumen_o").link_reason


def test_grouping_by_manager_spelt_two_ways(out):
    assert same_group(out, "vallon_t", "vallon_p")
    assert "same manager" in group_of(out, "vallon_t").link_reason


def test_a_namesake_born_in_another_month_is_not_linked(out):
    assert not same_group(out, "vallon_t", "namesake")


def test_grouping_by_phone(out):
    assert same_group(out, "cap", "horizon")
    assert group_of(out, "cap").link_reason == "same phone"


def test_grouping_by_website(out):
    assert same_group(out, "eco_a", "eco_f")
    assert group_of(out, "eco_a").link_reason == "same website"


def test_grouping_by_a_shared_address(out):
    assert same_group(out, "bleu_c", "bleu_s")
    assert group_of(out, "bleu_c").link_reason == "same address"


def test_an_auditor_shared_by_two_companies_does_not_link_them(out):
    # Two audit officers, a firm and a person, both on both companies.
    assert not same_group(out, "rivage", "pic")
    assert not same_group(out, "rivage", "lumen_o")  # the firm also audits a subsidiary


def test_a_directory_domain_shared_by_many_companies_does_not_link_them(out):
    artisans = {group_of(out, f"artisan{i:02d}").name for i in range(1, 22)}
    assert len(artisans) == 21
    assert pd.isna(group_of(out, "artisan05").website)  # a directory page is not a website


def test_a_crowded_address_does_not_link(out):
    assert not same_group(out, "artisan01", "artisan02")  # four at one business center


def test_manager_expansion_finds_a_non_rge_sister_but_not_a_property_company(out):
    companies = out[2].set_index("siren")
    assert same_group(out, "vallon_t", "vallon_s")
    assert companies.loc[SIRENS["vallon_s"], "via"] == "manager"
    assert SIRENS["vallon_sci"] not in companies.index
    row = group_of(out, "vallon_t")
    assert row.headcount_mid == 3 * 14.5 and row.in_segment


def test_a_holding_of_small_subsidiaries_lands_in_the_segment_and_on_the_shortlist(out):
    for key in ["lumen_o", "lumen_e", "lumen_s"]:
        assert band_mid(out[2].set_index("siren").loc[SIRENS[key], "band"]) < 30
    row = group_of(out, "lumen_o")
    assert row.headcount_mid == 3 * 14.5
    assert row.in_segment and row.shortlisted
    assert set(row.product_lines) == {"heat_pump", "solar"}


# Second source


def test_a_non_rge_company_enters_via_the_second_source(out):
    row = group_of(out, "nordwatt")
    assert row.source == "register" and row.in_segment and row.pre_growth == 1.0
    assert row.pre_product_mix == 0.5  # unknown until the agent looks (WP2)
    companies = out[2].set_index("siren")
    assert companies.loc[SIRENS["nordwatt"], "via"] == "naf_search"
    assert SIRENS["espace"] not in companies.index  # "pac" inside "espace"
    assert SIRENS["plomb"] not in companies.index  # no energy word
    assert companies.loc[SIRENS["brise"], "source"] == "rge"  # found by both, kept once


def test_a_lapsed_rge_installer_comes_back_through_the_second_source(out):
    companies = out[2].set_index("siren")
    assert companies.loc[SIRENS["expired"], "via"] == "naf_search"
    assert list(companies.loc[SIRENS["expired"], "domains"]) == []


# Drops, funnel, outputs


def test_closed_and_unknown_companies_drop_out_with_a_reason(out):
    companies = out[2].set_index("siren")
    assert companies.loc[SIRENS["closed"], "exclusion_reason"] == "closed"
    assert companies.loc[SIRENS["missing"], "exclusion_reason"] == "not found in the register"


def test_the_funnel_never_grows_except_where_a_source_is_added(out):
    stages = out[0].stages
    for before, after in pairwise(stages):
        if after.kind != "add":
            assert after.count <= before.count, after.id
    by_id = {s.id: s for s in stages}
    assert by_id["active_rows"].count < by_id["target_rows"].count
    assert by_id["register_source"].detail["added"] == 2  # nordwatt, expired
    assert by_id["manager_expansion"].detail["added"] == 1
    assert all(s.reason for s in stages)


def test_every_row_outside_the_shortlist_has_a_reason(out):
    market = out[1]
    assert market[~market.shortlisted].exclusion_reason.notna().all()
    assert market[market.shortlisted].exclusion_reason.isna().all()


def test_shortlist_is_capped(tmp_path, monkeypatch):
    real_load = config.load

    def small(path=None):
        icp = real_load(path)
        icp.prefilter.shortlist_size = 3
        return icp

    monkeypatch.setattr(config, "load", small)
    run_on_fixtures(tmp_path)
    market = pd.read_parquet(tmp_path / "market.parquet")
    assert market.shortlisted.sum() == 3
    candidates = market[market.in_segment | market.near_band]
    cut = candidates[candidates.shortlisted].pre_score.min()
    assert (candidates[~candidates.shortlisted].pre_score <= cut).all()
    assert not market[~(market.in_segment | market.near_band)].shortlisted.any()


def test_source_offline_end_to_end(tmp_path, capsys):
    fake = FakeApis()
    run_on_fixtures(tmp_path, fake)
    online = pd.read_parquet(tmp_path / "market.parquet")

    # A re-run makes no calls; offline reads the cache only.
    calls = fake.calls
    cli.main(["--data-dir", str(tmp_path), "source", "--offline"])
    assert fake.calls == calls
    offline = pd.read_parquet(tmp_path / "market.parquet")
    assert list(offline.group_id) == list(online.group_id)
    assert "Shortlist" in capsys.readouterr().out

    cli.main(["--data-dir", str(tmp_path), "funnel"])
    assert "Groups" in capsys.readouterr().out
    assert json.loads((tmp_path / "funnel.json").read_text())["stages"][0]["id"] == "rge_rows"


def test_source_offline_fails_on_a_cache_miss(tmp_path):
    with pytest.raises(SystemExit, match="--offline"):
        cli.main(["--data-dir", str(tmp_path), "source", "--offline"])
