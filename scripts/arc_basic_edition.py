#!/usr/bin/env python3
"""Build a valid Arc edition directly from parsed RSS items.

This is the no-AI core path: useful for proving scrape -> parse -> Arc render
before inserting Apple Intelligence.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ITEMS = ROOT / "arc.rss-items.json"
DEFAULT_OUT = ROOT / "arc.edition.json"


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:90] or "story"


def clamp(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def build_story(item: dict) -> dict:
    headline = item.get("headline", "").strip()
    summary = clamp(item.get("summary", ""), 120)
    briefing = item.get("summary", "").strip() or headline
    if len(briefing) > 220:
        briefing = clamp(briefing, 220)
    story_id = f"{slug(item.get('category', 'news'))}-{slug(headline)}"
    return {
        "id": story_id,
        "headline": headline,
        "summary": summary or headline,
        "briefing": briefing,
        "publisher": item.get("source", ""),
        "published_at": item.get("published_at"),
        "reading_minutes": 1,
        "url": item.get("url"),
        "image_url": item.get("image_url"),
        "image_alt": item.get("image_alt"),
        "topics": [],
        "developing": False,
        "sources": [
            {
                "publisher": item.get("source", ""),
                "url": item.get("url"),
            }
        ],
    }


def build_edition(items: list[dict], locale: str, max_per_category: int, max_categories: int | None) -> dict:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        if not item.get("headline"):
            continue
        grouped.setdefault(item.get("category", "News"), []).append(build_story(item))
    categories = [
        {"name": name, "stories": stories[:max_per_category]}
        for name, stories in grouped.items()
        if stories
    ]
    if max_categories is not None:
        categories = categories[:max_categories]
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "locale": locale,
        "categories": categories,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(DEFAULT_ITEMS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--locale", default="en-US")
    parser.add_argument("--max-per-category", type=int, default=2)
    parser.add_argument("--max-categories", type=int, default=3)
    args = parser.parse_args()

    payload = json.loads(Path(args.items).read_text())
    edition = build_edition(payload.get("items", []), args.locale, args.max_per_category, args.max_categories)
    Path(args.out).write_text(json.dumps(edition, indent=2, ensure_ascii=False) + "\n")
    story_count = sum(len(category["stories"]) for category in edition["categories"])
    print(f"edition={args.out} categories={len(edition['categories'])} stories={story_count}")
    return 0 if story_count else 2


if __name__ == "__main__":
    raise SystemExit(main())
