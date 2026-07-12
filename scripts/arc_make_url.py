#!/usr/bin/env python3
"""Read Arc edition JSON and print the hosted Arc URL with ?edition=."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse


DEFAULT_ARC_URL = "https://arc-news.oneplus2x69.workers.dev/"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arc-url", default=DEFAULT_ARC_URL)
    parser.add_argument("edition_json", nargs="?", help="Edition JSON text. Reads stdin when omitted.")
    args = parser.parse_args()

    raw = args.edition_json if args.edition_json is not None else sys.stdin.read()
    raw = raw.strip()
    parsed = json.loads(raw)
    compact = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
    separator = "&" if "?" in args.arc_url else "?"
    print(f"{args.arc_url}{separator}edition={urllib.parse.quote(compact, safe='')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
