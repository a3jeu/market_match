"""Wrapper tools around third-party CrewAI tools with safer defaults."""

from __future__ import annotations

import re
from typing import Any

from crewai.tools import BaseTool
from crewai_tools import ScrapeWebsiteTool, SerperDevTool
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field
import requests


class LimitedScrapeWebsiteToolSchema(BaseModel):
    """Input for LimitedScrapeWebsiteTool."""

    website_url: str = Field(..., description="Mandatory website url to scrape")


class LimitedScrapeWebsiteTool(BaseTool):
    """Cap scraped website output to avoid oversized prompts."""

    name: str = "Read website content (limited)"
    description: str = (
        "A wrapper around ScrapeWebsiteTool that truncates scraped content to "
        "a maximum number of characters before returning it."
    )
    args_schema: type[BaseModel] = LimitedScrapeWebsiteToolSchema
    max_chars: int = 50_000
    scrape_tool: ScrapeWebsiteTool = Field(default_factory=ScrapeWebsiteTool)

    def _run(self, website_url: str, **kwargs: Any) -> str:
        result = self.scrape_tool._run(website_url=website_url, **kwargs)
        content = str(result)

        if len(content) <= self.max_chars:
            return content

        return content[: self.max_chars]


class PlaywrightScrapeWebsiteToolSchema(BaseModel):
    """Input for PlaywrightScrapeWebsiteTool."""

    website_url: str = Field(..., description="Mandatory website url to scrape")


class PlaywrightScrapeWebsiteTool(BaseTool):
    """Read website content with a real browser for JS-heavy pages.

    Uses Playwright Chromium to render and extract visible text, then falls back
    to classic scraping and finally to r.jina.ai mirror when needed.
    """

    name: str = "Read website content with Playwright"
    description: str = (
        "Read website content using Playwright (Chromium) for JavaScript-heavy pages "
        "or anti-bot interstitials. Automatically falls back to basic scraping when needed."
    )
    args_schema: type[BaseModel] = PlaywrightScrapeWebsiteToolSchema
    max_chars: int = 50_000
    goto_timeout_ms: int = 45_000
    scrape_tool: ScrapeWebsiteTool = Field(default_factory=ScrapeWebsiteTool)

    def _run(self, website_url: str, **kwargs: Any) -> str:
        playwright_content = self._read_with_playwright(website_url)
        if self._is_good_content(playwright_content):
            return self._trim(playwright_content)

        classic_content = self._read_with_classic_scraper(website_url, **kwargs)
        if self._is_good_content(classic_content):
            return self._trim(classic_content)

        mirror_content = self._read_with_jina_mirror(website_url)
        if self._is_good_content(mirror_content):
            return self._trim(mirror_content)

        combined = (
            "Unable to extract meaningful page content. "
            "Possible causes: paywall, anti-bot protection, or dynamic rendering restrictions.\n\n"
            "Playwright attempt:\n"
            f"{self._trim(playwright_content)}\n\n"
            "Classic scraper attempt:\n"
            f"{self._trim(classic_content)}\n\n"
            "Mirror attempt:\n"
            f"{self._trim(mirror_content)}"
        )
        return self._trim(combined)

    def _read_with_playwright(self, website_url: str) -> str:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 2200},
                )
                page = context.new_page()

                page.goto(website_url, wait_until="domcontentloaded", timeout=self.goto_timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except PlaywrightTimeoutError:
                    # Some websites keep long-polling connections alive forever.
                    pass

                text = page.evaluate(
                    """
                    () => {
                      const clone = document.body ? document.body.cloneNode(true) : null;
                      if (!clone) return '';

                      const selectors = [
                        'script', 'style', 'noscript', 'svg', 'canvas',
                        'header', 'footer', 'nav', 'aside',
                        '[aria-hidden="true"]', '.sr-only'
                      ];
                      for (const selector of selectors) {
                        clone.querySelectorAll(selector).forEach(el => el.remove());
                      }

                      const articleCandidate =
                        clone.querySelector('article') ||
                        clone.querySelector('main') ||
                        clone;

                      return (articleCandidate.innerText || '').trim();
                    }
                    """
                )

                html = page.content()
                context.close()
                browser.close()

            text = str(text or "").strip()
            if text:
                return text

            # Fallback to html text extraction if innerText is empty.
            html_text = re.sub(r"<[^>]+>", " ", html)
            html_text = re.sub(r"\s+", " ", html_text).strip()
            return html_text
        except Exception as exc:
            return f"Playwright extraction error: {exc}"

    def _read_with_classic_scraper(self, website_url: str, **kwargs: Any) -> str:
        try:
            result = self.scrape_tool._run(website_url=website_url, **kwargs)
            return str(result)
        except Exception as exc:
            return f"Classic scraper error: {exc}"

    def _read_with_jina_mirror(self, website_url: str) -> str:
        try:
            mirror_url = f"https://r.jina.ai/http://{website_url.replace('https://', '').replace('http://', '')}"
            response = requests.get(mirror_url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            return f"Mirror extraction error: {exc}"

    def _trim(self, content: str) -> str:
        normalized = re.sub(r"\s+", " ", str(content or "")).strip()
        if len(normalized) <= self.max_chars:
            return normalized
        return normalized[: self.max_chars]

    def _is_good_content(self, content: str) -> bool:
        if not content:
            return False

        lowered = content.lower()
        blocked_markers = [
            "enable javascript and cookies to continue",
            "just a moment",
            "attention required",
            "access denied",
            "verify you are human",
            "captcha",
            "bot detection",
            "playwright extraction error",
            "classic scraper error",
        ]
        if any(marker in lowered for marker in blocked_markers):
            return False

        # Require a minimum amount of non-trivial text.
        return len(content.strip()) > 300


class NewsOnlySerperDevToolSchema(BaseModel):
    """Input for NewsOnlySerperDevTool."""

    search_query: str = Field(
        ..., description="Mandatory search query you want to use to search news"
    )


class NewsOnlySerperDevTool(BaseTool):
    """Force Serper requests to use the news endpoint."""

    name: str = "Search the internet with Serper (news only)"
    description: str = (
        "A wrapper around SerperDevTool that always enforces search_type='news'."
    )
    args_schema: type[BaseModel] = NewsOnlySerperDevToolSchema
    serper_tool: SerperDevTool = Field(default_factory=SerperDevTool)

    def _run(self, search_query: str, **kwargs: Any) -> Any:
        forwarded_kwargs = dict(kwargs)
        forwarded_kwargs.pop("search_type", None)
        return self.serper_tool._run(
            search_query=search_query,
            search_type="news",
            **forwarded_kwargs,
        )
