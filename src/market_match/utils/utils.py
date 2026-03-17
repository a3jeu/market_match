from __future__ import annotations

import json
import re
from typing import Any


def extract_json(raw_output: str) -> dict[str, Any]:
    """Parse a JSON object from a raw LLM output string, stripping markdown fences if present."""
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        return json.loads(cleaned)

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        raise ValueError("No JSON object found in output.")

    return json.loads(cleaned[first_brace : last_brace + 1])


def extract_body_html(full_html: str) -> str:
    """Return only the content inside <body>...</body>, stripping the outer tags."""
    match = re.search(r"<body[^>]*>(.*?)</body>", full_html, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return full_html


def safe_slug(text: str, fallback: str) -> str:
    """Convert *text* to a URL-friendly slug, falling back to *fallback* if empty."""
    base = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    compact = "-".join(part for part in base.split("-") if part)
    return compact[:70] if compact else fallback


def format_template(template: str, **kwargs: Any) -> str:
    """Replace only known {key} placeholders, leaving any other {...} content untouched.

    Uses a regex that matches {identifier} tokens (valid Python identifiers only),
    so JSON examples like {"key":"value"} in task descriptions are never touched.
    """

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        return str(kwargs[key]) if key in kwargs else match.group(0)

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", _replace, template)
