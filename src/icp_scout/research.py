"""WP2. `icp-scout research`: the agent over the shortlist, and `icp-scout cost`.

Reads the shortlisted groups from data/market.parquet, researches up to
`concurrency` of them at a time, and writes data/research/<group_id>.json (the
validated answer and its flags) and data/signals.parquet (one row per group and
signal, which WP3 scores). A recorded lead replays at no cost, so a stopped run
resumes where it was.
"""

import json
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import pandas as pd

from icp_scout.config import IcpConfig
from icp_scout.enrich import agent
from icp_scout.llm import LLM, RecordingMiss, read_ledger, write_json

DEFAULT_RECORDINGS = Path("fixtures/llm")


def run(
    icp: IcpConfig,
    data_dir: str | Path = "data",
    *,
    limit: int | None = None,
    mode: str = "record",
    recordings_dir: str | Path = DEFAULT_RECORDINGS,
    budget_usd: float | None = None,
    group_ids: list[str] | None = None,
    client=None,
    log=lambda msg: print(msg, file=sys.stderr),
) -> list[dict]:
    data_dir = Path(data_dir)
    leads = shortlist(data_dir, group_ids, limit)
    budget = budget_usd if budget_usd is not None else icp.research.budget_usd
    llm = LLM(recordings_dir, mode, data_dir / "ledger.jsonl", client=client)
    log(f"Researching {len(leads)} groups ({mode}, {icp.research.model}, budget ${budget:g}) ...")

    results, todo = [], iter(leads)
    stopped = False
    with ThreadPoolExecutor(icp.research.concurrency) as pool:
        running = set()
        while True:
            while len(running) < icp.research.concurrency and not stopped:
                if llm.spent_usd >= budget:
                    stopped = True
                    log(f"Budget reached: ${llm.spent_usd:.2f} spent; no new leads started.")
                    break
                lead = next(todo, None)
                if lead is None:
                    break
                running.add(pool.submit(_one, icp, llm, lead))
            if not running:
                break
            done, running = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                out = future.result()  # RecordingMiss propagates: --offline fails loudly
                write_json(data_dir / "research" / f"{out['group_id']}.json", out)
                results.append(out)
                log(f"  {out['group_id']} {out['name']}: {out['status']}"
                    + (f" ({out['reason']})" if out["reason"] else "")
                    + (f", {len(out['flags'])} flags" if out["flags"] else ""))  # fmt: skip

    order = {lead["group_id"]: i for i, lead in enumerate(leads)}
    results.sort(key=lambda r: order[r["group_id"]])
    write_signals(icp, data_dir)
    log(f"Done: {len(results)} of {len(leads)} researched, ${llm.spent_usd:.2f} spent live.")
    return results


def _one(icp: IcpConfig, llm: LLM, lead: dict) -> dict:
    try:
        return agent.research(icp, llm, lead)
    except RecordingMiss:
        raise
    except Exception as e:  # noqa: BLE001 - an API error fails this lead, not the run
        return {"group_id": lead["group_id"], "name": lead["name"], "model": icp.research.model,
                "calls": None, "status": "failed", "reason": f"{type(e).__name__}: {e}"[:500],
                "flags": [], "result": None}  # fmt: skip


def shortlist(data_dir: Path, group_ids: list[str] | None, limit: int | None) -> list[dict]:
    path = data_dir / "market.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run `icp-scout source` first")
    market = pd.read_parquet(path)
    rows = market[market["shortlisted"]].sort_values("pre_score", ascending=False, kind="stable")
    if group_ids:
        missing = set(group_ids) - set(rows["group_id"])
        if missing:
            raise ValueError(f"not on the shortlist: {', '.join(sorted(missing))}")
        rows = rows[rows["group_id"].isin(group_ids)]
    if limit is not None:
        rows = rows.head(limit)
    return [_row(r) for r in rows.to_dict("records")]


def _row(r: dict) -> dict:
    return {k: (list(v) if hasattr(v, "tolist") and not isinstance(v, str) else v)
            for k, v in r.items()}  # fmt: skip


