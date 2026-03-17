from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, List, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _data_dir() -> Path:
    directory = _project_root() / "data"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _history_file() -> Path:
    return _data_dir() / "published_news.json"


def _history_payload() -> dict[str, Any]:
    file_path = _history_file()
    if not file_path.exists():
        payload = {
            "editions": [],
            "seen_signatures": [],
        }
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {
            "editions": [],
            "seen_signatures": [],
        }
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


def _build_signature(title: str, url: str = "") -> str:
    normalized = f"{title.strip().lower()}|{url.strip().lower()}"
    return sha256(normalized.encode("utf-8")).hexdigest()


class ReadPublishedNewsInput(BaseModel):
    max_items: int = Field(
        default=120,
        description="Maximum number of the most recent news signatures/titles to return.",
    )


class ReadPublishedNewsTool(BaseTool):
    name: str = "read_published_news_history"
    description: str = (
        "Read previously published newsletter items to avoid repeating the same news across editions."
    )
    args_schema: Type[BaseModel] = ReadPublishedNewsInput

    def _run(self, max_items: int = 120) -> str:
        payload = _history_payload()
        editions = payload.get("editions", [])
        seen = payload.get("seen_signatures", [])

        flattened_items: list[dict[str, Any]] = []
        for edition in editions[-max_items:]:
            for item in edition.get("items", []):
                flattened_items.append(
                    {
                        "edition": edition.get("edition_number"),
                        "date": edition.get("edition_date"),
                        "title": item.get("title", ""),
                        "summary": item.get("summary", ""),
                        "source": item.get("source", ""),
                        "signature": item.get("signature", ""),
                    }
                )

        result = {
            "recent_items": flattened_items[-max_items:],
            "seen_signatures": seen,
            "guidance": "Do not reuse or paraphrase the same core event if title/source strongly overlaps with an existing signature.",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


class NewsHistoryEntry(BaseModel):
    title: str = Field(..., description="The headline of the article.")
    summary: str = Field(default="", description="A 1-3 sentence summary of the article.")
    source: str = Field(default="", description="The URL of the source article.")


class SavePublishedEditionInput(BaseModel):
    edition_number: int = Field(..., description="Edition number, e.g. 12")
    edition_date: str = Field(..., description="Edition date in YYYY-MM-DD format")
    items: List[NewsHistoryEntry] = Field(
        ...,
        description="List of news items to persist. Each item must have a title, and optionally a summary and a source URL.",
    )


class SavePublishedEditionTool(BaseTool):
    name: str = "save_published_edition_history"
    description: str = (
        "Persist newsletter edition metadata and news signatures after publication so future editions can avoid duplicates."
    )
    args_schema: Type[BaseModel] = SavePublishedEditionInput

    def _run(self, edition_number: int, edition_date: str, items: List[NewsHistoryEntry]) -> str:
        payload = _history_payload()

        # Accept plain dicts when called from Python code (not via an LLM)
        validated: list[NewsHistoryEntry] = [
            item if isinstance(item, NewsHistoryEntry) else NewsHistoryEntry.model_validate(item)
            for item in items
        ]

        normalized_items: list[dict[str, str]] = []
        signatures_to_add: set[str] = set()
        for item in validated:
            title = item.title.strip()
            summary = item.summary.strip()
            source = item.source.strip()
            if not title:
                continue
            signature = _build_signature(title=title, url=source)
            signatures_to_add.add(signature)
            normalized_items.append(
                {
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "signature": signature,
                }
            )

        payload.setdefault("editions", [])
        payload.setdefault("seen_signatures", [])

        payload["editions"].append(
            {
                "edition_number": edition_number,
                "edition_date": edition_date,
                "items": normalized_items,
            }
        )

        existing_signatures = set(payload["seen_signatures"])
        payload["seen_signatures"] = sorted(existing_signatures.union(signatures_to_add))

        _history_file().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return (
            f"Saved edition {edition_number} ({edition_date}) with "
            f"{len(normalized_items)} items in {_history_file().as_posix()}."
        )
