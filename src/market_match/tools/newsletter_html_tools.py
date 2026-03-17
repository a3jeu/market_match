from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel

from market_match.utils.editions import render_newsletter_html


class AssembleNewsletterHtmlInput(BaseModel):
    pass


class AssembleNewsletterHtmlTool(BaseTool):
    name: str = "assemble_newsletter_html"
    description: str = (
        "Assemble deterministic French newsletter HTML from generated edition artifacts "
        "(title, intro, articles, verdicts, and sources). Returns raw HTML content."
    )
    args_schema: Type[BaseModel] = AssembleNewsletterHtmlInput

    def _run(self) -> str:
        edition_dir = self._edition_dir()

        # title = self._read_text(edition_dir / "newsletter_title_fr.txt")
        intro_payload = self._read_json(edition_dir / "newsletter_intro_fr.json")
        selected_payload = self._read_json(edition_dir / "selected_news.json")

        intro_sentence = str(intro_payload.get("intro_sentence", "")).strip()
        intro_bullets = intro_payload.get("intro_bullets", [])
        if not isinstance(intro_bullets, list):
            intro_bullets = []

        selected_news = selected_payload.get("news", []) if isinstance(selected_payload, dict) else []
        source_map: dict[int, list[dict[str, str]]] = {
            idx: self._build_sources(item)
            for idx, item in enumerate(selected_news, start=1)
        }

        article_files = sorted(edition_dir.glob("news_*_article_fr.json"), key=self._news_file_sort_key)
        if not article_files:
            raise ValueError(f"No article files found in {edition_dir.as_posix()}")

        news_items: list[dict[str, Any]] = []
        for article_file in article_files:
            news_no = self._extract_news_no(article_file.name)
            article_payload = self._read_json(article_file)

            title_fr = self._read_text(edition_dir / f"news_{news_no}_title_fr.txt")
            intro_fr = self._read_text(edition_dir / f"news_{news_no}_intro_fr.txt")
            verdict_fr = self._read_text(edition_dir / f"news_{news_no}_verdict_fr.txt")

            news_items.append(
                {
                    "title_fr": title_fr,
                    "intro_fr": intro_fr,
                    "essentiel_fr": str(article_payload.get("essentials", "")).strip(),
                    "pratique_fr": str(article_payload.get("in_practice", "")).strip(),
                    "decryptage_fr": str(article_payload.get("breakdown", "")).strip(),
                    "enjeu_fr": str(article_payload.get("whats_at_stake", "")).strip(),
                    "verdict_fr": verdict_fr,
                    "sources": source_map.get(news_no, []),
                }
            )

        newsletter_html_fr = render_newsletter_html(
            lang="fr",
            # title=title,
            intro_sentence=intro_sentence,
            intro_bullets=[str(item).strip() for item in intro_bullets if str(item).strip()],
            news_items=news_items,
        )

        return newsletter_html_fr

    @staticmethod
    def _read_text(path: Path) -> str:
        if not path.exists():
            raise ValueError(f"Missing expected file: {path.as_posix()}")
        return path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ValueError(f"Missing expected file: {path.as_posix()}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path.as_posix()}: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object in {path.as_posix()}")
        return payload

    @staticmethod
    def _extract_news_no(filename: str) -> int:
        match = re.match(r"news_(\d+)_article_fr\.json$", filename)
        if not match:
            raise ValueError(f"Unsupported article file naming: {filename}")
        return int(match.group(1))

    @classmethod
    def _news_file_sort_key(cls, path: Path) -> int:
        return cls._extract_news_no(path.name)

    @staticmethod
    def _build_sources(item: dict[str, Any]) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []

        original_url = str(item.get("url") or item.get("original_url") or "").strip()
        original_source = str(item.get("source") or "").strip()
        if original_url:
            sources.append({"label": original_source or "Source principale", "url": original_url})

        additional_sources = item.get("additional_sources", [])
        if isinstance(additional_sources, list):
            for idx, src in enumerate(additional_sources, start=1):
                if not isinstance(src, dict):
                    continue
                src_url = str(src.get("url", "")).strip()
                src_name = str(src.get("source") or src.get("title") or "").strip()
                if src_url:
                    sources.append({"label": src_name or f"Source additionnelle {idx}", "url": src_url})

        market_context_source = item.get("market_context_source")
        if isinstance(market_context_source, dict):
            mcs_url = str(market_context_source.get("url", "")).strip()
            mcs_name = str(
                market_context_source.get("source") or market_context_source.get("title") or ""
            ).strip()
            if mcs_url:
                sources.append({"label": mcs_name or "Contexte de marche", "url": mcs_url})

        dedup: list[dict[str, str]] = []
        seen: set[str] = set()
        for source in sources:
            key = source.get("url", "")
            if not key or key in seen:
                continue
            seen.add(key)
            dedup.append(source)
        return dedup

    @staticmethod
    def _edition_dir() -> Path:
        root = Path(__file__).resolve().parents[3]
        edition_number = os.getenv("MARKET_MATCH_EDITION_NUMBER", "").strip()
        edition_date = os.getenv("MARKET_MATCH_EDITION_DATE", "").strip()

        if not edition_number or not edition_date:
            raise ValueError(
                "MARKET_MATCH_EDITION_NUMBER and MARKET_MATCH_EDITION_DATE must be set "
                "to assemble newsletter HTML."
            )

        try:
            number = int(edition_number)
        except ValueError as exc:
            raise ValueError(f"Invalid MARKET_MATCH_EDITION_NUMBER: {edition_number}") from exc

        edition_dir = root / "editions" / f"edition_{number}_{edition_date}"
        if not edition_dir.exists():
            raise ValueError(f"Edition directory not found: {edition_dir.as_posix()}")
        return edition_dir
