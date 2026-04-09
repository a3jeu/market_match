"""Research paper search tools for academic sources.

Covers arXiv and Semantic Scholar, focused on AI applied to
sports, finance, and economics.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


class ArxivSearchToolSchema(BaseModel):
    """Input for ArxivSearchTool."""

    query: str = Field(
        ...,
        description=(
            "Search query for arXiv. Use keywords relevant to AI in sports, finance, "
            "or economics."
        ),
    )
    max_results: int = Field(
        default=8,
        description="Maximum number of results to return (1-20). Default is 8.",
    )


class ArxivSearchTool(BaseTool):
    """Search arXiv for recent academic papers.

    Queries the public arXiv Atom API — no API key required.
    Focuses on cs.AI, cs.LG, q-fin, stat, and econ categories.
    """

    name: str = "Search arXiv for research papers"
    description: str = (
        "Search arXiv for recent academic papers and preprints related to "
        "AI in sports, finance, or economics. "
        "Returns paper title, authors, abstract, publication date, and URL. "
        "Use specific keyword queries to get relevant results."
    )
    args_schema: type[BaseModel] = ArxivSearchToolSchema

    def _run(self, query: str, max_results: int = 8, **kwargs: Any) -> str:
        max_results = max(1, min(max_results, 20))

        # Build a proper arXiv query: join tokens with AND using abs: field prefix
        # so each word must appear in title or abstract.
        tokens = [t.strip() for t in query.split() if t.strip()]
        if len(tokens) == 1:
            search_query = f"abs:{tokens[0]}"
        else:
            search_query = " AND ".join(f"abs:{t}" for t in tokens)

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = requests.get(ARXIV_API_URL, params=params, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            return f"arXiv API error: {exc}"

        return self._parse_response(response.text)

    def _parse_response(self, xml_text: str) -> str:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            return f"Failed to parse arXiv response: {exc}"

        entries = root.findall(f"{{{ARXIV_NS_ATOM}}}entry")
        # fallback: try without namespace prefix
        if not entries:
            entries = root.findall(f"{{{ARXIV_ATOM_NS}}}entry")
        if not entries:
            # bare tag
            entries = root.findall("entry")

        if not entries:
            return "No results found on arXiv for this query."

        results: list[str] = []
        for entry in entries:
            title = _et_text(entry, "title", ARXIV_ATOM_NS) or "No title"
            summary = _et_text(entry, "summary", ARXIV_ATOM_NS) or "No abstract"
            published = _et_text(entry, "published", ARXIV_ATOM_NS) or "Unknown date"

            # arXiv ID link (abstract page)
            paper_url = ""
            for link in entry.findall(f"{{{ARXIV_ATOM_NS}}}link"):
                href = link.get("href", "")
                rel = link.get("rel", "")
                if rel == "alternate" or "abs" in href:
                    paper_url = href
                    break
            if not paper_url:
                id_el = entry.find(f"{{{ARXIV_ATOM_NS}}}id")
                paper_url = id_el.text.strip() if id_el is not None and id_el.text else ""

            authors: list[str] = []
            for author_el in entry.findall(f"{{{ARXIV_ATOM_NS}}}author"):
                name_el = author_el.find(f"{{{ARXIV_ATOM_NS}}}name")
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())

            # Truncate summary to ~400 chars
            summary = summary.strip().replace("\n", " ")
            if len(summary) > 400:
                summary = summary[:400].rstrip() + "..."

            block = (
                f"Title: {title.strip()}\n"
                f"Authors: {', '.join(authors[:3]) or 'Unknown'}\n"
                f"Published: {published[:10]}\n"
                f"URL: {paper_url}\n"
                f"Abstract: {summary}\n"
            )
            results.append(block)

        return "\n---\n".join(results)


def _et_text(element: ET.Element, tag: str, ns: str) -> str | None:
    el = element.find(f"{{{ns}}}{tag}")
    if el is not None and el.text:
        return el.text.strip()
    # fallback without namespace
    el = element.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return None


# Fix: define both namespace aliases
ARXIV_NS_ATOM = ARXIV_ATOM_NS


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,abstract,year,authors,url,externalIds,publicationDate"


class SemanticScholarSearchToolSchema(BaseModel):
    """Input for SemanticScholarSearchTool."""

    query: str = Field(
        ...,
        description=(
            "Keywords to search for in Semantic Scholar. Focus on AI applied to "
            "sports, finance, or economics. Example: 'machine learning financial forecasting' "
            "or 'computer vision sports performance'."
        ),
    )
    max_results: int = Field(
        default=8,
        description="Maximum number of results to return (1–20). Default is 8.",
    )


class SemanticScholarSearchTool(BaseTool):
    """Search Semantic Scholar for academic papers.

    Uses the public Semantic Scholar Graph API — no API key required, but
    rate-limited to ~1 request/second. Automatically retries once on HTTP 429.
    """

    name: str = "Search Semantic Scholar for research papers"
    description: str = (
        "Search Semantic Scholar for peer-reviewed papers related to "
        "AI in sports, finance, or economics. "
        "Returns paper title, authors, abstract, publication year, and URL. "
        "Useful for finding cited, peer-reviewed work across all academic fields."
    )
    args_schema: type[BaseModel] = SemanticScholarSearchToolSchema
    semantic_scholar_api_key: str = Field(default="")

    def _run(self, query: str, max_results: int = 8, **kwargs: Any) -> str:
        max_results = max(1, min(max_results, 20))
        params: dict[str, Any] = {
            "query": query,
            "fields": SEMANTIC_SCHOLAR_FIELDS,
            "limit": max_results,
        }
        headers: dict[str, str] = {}
        if self.semantic_scholar_api_key:
            headers["x-api-key"] = self.semantic_scholar_api_key

        try:
            response = self._get_with_retry(params, headers)
        except requests.RequestException as exc:
            return f"Semantic Scholar API error: {exc}"

        if response.status_code == 429:
            return (
                "Semantic Scholar rate limit reached. "
                "Try again in a few seconds or use arXiv search instead."
            )
        if response.status_code != 200:
            return f"Semantic Scholar returned HTTP {response.status_code}: {response.text[:200]}"

        return self._parse_response(response.json())

    def _get_with_retry(
        self, params: dict, headers: dict, retries: int = 2
    ) -> requests.Response:
        for attempt in range(retries):
            response = requests.get(
                SEMANTIC_SCHOLAR_API_URL, params=params, headers=headers, timeout=20
            )
            if response.status_code != 429:
                return response
            # Back off before retry
            time.sleep(3 * (attempt + 1))
        return response  # return last response even if still 429

    def _parse_response(self, data: dict) -> str:
        papers = data.get("data", [])
        if not papers:
            return "No results found on Semantic Scholar for this query."

        results: list[str] = []
        for paper in papers:
            title = paper.get("title") or "No title"
            year = paper.get("year") or paper.get("publicationDate", "")[:4] or "Unknown"
            abstract = (paper.get("abstract") or "No abstract available").replace("\n", " ")
            if len(abstract) > 400:
                abstract = abstract[:400].rstrip() + "..."

            url = paper.get("url") or ""
            if not url:
                ext_ids = paper.get("externalIds") or {}
                doi = ext_ids.get("DOI", "")
                arxiv_id = ext_ids.get("ArXiv", "")
                if arxiv_id:
                    url = f"https://arxiv.org/abs/{arxiv_id}"
                elif doi:
                    url = f"https://doi.org/{doi}"

            authors = [a.get("name", "") for a in (paper.get("authors") or [])[:3]]

            block = (
                f"Title: {title}\n"
                f"Authors: {', '.join(authors) or 'Unknown'}\n"
                f"Year: {year}\n"
                f"URL: {url}\n"
                f"Abstract: {abstract}\n"
            )
            results.append(block)

        return "\n---\n".join(results)
