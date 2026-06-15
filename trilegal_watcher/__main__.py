"""CLI: python -m trilegal_watcher [industries|expertise|all]"""

import argparse
import sys

from .core import run_source
from .sources import ALL_SOURCES


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="trilegal_watcher",
        description="Scrape Trilegal listing pages and track new entries.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        default="all",
        choices=list(ALL_SOURCES.keys()) + ["all"],
        help="Which source to scrape (default: all).",
    )
    args = parser.parse_args(argv)

    if args.source == "all":
        targets = list(ALL_SOURCES.values())
    else:
        targets = [ALL_SOURCES[args.source]]

    total_new = 0
    for src in targets:
        total_new += run_source(src)
        print()

    print(f"All done. {total_new} new item(s) across {len(targets)} source(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
