"""Wrapper tools around third-party CrewAI tools with safer defaults."""

from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from crewai_tools import ScrapeWebsiteTool, SerperDevTool
from pydantic import BaseModel, Field


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
