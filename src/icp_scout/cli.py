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
    sub.add_parser("cost", help="cost per researched lead, from the ledger")
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
        recordings = (
            args.recordings
            or os.environ.get("ICP_SCOUT_RECORDINGS")
            or research_mod.DEFAULT_RECORDINGS
        )
        mode = "replay" if args.offline else "refresh" if args.refresh else "record"
        config_path = Path(args.config or os.environ.get("ICP_SCOUT_CONFIG") or config.DEFAULT_PATH)
        committed = Path(recordings).resolve().is_relative_to(Path("fixtures").resolve())
        if (
            mode != "replay"
            and committed
            and config_path.resolve() != config.DEFAULT_PATH.resolve()
        ):
            # ADR 0003: recordings of real companies never go under the committed fixtures/.
            sys.exit(
                f"{recordings} is committed: record the case with --recordings private/llm "
                "(or set ICP_SCOUT_RECORDINGS)"
            )
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
    elif args.command == "cost":
        from icp_scout.research import cost_report

        print(cost_report(args.data_dir))
    elif args.command == "compare":
        from icp_scout.research import compare

        try:
            print(compare(args.run_a, args.run_b))
        except FileNotFoundError as e:
            sys.exit(str(e))


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
