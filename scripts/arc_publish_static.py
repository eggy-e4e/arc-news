#!/usr/bin/env python3
"""Regenerate Arc's static edition and publish it to GitHub Pages."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "arc_open_core.py"
EDITION = ROOT / "arc.edition.json"
DEFAULT_REPO = Path("/Users/hoanghuuquoc/Documents/Codex/2026-07-12/let/work/arc-news-site")


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(DEFAULT_REPO))
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo)
    run([sys.executable, str(CORE), "--no-open"])
    shutil.copy2(EDITION, repo / "arc.edition.json")
    status = run(["git", "status", "--short", "arc.edition.json"], cwd=repo)
    if not status:
        print("No edition changes to publish.")
        return 0
    run(["git", "add", "arc.edition.json"], cwd=repo)
    message = "Update Arc edition " + datetime.now().astimezone().isoformat(timespec="minutes")
    run(["git", "commit", "-m", message], cwd=repo)
    if not args.no_push:
        run(["git", "push"], cwd=repo)
    print("Published arc.edition.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
