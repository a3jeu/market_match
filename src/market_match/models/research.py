from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class RecentNews(BaseModel):
    """A news found by the scout agent."""

    title: str = Field(description="The headline of the news item.")
    topic: str = Field(description="The topic of the news (sports, finance or economics)")
    url: str = Field(description="The direct URL linking to the news article.")
    published_at: str = Field(description="The publication date (YYYY-MM-DD).")
    source: str = Field(description="The name of the media outlet or organization that published the article.")
    article_content: str = Field(description="A 3-4 sentence summary of the news item.")
    why_relevant: str = Field(
        description="A short explanation of why this news is relevant for AI developments in this topic."
    )


class RecentNewsList(BaseModel):
    """A list of news found by the scout agent."""

    news: List[RecentNews] = Field(
        description="A list of recent news items related to AI in sports, finance, or economics."
    )


class AdditionalSource(BaseModel):
    """An additional source related to an already selected news item."""

    title: str = Field(description="The headline of the additional article.")
    source: str = Field(description="The media outlet or organization that published the additional article.")
    url: str = Field(description="The direct URL linking to the additional article.")
    published_at: str = Field(description="The publication date (YYYY-MM-DD).")
    article_content: str = Field(
        description="A 3-4 sentences summary of the useful content from the additional article."
    )
    # added_value_for_writer: str = Field(
    #     description="What this source adds for the writer compared with the original article."
    # )


class MarketContextSource(BaseModel):
    """A broader market-context source related to an enriched news item."""

    title: str = Field(description="The headline of the market-context article.")
    source: str = Field(description="The media outlet or organization that published the context article.")
    url: str = Field(description="The direct URL linking to the market-context article.")
    published_at: str = Field(description="The publication date (YYYY-MM-DD).")
    article_content: str = Field(
        description="A 3-4 sentences summary focused on market context, competitors, and environment."
    )
    # added_value_for_writer: str = Field(
    #     description="How this source helps write market-positioning and external-environment analysis."
    # )


class EnrichedNewsItemResearch(BaseModel):
    """A selected news item enriched with 1 to 2 additional sources (no market context yet)."""

    title: str = Field(description="The title of the original selected news item.")
    topic: str = Field(description="The topic of the original news item (sports, finance or economics).")
    url: str = Field(description="The URL of the original selected news item.")
    article_content: str = Field(description="A 3-4 sentence summary of the original news item.")
    additional_sources: List[AdditionalSource] = Field(
        default_factory=list,
        description="A list of 1 to 2 additional sources covering the same story with complementary value."
    )
class EnrichedNewsListResearch(BaseModel):
    """A list of news items enriched with additional sources (no market context yet)."""

    news: List[EnrichedNewsItemResearch] = Field(
        description="A list of original news items enriched with additional sources."
    )


class EnrichedNewsItem(BaseModel):
    """A selected news item enriched with additional and market-context sources."""

    title: str = Field(description="The title of the original selected news item.")
    topic: str = Field(description="The topic of the original news item (sports, finance or economics).")
    url: str = Field(description="The URL of the original selected news item.")
    article_content: str = Field(description="A 3-4 sentence summary of the original news item.")
    published_at: str = Field(description="The publication date of the original news item (YYYY-MM-DD).")
    source: str = Field(description="The media outlet or organization that published the original news item.")
    additional_sources: List[AdditionalSource] = Field(
        default_factory=list,
        description="A list of 1 to 2 additional sources covering the same story with complementary value."
    )
    market_context_source: MarketContextSource = Field(
        description=(
            "One additional source that provides broader market context around the story "
            "(competitors, ecosystem, and external environment)."
        ),
    )


class EnrichedNewsList(BaseModel):
    """A list of news items enriched with additional and market-context sources."""

    news: List[EnrichedNewsItem] = Field(
        description="A list of original news items enriched with additional sources."
    )
