"""The ICP config: everything specific to one vendor and market, in one file."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_PATH = Path("config/icp.example.yaml")


class Vendor(BaseModel):
    name: str
    pitch: str


class SecondSource(BaseModel):
    """Installers outside the RGE registry, found in the company register."""

    naf_codes: list[str] = []
    # Whole words, matched case- and accent-insensitively against the company name.
    name_keywords: list[str] = []
    # Lowest INSEE headcount band code searched (e.g. "11" = 10-19 staff).
    min_headcount_band: str = "11"


class Market(BaseModel):
    country: str
    rge_domains: list[str] = Field(min_length=1)
    # Product line -> the RGE domains that prove it. Empty: each domain is its own line.
    product_lines: dict[str, list[str]] = {}
    # None or no NAF codes: the register is only used to enrich RGE companies.
    second_source: SecondSource | None = None
    # Companies to add by SIREN whatever the filters say (e.g. reference customers
    # that neither source finds), so they can be researched and scored like the rest.
    extra_sirens: list[str] = []

    @model_validator(mode="after")
    def _lines_use_known_domains(self) -> "Market":
        unknown = {d for ds in self.product_lines.values() for d in ds} - set(self.rge_domains)
        if unknown:
            raise ValueError(f"product_lines use domains not in rge_domains: {sorted(unknown)}")
        return self


class Segment(BaseModel):
    headcount_min: int
    headcount_max: int

    @model_validator(mode="after")
    def _ordered(self) -> "Segment":
        if self.headcount_min > self.headcount_max:
            raise ValueError("headcount_min is above headcount_max")
        return self


class Signal(BaseModel):
    id: str
    label: str
    weight: float = Field(gt=0)
    # What 0, 0.5 and 1 mean. The agent is shown it, so extraction stays consistent.
    definition: str | None = None


class Prefilter(BaseModel):
    shortlist_size: int = Field(default=175, gt=0)


class Research(BaseModel):
    """The research agent (WP2). The model must support the web_search/web_fetch
    tool versions in enrich/agent.py; recordings are per model."""

    model: str = "claude-opus-5-5"
    effort: str = "medium"
    max_searches: int = Field(default=5, ge=0)
    max_fetches: int = Field(default=6, ge=0)
    # Cap on each fetched page, in tokens. Pages are most of the input cost. None: no cap.
    max_page_tokens: int | None = Field(default=None, gt=0)
    # Stop starting new leads once this run's live spend passes this.
    budget_usd: float = Field(default=60, gt=0)
    concurrency: int = Field(default=4, ge=1)


class Tiers(BaseModel):
    A: float
    B: float


class Outreach(BaseModel):
    language: str
    translate_to: str | None = None


class IcpConfig(BaseModel):
    vendor: Vendor
    market: Market
    segment: Segment
    reference_customers: list[str] = []
    signals: list[Signal] = Field(min_length=1)
    tiers: Tiers
    outreach: Outreach
    prefilter: Prefilter = Prefilter()
    research: Research = Research()

    @model_validator(mode="after")
    def _unique_signals(self) -> "IcpConfig":
        ids = [s.id for s in self.signals]
        if len(ids) != len(set(ids)):
            raise ValueError("signal ids must be unique")
        return self


def load(path: str | Path | None = None) -> IcpConfig:
    """Load the config from `path`, else $ICP_SCOUT_CONFIG, else the example."""
    path = Path(path or os.environ.get("ICP_SCOUT_CONFIG") or DEFAULT_PATH)
    with path.open(encoding="utf-8") as f:
        return IcpConfig.model_validate(yaml.safe_load(f))
