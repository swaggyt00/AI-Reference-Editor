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
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen

INDEX = Path(__file__).resolve().parents[1] / "docs" / "knowledge.json"
HOSTS = {"www.remotion.dev", "ffmpeg.org", "docs.opencv.org", "ai.google.dev"}
MAX_BYTES = 600_000
MAX_SOURCES = 60
NEW_SOURCES_PER_RUN = 4
DISCOVERY_PAGES = {'remotion-transitions','remotion-resources','remotion-motionblur'}
TECHNIQUE_WORDS = ('transition','fade','slide','wipe','blur','zoom','captions','animation','audio','text','tracking','effect','camera','media','font','color','render','video')


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
        self.links = []
        self._capture = None
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        tags = dict(attrs)
        if tag == "a" and isinstance(tags.get("href"),str) and len(self.links)<150:
            self.links.append(tags["href"])
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
    # Only the 3 known navigation pages are candidates for discovery.
    # No external resources, embedded media or article bodies are saved.
    return {"online_title": parser.title,
            "online_description": parser.description,
            "online_headings": parser.headings,
            "_found_links": parser.links}


def bounded_discover(home_url, hrefs, known_urls):
    """Select a few new official Remotion technique docs, no media or outside domains."""
    selected = []
    for href in hrefs[:150] if isinstance(hrefs,list) else []:
        if not isinstance(href,str) or len(href)>220:
            continue
        target = urljoin(home_url,href)
        parsed = urlparse(target)
        if parsed.scheme!="https" or parsed.hostname!="www.remotion.dev":
            continue
        path = parsed.path.lower().rstrip("/")
        if not path.startswith("/docs/") or path.count("/")>5:
            continue
        if path.endswith((".mp4",".mov",".avi",".webm",".mkv",".jpg",".png",
                          ".gif",".webp",".zip",".js",".exe",".py",".tsx")):
            continue
        if not any(w in path for w in TECHNIQUE_WORDS):
            continue
        normalized = "https://www.remotion.dev" + path
        if normalized in known_urls:
            continue
        known_urls.add(normalized)
        slug = re.sub(r"[^a-z0-9]+","-",path[6:]).strip("-")[:65]
        if not slug:
            continue
        selected.append({
            "id":"discovered-"+slug,
            "title":"Remotion documentation: "+slug.replace("-"," "),
            "url":normalized,
            "tags":[t for t in re.findall(r"[a-z0-9]{3,}",slug)[:8]],
            "note":"Official technique documentation discovered online; "
                   "not an installed or tested editing effect.",
            "mode":"reference","implementation":"research_only",
            "online_title":None,"online_description":None,
            "online_headings":[],"checked_at":None,"status":"not_checked"
        })
        if len(selected)>=NEW_SOURCES_PER_RUN:
            break
    return selected


def refresh(index_path=INDEX, fetch=get_metadata):
    index_path = Path(index_path)
    data = json.loads(index_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unexpected knowledge schema")
    stats = {"fetched": 0, "unavailable": 0, "discovered": 0}
    known_urls = {r.get("url","").rstrip("/") for r in data["sources"]}
    discovered_links = []
    for record in data["sources"][:MAX_SOURCES]:
        # A failed refresh NEVER deletes previously verified metadata.
        try:
            metadata = dict(fetch(record["url"]))
            hrefs = metadata.pop("_found_links",[])
            if record.get("id") in DISCOVERY_PAGES:
                discovered_links.append((record["url"],hrefs))
            record.update(metadata)
            record["status"] = "ok"
            record["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            stats["fetched"] += 1
        except Exception:
            record["status"] = "unavailable"
            stats["unavailable"] += 1
    # Discover new official documentation topics, never save video data.
    # Discovered topics have research_only status until manually implemented.
    for url,links in discovered_links:
        if len(data["sources"]) >= MAX_SOURCES or stats["discovered"] >= NEW_SOURCES_PER_RUN:
            break
        found=bounded_discover(url,links,known_urls)
        remaining=min(MAX_SOURCES-len(data["sources"]),
                      NEW_SOURCES_PER_RUN-stats["discovered"])
        data["sources"].extend(found[:remaining])
        stats["discovered"]+=len(found[:remaining])
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return stats


if __name__ == "__main__":
    result = refresh()
    print(f"Official online resources checked: {result['fetched']} updated, "
          f"{result['unavailable']} unavailable, {result['discovered']} newly discovered.")
