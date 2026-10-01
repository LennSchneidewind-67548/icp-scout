"""Command line entry point. Stages are added as their work packages land (docs/plan.md)."""

import argparse
import os
import sys
from pathlib import Path

from icp_scout import config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="icp-scout")
    parser.add_argument(
        "--config", help="ICP config path (default: $ICP_SCOUT_CONFIG or the example)"
    )
    parser.add_argument(
        "--data-dir", default="data", help="pulled and generated data (default: data)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show-config", help="print the loaded ICP config")
    source = sub.add_parser("source", help="pull the market, roll up groups, pre-filter")
    source.add_argument(
        "--limit", type=int, help="join at most N certified companies (for development)"
    )
    source.add_argument(
        "--offline", action="store_true", help="read the cache only, fail on a miss"
    )
    source.add_argument("--refresh", action="store_true", help="ignore the cache and fetch again")
    sub.add_parser("funnel", help="print the funnel of the last `source` run")
    research = sub.add_parser("research", help="research the shortlist with the agent")
    research.add_argument("--limit", type=int, help="research the top N shortlisted groups")
    research.add_argument(
        "--group", action="append", dest="groups", metavar="ID", help="only this group (repeatable)"
    )
    research.add_argument(
        "--offline", action="store_true", help="replay recordings only, fail on a miss"
    )
    research.add_argument(
        "--refresh", action="store_true", help="call the model again and overwrite recordings"
    )
    research.add_argument(
        "--recordings",
        help="recordings directory (default: $ICP_SCOUT_RECORDINGS or fixtures/llm; "
        "private/llm for the case)",
    )
    research.add_argument("--budget-usd", type=float, help="default: research.budget_usd")
    regrade = sub.add_parser("regrade", help="regrade the recorded evidence on the finer scales")
    regrade.add_argument(
        "--offline", action="store_true", help="replay recordings only, fail on a miss"
    )
    regrade.add_argument("--recordings", help="as for research")
    sub.add_parser("score", help="score, tier and rank; print the SDR queue")
    sub.add_parser("cost", help="cost per researched lead, from the ledger")
    sub.add_parser("insights", help="the findings: tables and chart specs to data/insights/")
    compare = sub.add_parser("compare", help="compare two research runs (e.g. two models)")
    compare.add_argument("run_a", help="data dir of the first run")
    compare.add_argument("run_b", help="data dir of the second run")
    args = parser.parse_args(argv)
    load_env()

    if args.command == "show-config":
        icp = config.load(args.config)
        print(icp.model_dump_json(indent=2))
    elif args.command == "source":
        from icp_scout import sourcing
        from icp_scout.http import CacheMiss

        icp = config.load(args.config)
        try:
            funnel = sourcing.run(
                icp, args.data_dir, limit=args.limit, offline=args.offline, refresh=args.refresh
            )
        except CacheMiss as e:
            sys.exit(f"--offline: {e}")
        print(funnel.render())
    elif args.command == "funnel":
        from icp_scout.funnel import Funnel

        path = Path(args.data_dir) / "funnel.json"
        if not path.exists():
            sys.exit(f"{path} not found: run `icp-scout source` first")
        print(Funnel.read(path).render())
    elif args.command == "research":
        from icp_scout import research as research_mod
        from icp_scout.llm import RecordingMiss

        if args.offline and args.refresh:
            sys.exit("--offline and --refresh exclude each other")
        icp = config.load(args.config)
        mode = "replay" if args.offline else "refresh" if args.refresh else "record"
        recordings = recordings_dir(args, mode)
        try:
            research_mod.run(
                icp, args.data_dir, limit=args.limit, mode=mode, recordings_dir=recordings,
                budget_usd=args.budget_usd, group_ids=args.groups,
            )  # fmt: skip
        except RecordingMiss as e:
            sys.exit(f"--offline: {e}")
        except (FileNotFoundError, ValueError) as e:
            sys.exit(str(e))
        print(research_mod.cost_report(args.data_dir))
    elif args.command == "regrade":
        from icp_scout.enrich import regrade as regrade_mod
        from icp_scout.llm import RecordingMiss

        icp = config.load(args.config)
        mode = "replay" if args.offline else "record"
        try:
            regrade_mod.run(
                icp, args.data_dir, mode=mode, recordings_dir=recordings_dir(args, mode)
            )
        except RecordingMiss as e:
            sys.exit(f"--offline: {e}")
        except FileNotFoundError as e:
            sys.exit(str(e))
    elif args.command == "score":
        from icp_scout import score

        icp = config.load(args.config)
        try:
            table = score.run(icp, args.data_dir)
        except FileNotFoundError as e:
            sys.exit(str(e))
        print(score.report(icp, table))
    elif args.command == "insights":
        from icp_scout import insights

        icp = config.load(args.config)
        try:
            findings = insights.run(icp, args.data_dir)
        except FileNotFoundError as e:
            sys.exit(str(e))
        print(insights.report(findings))
        print(f"\nWritten to {Path(args.data_dir) / 'insights'}/")
    elif args.command == "cost":
        from icp_scout.research import cost_report

        print(cost_report(args.data_dir))
    elif args.command == "compare":
        from icp_scout.research import compare

        try:
            print(compare(args.run_a, args.run_b))
        except FileNotFoundError as e:
            sys.exit(str(e))


def recordings_dir(args, mode: str) -> str:
    """--recordings, else $ICP_SCOUT_RECORDINGS, else the committed fixtures."""
    from icp_scout.research import DEFAULT_RECORDINGS

    recordings = args.recordings or os.environ.get("ICP_SCOUT_RECORDINGS") or DEFAULT_RECORDINGS
    config_path = Path(args.config or os.environ.get("ICP_SCOUT_CONFIG") or config.DEFAULT_PATH)
    committed = Path(recordings).resolve().is_relative_to(Path("fixtures").resolve())
    if mode != "replay" and committed and config_path.resolve() != config.DEFAULT_PATH.resolve():
        # ADR 0003: recordings of real companies never go under the committed fixtures/.
        sys.exit(
            f"{recordings} is committed: record the case with --recordings private/llm "
            "(or set ICP_SCOUT_RECORDINGS)"
        )
    return str(recordings)


def load_env(path: str | Path = ".env") -> None:
    """Read KEY=VALUE lines from .env into the environment (set variables win)."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    main()
