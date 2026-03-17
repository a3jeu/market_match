from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ANCHOR_RE = re.compile(r'(<a\s+[^>]*href=")([^"]+)("[^>]*>)(.*?)(</a>)', re.IGNORECASE | re.DOTALL)


def load_url_label_map(selected_news_path: Path) -> dict[str, str]:
    payload = json.loads(selected_news_path.read_text(encoding="utf-8"))
    news = payload.get("news", []) if isinstance(payload, dict) else []

    if not isinstance(news, list):
        raise ValueError("selected_news.json must contain a 'news' list")

    url_to_label: dict[str, str] = {}

    for item in news:
        if not isinstance(item, dict):
            continue

        main_url = str(item.get("url") or item.get("original_url") or "").strip()
        main_source = str(item.get("source") or "").strip()
        if main_url and main_source:
            url_to_label.setdefault(main_url, main_source)

        additional_sources = item.get("additional_sources", [])
        if isinstance(additional_sources, list):
            for src in additional_sources:
                if not isinstance(src, dict):
                    continue
                src_url = str(src.get("url") or "").strip()
                src_name = str(src.get("source") or src.get("title") or "").strip()
                if src_url and src_name:
                    url_to_label.setdefault(src_url, src_name)

        market_context = item.get("market_context_source")
        if isinstance(market_context, dict):
            market_url = str(market_context.get("url") or "").strip()
            market_name = str(market_context.get("source") or market_context.get("title") or "").strip()
            if market_url and market_name:
                url_to_label.setdefault(market_url, market_name)

    return url_to_label


def patch_newsletter_file(newsletter_path: Path, url_to_label: dict[str, str]) -> int:
    # newline="" preserves original line endings exactly as read from disk.
    with newsletter_path.open("r", encoding="utf-8", newline="") as file:
        html = file.read()

    replaced_count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal replaced_count
        before, href, middle, label, after = match.groups()
        new_label = url_to_label.get(href)
        if not new_label or label == new_label:
            return match.group(0)
        replaced_count += 1
        return f"{before}{href}{middle}{new_label}{after}"

    patched_html = ANCHOR_RE.sub(repl, html)

    if patched_html != html:
        with newsletter_path.open("w", encoding="utf-8", newline="") as file:
            file.write(patched_html)

    return replaced_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch newsletter source labels using selected_news.json")
    parser.add_argument("--selected-news", required=True, help="Path to selected_news.json")
    parser.add_argument("newsletters", nargs="+", help="Newsletter HTML files to patch")
    args = parser.parse_args()

    selected_news_path = Path(args.selected_news)
    if not selected_news_path.exists():
        raise FileNotFoundError(f"Missing file: {selected_news_path}")

    url_to_label = load_url_label_map(selected_news_path)
    if not url_to_label:
        raise ValueError("No source mapping found in selected_news.json")

    total_replaced = 0
    for newsletter in args.newsletters:
        newsletter_path = Path(newsletter)
        if not newsletter_path.exists():
            raise FileNotFoundError(f"Missing file: {newsletter_path}")
        replaced = patch_newsletter_file(newsletter_path, url_to_label)
        total_replaced += replaced
        print(f"{newsletter_path}: {replaced} link label(s) updated")

    print(f"Total updated labels: {total_replaced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