def write_signals(icp: IcpConfig, data_dir: Path) -> pd.DataFrame:
    """data/signals.parquet from every data/research/*.json: one row per group and signal."""
    rows = []
    for path in sorted((data_dir / "research").glob("*.json")):
        out = json.loads(path.read_text(encoding="utf-8"))
        signals = (out["result"] or {}).get("signals", {})
        for s in icp.signals:
            sig = signals.get(s.id)
            rows.append({
                "group_id": out["group_id"],
                "name": out["name"],
                "status": out["status"],
                "signal": s.id,
                "value": sig["value"] if sig else None,
                "found": sig["found"] if sig else False,
                "rationale_en": sig["rationale_en"] if sig else None,
                "evidence": sig["evidence"] if sig else [],
                "flags": [f["code"] for f in out["flags"] if f["signal"] in (s.id, None)],
                "website": (out["result"] or {}).get("website"),
                "notes_en": (out["result"] or {}).get("notes_en"),
                "reason": out["reason"],
            })  # fmt: skip
    table = pd.DataFrame(rows)
    table.to_parquet(data_dir / "signals.parquet", index=False)
    return table


# `icp-scout cost`


def cost_report(data_dir: str | Path) -> str:
    """Cost per lead from the ledger. Each recording counts once, at the cost it was
    recorded at, however often it was replayed: the cost of producing the data."""
    data_dir = Path(data_dir)
    ledger = read_ledger(data_dir / "ledger.jsonl")
    if not ledger:
        return f"No ledger at {data_dir / 'ledger.jsonl'}: run `icp-scout research` first."
    calls = pd.DataFrame(ledger)
    unique = calls.drop_duplicates("key")
    per_lead = unique.groupby("lead").agg(
        usd=("usd", "sum"), calls=("key", "count"), input=("input_tokens", "sum"),
        cache_write=("cache_write_tokens", "sum"), cache_read=("cache_read_tokens", "sum"),
        output=("output_tokens", "sum"), searches=("web_searches", "sum"),
        fetches=("web_fetches", "sum"),
    )  # fmt: skip
    prompt = per_lead[["input", "cache_write", "cache_read"]].sum().sum()
    hit = per_lead["cache_read"].sum() / prompt if prompt else 0.0
    status = _statuses(data_dir)
    live = calls[~calls["replayed"]]
    usd = per_lead["usd"]
    lines = [
        f"Leads researched   {len(per_lead):,}  ({', '.join(sorted(unique['model'].unique()))})",
        f"Total cost         ${usd.sum():,.2f}  ({len(unique):,} recorded calls)",
        (
            f"Cost per lead      mean ${usd.mean():.3f}  p50 ${usd.quantile(0.5):.3f}  "
            f"p90 ${usd.quantile(0.9):.3f}  max ${usd.max():.3f}"
        ),
        (
            f"Per lead (mean)    {per_lead['calls'].mean():.1f} calls, "
            f"{per_lead['input'].mean():,.0f} input + {per_lead['cache_write'].mean():,.0f} "
            f"cache-write + {per_lead['cache_read'].mean():,.0f} cache-read + "
            f"{per_lead['output'].mean():,.0f} output tokens, "
            f"{per_lead['searches'].mean():.1f} searches, {per_lead['fetches'].mean():.1f} fetches"
        ),
        f"Cache hit rate     {hit:.0%} of prompt tokens read from cache",
        (
            f"This ledger        {len(live):,} live calls (${live['usd'].sum():,.2f}), "
            f"{len(calls) - len(live):,} replayed"
        ),
    ]
    if status:
        flagged = sum(1 for s in status.values() if s["status"] == "ok" and s["flags"])
        failed = [f"{g} ({s['reason']})" for g, s in status.items() if s["status"] == "failed"]
        detail = f": {'; '.join(failed)}" if failed else ""
        lines.append(f"Failed leads       {len(failed):,}{detail}")
        lines.append(
            f"Flagged leads      {flagged:,} (a value without evidence, or evidence "
            "citing a URL the agent never retrieved)"
        )
    return "\n".join(lines)


