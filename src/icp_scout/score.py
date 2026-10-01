"""WP3. The rubric: signals -> 1-10 score -> tier -> the SDR queue. Pure, deterministic.

score = 1 + 9 x weighted mean of signal values, weights from the ICP config.
Re-scoring after a weight change needs no model call, which is what makes the
live weight sliders in the app possible.

Two refinements against the saturation WP2 showed (most leads tied at the top):
- a signal with `grades` in the config takes the regrade pass's finer value;
- the size signal, where the agent put the group inside the band, follows the
  sweet-spot curve on the group's headcount (regrade estimate, else registry).
Leads still tied are ordered by how many signals have evidence, then by name.
Never by the pre-rank: it doesn't predict the agent's score.

References (config `reference_sirens`) are scored and ranked like any lead, as
calibration, but never take a place in the SDR queue.
"""

import json
from pathlib import Path

import pandas as pd

from icp_scout.config import IcpConfig, Segment


def size_curve(headcount: float | None, seg: Segment) -> float | None:
    """1 inside the sweet spot, linear down to edge_value at the band edges, edge_value
    beyond them. None when there is no headcount or no sweet spot."""
    if headcount is None or pd.isna(headcount) or not seg.sweet_spot:
        return None
    lo, hi = seg.sweet_spot
    if lo <= headcount <= hi:
        return 1.0
    if headcount < lo:
        frac = (
            (headcount - seg.headcount_min) / (lo - seg.headcount_min)
            if lo > seg.headcount_min
            else 1
        )
    else:
        frac = (
            (seg.headcount_max - headcount) / (seg.headcount_max - hi)
            if seg.headcount_max > hi
            else 1
        )
    frac = min(max(frac, 0.0), 1.0)
    return round(seg.edge_value + (1 - seg.edge_value) * frac, 4)


