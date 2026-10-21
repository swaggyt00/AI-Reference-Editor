#!/usr/bin/env python3
"""Refresh public editing documentation metadata for GitHub Pages knowledge.

NO videos, screenshots, whole articles, personal uploads or API keys downloaded.
Untrusted HTML is parsed ONLY as title/description/headings with strict limits.
Run from repository root with Python 3.11+, network access, no extra packages.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

INDEX = Path(__file__).resolve().parents[1] / "docs" / "knowledge.json"
HOSTS = {"www.remotion.dev", "ffmpeg.org", "docs.opencv.org", "ai.google.dev"}
MAX_BYTES = 260_000


def clean_text(value, limit=220):
    # Text returned by web sites is untrusted input, never code or instructions.
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    # Keep plain printable text, avoid markdown/XML structures within prompts.
    return value.replace("<", "").replace(">", "").replace("{", "").replace("}", "")[:limit]


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings = []
        self._capture = None
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        tags = dict(attrs)
        if tag == "meta" and tags.get("name", "").lower() == "description":
            self.description = clean_text(tags.get("content", ""), 260)
        if tag in ("title", "h1", "h2"):
            self._capture = tag
            self._buffer = []

    def handle_data(self, data):
        if self._capture and len("".join(self._buffer)) < 200:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag != self._capture:
            return
        value = clean_text(" ".join(self._buffer), 100)
        if tag == "title":
            self.title = value
        elif value and len(self.headings) < 8 and value not in self.headings:
            self.headings.append(value)
        self._capture = None
        self._buffer = []


def get_metadata(url, opener=urlopen):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS:
        raise ValueError("Unapproved official documentation host")
    request = Request(url, headers={
        "User-Agent": "AI-Reference-Editor-Knowledge-Index/1.0 (documentation metadata only)",
        "Accept": "text/html",
    })
    with opener(request, timeout=12) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in HOSTS:
            raise ValueError("Unapproved redirect")
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            raise ValueError("Source is not HTML")
        html = response.read(MAX_BYTES + 1)
        if len(html) > MAX_BYTES:
            # Never fetch huge full FFmpeg docs; its curated note remains.
            raise ValueError("HTML is too large for bounded metadata inspection")
    parser = MetadataParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    if not parser.title and not parser.description:
        raise ValueError("No readable HTML metadata")
    return {"online_title": parser.title,
            "online_description": parser.description,
            "online_headings": parser.headings}


def refresh(index_path=INDEX, fetch=get_metadata):
    index_path = Path(index_path)
    data = json.loads(index_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unexpected knowledge schema")
    stats = {"fetched": 0, "unavailable": 0}
    for record in data["sources"]:
        # A failed refresh NEVER deletes previously verified metadata.
        try:
            metadata = fetch(record["url"])
            record.update(metadata)
            record["status"] = "ok"
            record["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            stats["fetched"] += 1
        except Exception:
            record["status"] = "unavailable"
            stats["unavailable"] += 1
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return stats


if __name__ == "__main__":
    result = refresh()
    print(f"Official online resources checked: {result['fetched']} updated, "
          f"{result['unavailable']} unavailable.")
