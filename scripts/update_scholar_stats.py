#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch accurate Google Scholar profile totals via the SerpApi author endpoint.

Required environment variable: SERPAPI_KEY
Never estimate numbers from another bibliometric database.
On API errors, retain the existing snapshot rather than publishing made-up data.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUTHOR_ID = "ZAoEFaYAAAAJ"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "scholar-stats.json"
API = "https://serpapi.com/search.json"


def fetch_page(key: str, offset: int = 0) -> dict:
    query = urlencode({
        "engine": "google_scholar_author",
        "author_id": AUTHOR_ID,
        "hl": "en",
        "num": 100,
        "start": offset,
        "api_key": key,
    })
    request = Request(API + "?" + query, headers={"User-Agent": "ScholarHomepageUpdater/1.0"})
    with urlopen(request, timeout=40) as response:
        result = json.load(response)
    if result.get("error") or result.get("search_metadata", {}).get("status") == "Error":
        raise RuntimeError(result.get("error", "SerpApi returned an error"))
    return result


def whole_number(value) -> int:
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    integer = int(value)
    if integer < 0:
        raise ValueError("Negative metric from API")
    return integer


def main() -> None:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        raise RuntimeError("Set a GitHub Actions secret named SERPAPI_KEY first.")

    results = fetch_page(key)
    if not results.get("author") or not results.get("cited_by", {}).get("table"):
        raise RuntimeError("SerpApi did not return a complete Google Scholar author profile.")
    table = results["cited_by"]["table"]
    citations = whole_number(next(row["citations"]["all"] for row in table if "citations" in row))
    h_index = whole_number(next(row["h_index"]["all"] for row in table if "h_index" in row))

    # Google Scholar Author API provides at most 100 articles per page.
    # Count all unique citation IDs instead of counting only the first page.
    seen = set()
    offset = 0
    for page_index in range(30):
        page = results if page_index == 0 else fetch_page(key, offset)
        articles = page.get("articles", [])
        if not isinstance(articles, list):
            raise RuntimeError("Invalid article list; keeping previous snapshot.")
        for article in articles:
            identity = article.get("citation_id") or article.get("link") or article.get("title")
            if identity:
                seen.add(identity)
        if len(articles) < 100:
            break
        offset += 100
    else:
        raise RuntimeError("Too many pages to count safely; keeping previous snapshot.")

    if not seen:
        raise RuntimeError("No publications returned for the scholar profile; keeping previous snapshot.")
    stats = {
        "source": "Google Scholar",
        "author_id": AUTHOR_ID,
        "publications": len(seen),
        "h_index": h_index,
        "citations": citations,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(OUTPUT)
    print("Updated Google Scholar metrics successfully: " + json.dumps(stats))


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, ValueError, KeyError, StopIteration, RuntimeError) as exc:
        raise SystemExit(f"Scholar update failed; previous data preserved: {exc}") from exc
