#!/usr/bin/env python3
"""Fetch Arc RSS sources and produce Apple Intelligence-ready input."""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import re
import sys
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "arc.config.json"
DEFAULT_JSON_OUT = ROOT / "arc.rss-items.json"
DEFAULT_TEXT_OUT = ROOT / "arc.ai-input.txt"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_publisher_suffix(title: str) -> str:
    return re.sub(r"\s[-|]\s[^-|]{2,80}$", "", title).strip()


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag in names:
            return clean_text("".join(child.itertext()))
    return ""


def child_attr(node: ET.Element, child_name: str, attr: str) -> str:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        if tag == child_name and child.attrib.get(attr):
            return child.attrib[attr].strip()
    return ""


def child_image_url(node: ET.Element) -> str | None:
    for child in list(node):
        tag = child.tag.rsplit("}", 1)[-1].lower()
        attrs = {key.rsplit("}", 1)[-1].lower(): value for key, value in child.attrib.items()}
        candidate = ""
        if tag in {"content", "thumbnail"} and attrs.get("url"):
            candidate = attrs["url"]
        elif tag == "image" and (attrs.get("url") or attrs.get("href")):
            candidate = attrs.get("url") or attrs.get("href") or ""
        elif tag == "enclosure" and attrs.get("url") and attrs.get("type", "").startswith("image/"):
            candidate = attrs["url"]
        if candidate and not re.search(r"rss-pixel|tracking|/pixel[.?/]", candidate, re.I):
            return normalize_image_url(html.unescape(candidate.strip()))
    return None


def normalize_image_url(url: str) -> str:
    url = re.sub(r"([?&])width=\d+", r"\1width=1200", url, flags=re.I)
    return re.sub(r"/standard/240/", "/standard/1024/", url, flags=re.I)


def parse_feed(xml_text: str, category: str, source: dict) -> list[dict]:
    source_name = source.get("name", "")
    source_url = source.get("url", "")
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        root = ET.fromstring(xml_text)

    entries = []
    nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    for node in nodes:
        title = child_text(node, ("title",))
        link = child_text(node, ("link",)) or child_attr(node, "link", "href")
        summary = child_text(node, ("description", "summary", "content", "encoded"))
        published = parse_date(child_text(node, ("pubdate", "published", "updated", "date")))
        image_url = child_image_url(node)
        guid = child_text(node, ("guid", "id")) or link or title
        if not title:
            continue
        entries.append(
            {
                "id": hashlib.sha1(f"{category}|{source_name}|{guid}".encode()).hexdigest()[:16],
                "category": category,
                "source": source_name,
                "source_type": source.get("type", ""),
                "source_url": source_url,
                "headline": title,
                "summary": summary,
                "url": link,
                "published_at": published,
                "image_url": image_url,
                "image_alt": title if image_url else None,
            }
        )
    return entries


def fetch(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ArcShortcutRSS/1.0 (+https://eggy-e4e.github.io/arc-news/)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def normalize_title(title: str, remove_suffix: bool) -> str:
    title = clean_text(title)
    return strip_publisher_suffix(title) if remove_suffix else title


def load_items(config: dict, timeout: int, max_sources: int | None) -> tuple[list[dict], list[dict]]:
    settings = config.get("settings", {})
    max_per_feed = int(settings.get("maximum_items_per_feed", 10))
    max_per_category = int(settings.get("maximum_stories_per_category", 5))
    lookback_hours = int(settings.get("lookback_hours", 30))
    remove_suffix = bool(settings.get("remove_publisher_suffix_from_titles", True))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    errors = []
    items = []
    source_count = 0

    for category in config.get("categories", []):
        if not category.get("enabled", True):
            continue
        category_items = []
        for source in category.get("sources", []):
            if max_sources is not None and source_count >= max_sources:
                break
            source_count += 1
            try:
                parsed = parse_feed(fetch(source["url"], timeout), category["name"], source)
            except (urllib.error.URLError, TimeoutError, ET.ParseError, KeyError, UnicodeDecodeError) as error:
                errors.append({"category": category.get("name", ""), "source": source.get("name", ""), "url": source.get("url", ""), "error": str(error)})
                continue
            for item in parsed[:max_per_feed]:
                item["headline"] = normalize_title(item["headline"], remove_suffix)
                item["summary"] = clean_text(item["summary"])
                if item["published_at"]:
                    try:
                        if datetime.fromisoformat(item["published_at"]) < cutoff:
                            continue
                    except ValueError:
                        pass
                category_items.append(item)
        category_items.sort(key=selection_key)
        items.extend(category_items[:max_per_category])
        if max_sources is not None and source_count >= max_sources:
            break
    return dedupe(items), errors


def selection_key(item: dict) -> tuple:
    source_rank = {"primary": 0, "publisher": 1, "aggregator": 2}.get(item.get("source_type", ""), 3)
    published = item.get("published_at") or ""
    try:
        recency = -datetime.fromisoformat(published).timestamp()
    except ValueError:
        recency = 0
    return (source_rank, recency)


def dedupe(items: list[dict]) -> list[dict]:
    seen = set()
    output = []
    for item in items:
        key = re.sub(r"[^a-z0-9]+", " ", item["headline"].lower()).strip()
        key = " ".join(key.split()[:12])
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def ai_input(config: dict, items: list[dict]) -> str:
    settings = config.get("settings", {})
    lines = [
        f"Generated at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Locale: {settings.get('locale', 'en-US')}",
        "",
        "RSS STORIES",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"CATEGORY: {item['category']}",
                f"SOURCE: {item['source']}",
                f"PUBLISHED: {item.get('published_at') or 'unknown'}",
                f"TITLE: {item['headline']}",
                f"URL: {item.get('url') or 'unknown'}",
                "SUMMARY:",
                textwrap.shorten(item.get("summary") or "", width=900, placeholder="..."),
                "---",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    parser.add_argument("--text-out", default=str(DEFAULT_TEXT_OUT))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--max-sources", type=int, default=None)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text())
    items, errors = load_items(config, args.timeout, args.max_sources)
    Path(args.json_out).write_text(json.dumps({"items": items, "errors": errors}, indent=2, ensure_ascii=False) + "\n")
    Path(args.text_out).write_text(ai_input(config, items))

    categories = {}
    for item in items:
        categories[item["category"]] = categories.get(item["category"], 0) + 1
    print(f"items={len(items)} categories={categories} errors={len(errors)}")
    for error in errors[:8]:
        print(f"error: {error['category']} / {error['source']}: {error['error']}", file=sys.stderr)
    return 0 if items else 2


if __name__ == "__main__":
    raise SystemExit(main())
