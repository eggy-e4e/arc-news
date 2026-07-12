#!/usr/bin/env python3
"""Run the local Arc core pipeline and open the hosted reader."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRAPER = ROOT / "scripts" / "arc_scrape_rss.py"
BASIC_EDITION = ROOT / "scripts" / "arc_basic_edition.py"
MAKE_URL = ROOT / "scripts" / "arc_make_url.py"
EDITION = ROOT / "arc.edition.json"


def run(cmd: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, text=True, capture_output=True, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-sources", type=int, default=None)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    scrape_cmd = [sys.executable, str(SCRAPER)]
    if args.max_sources is not None:
        scrape_cmd.extend(["--max-sources", str(args.max_sources)])
    scrape = run(scrape_cmd)
    print(scrape.stdout.strip(), file=sys.stderr)

    edition = run([sys.executable, str(BASIC_EDITION)])
    print(edition.stdout.strip(), file=sys.stderr)

    url = run([sys.executable, str(MAKE_URL)], stdin=EDITION.read_text()).stdout.strip()
    print(url)
    if not args.no_open:
        subprocess.run(["open", url], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
