"""The ICP config: everything specific to one vendor and market, in one file."""

import os
from pathlib import Path
from typing import Literal

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
    # Headcount the vendor fits best (WP3). Inside it the size signal is 1; it falls
    # linearly to `edge_value` at the band edges. None: the agent's value stands.
    sweet_spot: tuple[int, int] | None = None
    edge_value: float = Field(default=0.6, ge=0, le=1)
    # The signal the sweet spot grades.
    size_signal: str = "size_fit"

    @model_validator(mode="after")
    def _ordered(self) -> "Segment":
        if self.headcount_min > self.headcount_max:
            raise ValueError("headcount_min is above headcount_max")
        if self.sweet_spot:
            lo, hi = self.sweet_spot
            if not self.headcount_min <= lo <= hi <= self.headcount_max:
                raise ValueError("sweet_spot must lie inside headcount_min..headcount_max")
        return self


class Signal(BaseModel):
    id: str
    label: str
    weight: float = Field(gt=0)
    # What 0, 0.5 and 1 mean. The agent is shown it, so extraction stays consistent.
    definition: str | None = None
    # A finer scale than `definition` (WP3). The regrade pass grades the recorded
    # evidence against it. Kept apart from `definition`, which is part of the
    # research prompt: changing that would invalidate every research recording.
    grades: str | None = None


class Prefilter(BaseModel):
    shortlist_size: int = Field(default=175, gt=0)


class Research(BaseModel):
    """The research agent (WP2). The model must support the web_search/web_fetch
    tool versions in enrich/agent.py; recordings are per model."""

    # "api": Messages API calls, billed per token (llm.py). "claude-code": the
    # `claude` CLI on the author's subscription, no API money (claude_code.py).
    backend: Literal["api", "claude-code"] = "api"
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    max_searches: int = Field(default=5, ge=0)
    max_fetches: int = Field(default=6, ge=0)
    # Cap on each fetched page, in tokens. Pages are most of the input cost. None: no cap.
    max_page_tokens: int | None = Field(default=None, gt=0)
    # Stop starting new leads once this run's live spend passes this.
    budget_usd: float = Field(default=60, gt=0)
    concurrency: int = Field(default=4, ge=1)
    # claude-code only: stop starting new leads once a usage window of the
    # subscription is this full (window name as the CLI reports it; others: 0.9).
    # The 7-day cap is lower so the plan stays usable for other work that week.
    max_utilization: dict[str, float] = {"five_hour": 0.9, "seven_day": 0.7}


class Tiers(BaseModel):
    A: float
    B: float


class Queue(BaseModel):
    """The SDR hand-off (WP3)."""

    size: int = Field(default=50, gt=0)


class Outreach(BaseModel):
    language: str
    translate_to: str | None = None


class IcpConfig(BaseModel):
    vendor: Vendor
    market: Market
    segment: Segment
    reference_customers: list[str] = []
    # A group with any of these SIRENs is a reference: scored and ranked as
    # calibration, never put in the SDR queue.
    reference_sirens: list[str] = []
    signals: list[Signal] = Field(min_length=1)
    tiers: Tiers
    outreach: Outreach
    prefilter: Prefilter = Prefilter()
    research: Research = Research()
    queue: Queue = Queue()

    @model_validator(mode="after")
    def _unique_signals(self) -> "IcpConfig":
        ids = [s.id for s in self.signals]
        if len(ids) != len(set(ids)):
            raise ValueError("signal ids must be unique")
        if self.segment.sweet_spot and self.segment.size_signal not in ids:
            raise ValueError(f"segment.size_signal {self.segment.size_signal!r} is not a signal")
        return self


def load(path: str | Path | None = None) -> IcpConfig:
    """Load the config from `path`, else $ICP_SCOUT_CONFIG, else the example."""
    path = Path(path or os.environ.get("ICP_SCOUT_CONFIG") or DEFAULT_PATH)
    with path.open(encoding="utf-8") as f:
        return IcpConfig.model_validate(yaml.safe_load(f))