def load_regrades(data_dir: str | Path) -> dict[str, dict]:
    out = {}
    for path in sorted((Path(data_dir) / "regrade").glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r["status"] == "ok":
            out[r["group_id"]] = r["result"]
    return out


def score(
    icp: IcpConfig,
    signals: pd.DataFrame,
    market: pd.DataFrame,
    regrades: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """One row per researched group, best first: signal values, score, tier, rank,
    queue rank (None for references and leads past the queue), reason_en."""
    regrades = regrades or {}
    ok = signals[signals["status"] == "ok"]
    ids = [s.id for s in icp.signals]
    weights = {s.id: s.weight for s in icp.signals}
    seg = icp.segment
    market = market.set_index("group_id")
    refs = set(icp.reference_sirens)

    rows = []
    for gid, g in ok.groupby("group_id", sort=False):
        agent = dict(zip(g["signal"], g["value"], strict=True))
        backed = int(
            sum(bool(f) and len(e) > 0 for f, e in zip(g["found"], g["evidence"], strict=True))
        )
        rg = regrades.get(gid) or {}
        values = {s: float(agent.get(s) or 0.0) for s in ids}
        for s, grade in (rg.get("grades") or {}).items():
            if s in values:
                values[s] = float(grade["value"])
        m = market.loc[gid] if gid in market.index else None
        headcount = rg.get("headcount")
        source = "regrade" if headcount is not None else None
        if headcount is None and m is not None and not pd.isna(m["headcount_mid"]):
            headcount, source = float(m["headcount_mid"]), "registry"
        curve = size_curve(headcount, seg)
        if curve is not None and agent.get(seg.size_signal) == 1:
            values[seg.size_signal] = curve
        members = list(m["members"]) if m is not None else []
        rows.append({
            "group_id": gid,
            "name": g["name"].iloc[0],
            **values,
            "headcount": headcount,
            "headcount_source": source,
            "evidence_backed": backed,
            "is_reference": bool(refs & set(members)),
            "pre_score": m["pre_score"] if m is not None else None,
            "regraded": bool(rg),
            "phrases": rg.get("phrases") or {},
        })  # fmt: skip
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    total = sum(weights.values())
    table["score"] = (1 + 9 * sum(table[s] * w for s, w in weights.items()) / total).round(2)
    table["tier"] = table["score"].map(
        lambda x: "A" if x >= icp.tiers.A else "B" if x >= icp.tiers.B else "C"
    )
    table = table.sort_values(
        ["score", "evidence_backed", "name"], ascending=[False, False, True], kind="stable"
    ).reset_index(drop=True)
    table["rank"] = table.index + 1
    leads = table[~table["is_reference"]]
    queue = pd.Series(range(1, len(leads) + 1), index=leads.index)
    table["queue_rank"] = queue.where(queue <= icp.queue.size).astype("Int64")
    table["reason_en"] = [reason(icp, r) for r in table.to_dict("records")]
    return table.drop(columns="phrases")


def reason(icp: IcpConfig, row: dict) -> str:
    """One line for the SDR: score and tier, the strong signals, then the weakest."""
    by_weight = sorted(icp.signals, key=lambda s: -s.weight)

    def phrase(s) -> str:
        text = (row["phrases"].get(s.id) or "").strip().rstrip(".")
        if s.id == icp.segment.size_signal and row["headcount"] is not None:
            approx = f"~{row['headcount']:.0f} staff"
            if "staff" not in text.lower():
                text = ", ".join(filter(None, [approx, text]))
        return text or s.label.lower()

    strong = [phrase(s) for s in by_weight if row[s.id] >= 0.75]
    weak = min(by_weight, key=lambda s: (row[s.id], -s.weight))
    parts = [f"{row['score']:.1f} {row['tier']}", *strong]
    if row[weak.id] < 0.75:
        parts.append(f"weakest: {phrase(weak)}")
    if row["is_reference"]:
        parts.append("reference (calibration, not queued)")
    return " | ".join(parts)


def run(icp: IcpConfig, data_dir: str | Path = "data") -> pd.DataFrame:
    """data/scored.parquet from data/signals.parquet, data/market.parquet and data/regrade/."""
    data_dir = Path(data_dir)
    for name in ("signals.parquet", "market.parquet"):
        if not (data_dir / name).exists():
            raise FileNotFoundError(f"{data_dir / name} not found: run `icp-scout research` first")
    table = score(
        icp,
        pd.read_parquet(data_dir / "signals.parquet"),
        pd.read_parquet(data_dir / "market.parquet"),
        load_regrades(data_dir),
    )
    table.to_parquet(data_dir / "scored.parquet", index=False)
    return table


def tie_break_places(table: pd.DataFrame, size: int) -> int:
    """How many queue places a tie-break decided: the leads in the queue that share
    a score with the first lead past it. 0 when the cut falls between two scores."""
    leads = table[~table["is_reference"]].reset_index(drop=True)
    if len(leads) <= size:
        return 0
    cut = leads.loc[size, "score"]
    return int((leads.loc[: size - 1, "score"] == cut).sum())


def report(icp: IcpConfig, table: pd.DataFrame) -> str:
    size = icp.queue.size
    tiers = table["tier"].value_counts()
    lines = [
        (
            f"Scored {len(table)} groups ({table['regraded'].sum()} regraded): "
            f"{tiers.get('A', 0)} A, {tiers.get('B', 0)} B, {tiers.get('C', 0)} C; "
            f"{table['score'].nunique()} distinct scores"
        ),
        (
            f"Queue: top {size}, references excluded; {tie_break_places(table, size)} places "
            "decided by a tie-break"
        ),
        "",
    ]
    for r in table[table["queue_rank"].notna() | table["is_reference"]].itertuples():
        q = f"{r.queue_rank:>3}" if not pd.isna(r.queue_rank) else "ref"
        lines.append(f"{q} #{r.rank:<4}{r.name[:38]:<38}  {r.reason_en}")
    return "\n".join(lines)
