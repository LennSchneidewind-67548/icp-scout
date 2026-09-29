"""WP1. The sourcing funnel: a count and a reason at every stage, written to data/funnel.json.

`count` is what is still in play after the stage. Stages of kind "filter" or
"merge" never grow; "add" stages bring in companies from another source (the
register search, the manager expansion) and say how many in `detail["added"]`.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Stage:
    id: str
    label: str
    count: int
    reason: str
    kind: str = "filter"  # "filter", "add" or "merge"
    detail: dict = field(default_factory=dict)


@dataclass
class Funnel:
    stages: list[Stage] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def add(self, id: str, label: str, count: int, reason: str, kind: str = "filter", **detail):
        self.stages.append(Stage(id, label, count, reason, kind, detail))

    def write(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        body = {"meta": self.meta, "stages": [asdict(s) for s in self.stages]}
        Path(path).write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def read(cls, path: str | Path) -> "Funnel":
        body = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Stage(**s) for s in body["stages"]], body.get("meta", {}))

    def render(self) -> str:
        width = max(len(s.label) for s in self.stages)
        lines = []
        for s in self.stages:
            lines.append(f"{s.label:<{width}}  {s.count:>8,}  {s.reason}")
        return "\n".join(lines)
