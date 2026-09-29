"""Command line entry point. Stages are added as their work packages land (docs/plan.md)."""

import argparse

from icp_scout import config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="icp-scout")
    parser.add_argument("--config", help="ICP config path (default: $ICP_SCOUT_CONFIG or the example)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show-config", help="print the loaded ICP config")
    args = parser.parse_args(argv)

    if args.command == "show-config":
        icp = config.load(args.config)
        print(icp.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
