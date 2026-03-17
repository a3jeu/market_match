from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import extract_body_html


def next_edition_number(history_file: Path | None = None) -> int:
    if history_file is None:
        history_file = Path(__file__).resolve().parents[3] / "data" / "published_news.json"

    if not history_file.exists():
        return 1

    try:
        payload = json.loads(history_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 1

    editions = payload.get("editions", [])
    if not editions:
        return 1

    latest = max((int(item.get("edition_number", 0)) for item in editions), default=0)
    return latest + 1


def _build_news_html(item: dict[str, Any], lang: str, index: int) -> str:
    if lang == "fr":
        title = item.get("title_fr", "")
        intro = item.get("intro_fr", "")
        essentials = item.get("essentiel_fr", "")
        practice = item.get("pratique_fr", "")
        breakdown = item.get("decryptage_fr", "")
        stake = item.get("enjeu_fr", "")
        verdict = item.get("verdict_fr", "")
        labels = {
            "essentials": "L’essentiel",
            "practice": "En pratique",
            "breakdown": "Décryptage",
            "stake": "L'enjeu",
            "verdict": "Verdict",
            "sources": "Sources",
        }
    else:
        title = item.get("title_en", "")
        intro = item.get("intro_en", "")
        essentials = item.get("essentials_en", "")
        practice = item.get("in_practice_en", "")
        breakdown = item.get("breakdown_en", "")
        stake = item.get("whats_at_stake_en", "")
        verdict = item.get("verdict_en", "")
        labels = {
            "essentials": "The Essentials",
            "practice": "In Practice",
            "breakdown": "Breakdown",
            "stake": "What's at Stake",
            "verdict": "Verdict",
            "sources": "Sources",
        }

    source_links = "".join(
        f'<li><a href="{s.get("url", "")}" target="_blank" rel="noopener">{s.get("label", "Source")}</a></li>'
        for s in item.get("sources", [])
    )

    return (
        f"<article><h2>{index}. {title}</h2>"
        f"<p>{intro}</p>"
        f"<p><strong>{labels['essentials']} :</strong> {essentials}</p>"
        f"<p><strong>{labels['practice']} :</strong> {practice}</p>"
        f"<p><strong>{labels['breakdown']} :</strong> {breakdown}</p>"
        f"<p><strong>{labels['stake']} :</strong> {stake}</p>"
        f"<p><strong>{labels['verdict']} :</strong> {verdict}</p>"
        f"<p><strong>{labels['sources']} :</strong></p><ul>{source_links}</ul>"
        "</article>"
    )


def render_newsletter_html(
    *,
    lang: str,
    # title: str,
    intro_sentence: str,
    intro_bullets: list[str],
    news_items: list[dict[str, Any]],
) -> str:
    html_lang = "fr" if lang == "fr" else "en"
    intro_list = "".join(f"<li>{bullet}</li>" for bullet in intro_bullets)
    news_html = "\n".join(_build_news_html(item, lang, idx) for idx, item in enumerate(news_items, start=1))

    if lang == "fr":
        signature_html = (
            '<footer style="border-top: 2px solid #e5e7eb; margin-top: 40px; padding-top: 20px; color: #6b7280;">'
            '<p style="font-style: italic; margin: 0;">Créez le futur</p>'
            '<p style="font-weight: bold; margin: 4px 0 0;">Tommy Gagné</p>'
            "</footer>"
        )
    else:
        signature_html = (
            '<footer style="border-top: 2px solid #e5e7eb; margin-top: 40px; padding-top: 20px; color: #6b7280;">'
            '<p style="font-style: italic; margin: 0;">Create the future</p>'
            '<p style="font-weight: bold; margin: 4px 0 0;">Tommy Gagné</p>'
            "</footer>"
        )

    return f"""
<!doctype html>
<html lang=\"{html_lang}\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{title}</title>
    <style>
      body {{ font-family: Arial, Helvetica, sans-serif; max-width: 900px; margin: 0 auto; padding: 24px; line-height: 1.6; color: #1f2937; }}
      h1 {{ margin-bottom: 8px; }}
      h2 {{ margin-top: 28px; }}
      article {{ border-top: 1px solid #e5e7eb; padding-top: 16px; margin-top: 16px; }}
      ul {{ padding-left: 20px; }}
      a {{ color: #1d4ed8; text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
    </style>
  </head>
  <body>
    <h1>{title}</h1>
    <p>{intro_sentence}</p>
    <ul>{intro_list}</ul>
    {news_html}
    {signature_html}
  </body>
</html>"""


def export_edition(
    *,
    project_root: Path,
    writing_model: str,
    research_model: str,
    edition_number: int,
    edition_date: str,
    title_fr: str,
    title_en: str,
    intro_payload: dict[str, Any],
    news_items: list[dict[str, Any]],
    newsletter_html_fr: str,
    newsletter_html_en: str,
    facebook_fr: str,
    linkedin_fr: str,
    twitter_fr: str,
) -> Path:
    edition_dir = project_root / "editions" / f"edition_{edition_number}_{edition_date}"
    edition_dir.mkdir(parents=True, exist_ok=True)

    (edition_dir / "metadata.json").write_text(
        json.dumps(
            {
                "edition_number": edition_number,
                "edition_date": edition_date,
                "news_count": len(news_items),
                "writing_model": writing_model,
                "research_model": research_model,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (edition_dir / "title_fr.json").write_text(json.dumps({"title_fr": title_fr}, ensure_ascii=False, indent=2), encoding="utf-8")
    (edition_dir / "title_en.json").write_text(json.dumps({"title_en": title_en}, ensure_ascii=False, indent=2), encoding="utf-8")

    (edition_dir / "introduction_fr.json").write_text(
        json.dumps(
            {
                "intro_sentence_fr": intro_payload.get("intro_sentence_fr", ""),
                "intro_bullets_fr": intro_payload.get("intro_bullets_fr", []),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (edition_dir / "introduction_en.json").write_text(
        json.dumps(
            {
                "intro_sentence_en": intro_payload.get("intro_sentence_en", ""),
                "intro_bullets_en": intro_payload.get("intro_bullets_en", []),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    for idx, item in enumerate(news_items, start=1):
        (edition_dir / f"news_{idx:02d}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (edition_dir / f"image_prompt_news_{idx:02d}.json").write_text(
            json.dumps({"image_prompt_en": item.get("image_prompt_en", "")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if news_items:
        (edition_dir / "thumbnail_prompt_news_01.json").write_text(
            json.dumps({"image_prompt_en": news_items[0].get("image_prompt_en", "")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    (edition_dir / "facebook_fr.json").write_text(
        json.dumps({"facebook_fr": facebook_fr}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (edition_dir / "linkedin_fr.json").write_text(
        json.dumps({"linkedin_fr": linkedin_fr}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (edition_dir / "twitter_fr.json").write_text(
        json.dumps({"twitter_fr": twitter_fr}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (edition_dir / "newsletter_fr.html").write_text(newsletter_html_fr, encoding="utf-8")
    (edition_dir / "newsletter_en.html").write_text(newsletter_html_en, encoding="utf-8")

    share_dir = edition_dir / "share"
    share_dir.mkdir(parents=True, exist_ok=True)

    (share_dir / "newsletter_fr.html").write_text(extract_body_html(newsletter_html_fr), encoding="utf-8")
    (share_dir / "newsletter_en.html").write_text(extract_body_html(newsletter_html_en), encoding="utf-8")
    (share_dir / "title_fr.txt").write_text(title_fr, encoding="utf-8")
    (share_dir / "title_en.txt").write_text(title_en, encoding="utf-8")
    (share_dir / "facebook_fr.txt").write_text(facebook_fr, encoding="utf-8")
    (share_dir / "linkedin_fr.txt").write_text(linkedin_fr, encoding="utf-8")
    (share_dir / "twitter_fr.txt").write_text(twitter_fr, encoding="utf-8")
    thumbnail_prompt = news_items[0].get("image_prompt_en", "") if news_items else ""
    (share_dir / "thumbnail_prompt_news.txt").write_text(thumbnail_prompt, encoding="utf-8")

    return edition_dir


def _history_payload() -> dict[str, Any]:
    history_file = Path(__file__).resolve().parents[3] / "data" / "published_news.json"
    if not history_file.exists():
        payload = {
            "editions": [],
            "seen_signatures": [],
        }
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    try:
        return json.loads(history_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {
            "editions": [],
            "seen_signatures": [],
        }
        history_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


def _resolve_edition_context() -> tuple[int, str]:
    raw_number = os.getenv("MARKET_MATCH_EDITION_NUMBER", "").strip()
    raw_date = os.getenv("MARKET_MATCH_EDITION_DATE", "").strip()

    try:
        edition_number = int(raw_number)
    except (TypeError, ValueError):
        payload = _history_payload()
        editions = payload.get("editions", [])
        latest = max((int(item.get("edition_number", 0)) for item in editions), default=0)
        edition_number = latest + 1

    edition_date = raw_date or datetime.now().date().isoformat()
    return edition_number, edition_date


def _selected_news_items(result: Any) -> list[dict[str, str]]:
    if hasattr(result, "pydantic") and getattr(result, "pydantic") is not None:
        source_payload = result.pydantic
    else:
        source_payload = result

    if isinstance(source_payload, dict):
        news_items = source_payload.get("news", [])
    else:
        news_items = getattr(source_payload, "news", [])

    normalized: list[dict[str, str]] = []
    for item in news_items:
        if isinstance(item, dict):
            title = str(item.get("title", "")).strip()
            source = str(item.get("original_url") or item.get("url") or "").strip()
            summary = str(item.get("article_content", "")).strip()
        else:
            title = str(getattr(item, "title", "")).strip()
            source = str(getattr(item, "original_url", "") or getattr(item, "url", "")).strip()
            summary = str(getattr(item, "article_content", "")).strip()

        if not title:
            continue
        normalized.append({"title": title, "summary": summary, "source": source})

    return normalized


def save_selected_news(result: Any) -> str:
    from market_match.tools.news_history_tools import SavePublishedEditionTool

    edition_number, edition_date = _resolve_edition_context()
    items = _selected_news_items(result)
    
    # Save the actual count of selected news to environment for writing tasks
    actual_news_count = len(items)
    os.environ["MARKET_MATCH_ACTUAL_NEWS_COUNT"] = str(actual_news_count)
    
    return SavePublishedEditionTool().run(
        edition_number=edition_number,
        edition_date=edition_date,
        items=items,
    )


def create_share_bundle_for_edition(edition_number: int, edition_date: str) -> str:
    """Create share directory and copy selected edition files if they exist.

    Missing files are ignored by design.
    """
    project_root = Path(__file__).resolve().parents[3]
    edition_dir = project_root / "editions" / f"edition_{edition_number}_{edition_date}"
    share_dir = edition_dir / "share"
    share_dir.mkdir(parents=True, exist_ok=True)

    file_names = [
        "newsletter_fr.html",
        "newsletter_en.html",
        "newsletter_title_fr.txt",
        "newsletter_title_en.txt",
        "image_prompt_news_1.txt",
        "social_linkedin.txt",
        "social_twitter.txt",
        "social_facebook.txt",
    ]

    copied = 0
    missing = 0

    for file_name in file_names:
        src = edition_dir / file_name
        dst = share_dir / file_name
        if not src.exists() or not src.is_file():
            missing += 1
            continue
        shutil.copy2(src, dst)
        copied += 1

    return (
        f"Share bundle ready in {share_dir.as_posix()} "
        f"(copied={copied}, missing={missing})."
    )


def create_share_bundle_callback(_: Any) -> str:
    """CrewAI callback to materialize share assets after social post generation."""
    raw_number = os.getenv("MARKET_MATCH_EDITION_NUMBER", "").strip()
    edition_date = os.getenv("MARKET_MATCH_EDITION_DATE", "").strip()

    if not raw_number or not edition_date:
        return "Skipped share bundle callback: missing MARKET_MATCH_EDITION_NUMBER or MARKET_MATCH_EDITION_DATE."

    try:
        edition_number = int(raw_number)
    except ValueError:
        return f"Skipped share bundle callback: invalid MARKET_MATCH_EDITION_NUMBER={raw_number}."

    return create_share_bundle_for_edition(edition_number=edition_number, edition_date=edition_date)