def _statuses(data_dir: Path) -> dict[str, dict]:
    out = {}
    for path in sorted((data_dir / "research").glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        out[r["group_id"]] = r
    return out


# `icp-scout compare`


def compare(dir_a: str | Path, dir_b: str | Path) -> str:
    """Two research runs over the same leads (e.g. two models), side by side: cost,
    signals found, flags, and where the values disagree. No model call."""
    runs = {}
    for d in (Path(dir_a), Path(dir_b)):
        path = d / "signals.parquet"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found: run `icp-scout research` there first")
        runs[d.name] = (pd.read_parquet(path), read_ledger(d / "ledger.jsonl"))
    (a, (sa, la)), (b, (sb, lb)) = runs.items()
    both = sorted(set(sa["group_id"]) & set(sb["group_id"]))
    lines = [f"{len(both)} leads researched in both {a} and {b}", ""]

    width = max(len(a), len(b), 6)
    lines.append(f"{'':<22}{a:>{width}}  {b:>{width}}")
    rows = [_run_stats(s[s["group_id"].isin(both)], led, both) for s, led in ((sa, la), (sb, lb))]
    for label in rows[0]:
        lines.append(f"{label:<22}{rows[0][label]:>{width}}  {rows[1][label]:>{width}}")

    ok_a = sa[sa["group_id"].isin(both) & (sa["status"] == "ok")]
    ok_b = sb[sb["group_id"].isin(both) & (sb["status"] == "ok")]
    joined = ok_a.merge(ok_b, on=["group_id", "signal"], suffixes=("_a", "_b"))
    lines += ["", "Agreement per signal (leads both researched without failure)"]
    for signal, g in joined.groupby("signal", sort=False):
        same = (g["value_a"] == g["value_b"]).mean()
        diff = (g["value_a"] - g["value_b"]).abs().mean()
        lines.append(f"  {signal:<20}same value {same:>5.0%}   mean |difference| {diff:.2f}")
    differ = joined[joined["value_a"] != joined["value_b"]]
    if len(differ):
        lines += ["", f"Disagreements ({a} vs {b}): read the evidence for these"]
        for r in differ.itertuples():
            lines.append(f"  {r.group_id} {r.name_a[:30]:<30} {r.signal:<16}"
                         f"{r.value_a:g} vs {r.value_b:g}")  # fmt: skip
    return "\n".join(lines)


def _run_stats(signals: pd.DataFrame, ledger: list[dict], leads: list[str]) -> dict[str, str]:
    calls = pd.DataFrame(ledger).drop_duplicates("key") if ledger else pd.DataFrame()
    calls = calls[calls["lead"].isin(leads)] if len(calls) else calls
    per_lead = calls.groupby("lead")["usd"].sum() if len(calls) else pd.Series(dtype=float)
    status = signals.drop_duplicates("group_id")["status"]
    flagged = signals[signals["flags"].map(len) > 0]["group_id"].nunique()
    tokens = calls[["input_tokens", "cache_write_tokens", "cache_read_tokens"]].sum().sum()
    return {
        "model": ", ".join(sorted(calls["model"].unique())) if len(calls) else "?",
        "cost per lead (mean)": f"${per_lead.mean():.3f}" if len(per_lead) else "?",
        "cost, these leads": f"${per_lead.sum():.2f}",
        "prompt tokens / lead": f"{tokens / max(len(per_lead), 1):,.0f}",
        "output tokens / lead": f"{calls['output_tokens'].sum() / max(len(per_lead), 1):,.0f}"
        if len(calls) else "?",
        "searches / lead": f"{calls['web_searches'].sum() / max(len(per_lead), 1):.1f}"
        if len(calls) else "?",
        "failed leads": f"{(status == 'failed').sum()}",
        "flagged leads": f"{flagged}",
        "signals found": f"{signals['found'].mean():.0%}",
        "mean value": f"{signals['value'].mean():.2f}",
    }  # fmt: skip
