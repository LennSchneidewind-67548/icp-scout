"""The ICP config: everything specific to one vendor and market, in one file."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_PATH = Path("config/icp.example.yaml")


class Vendor(BaseModel):
    name: str
    pitch: str


class Market(BaseModel):
    country: str
    rge_domains: list[str] = Field(min_length=1)


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
