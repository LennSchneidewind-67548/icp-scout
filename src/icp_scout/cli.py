"""Command line entry point. Stages are added as their work packages land (docs/plan.md)."""

import argparse
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
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    main()
