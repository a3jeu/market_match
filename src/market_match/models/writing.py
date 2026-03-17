from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class NewsArticleSection(BaseModel):
    """Sections of a written news article."""

    essentials: str = Field(
        description="1-2 sentence summary of the news."
    )
    in_practice: str = Field(
        description="Short paragraph (3-4 sentences) explaining what the news means in practice."
    )
    breakdown: str = Field(
        description="Short paragraph (3-4 sentences) providing broader market context and positioning."
    )
    whats_at_stake: str = Field(
        description="Short paragraph (3-4 sentences) analyzing concrete impacts, including potential winners and losers."
    )


class WrittenNewsArticle(BaseModel):
    """A complete written news article with all sections."""

    essentials: str = Field(
        description="1-2 sentence summary of the news."
    )
    in_practice: str = Field(
        description="Short paragraph (3-4 sentences) explaining what the news means in practice."
    )
    breakdown: str = Field(
        description="Short paragraph (3-4 sentences) providing broader market context and analysis."
    )
    whats_at_stake: str = Field(
        description="Short paragraph (3-4 sentences) analyzing concrete impacts, including potential winners and losers."
    )


class NewsArticleIntro(BaseModel):
    """A single-sentence introduction for a news article."""

    introduction: str = Field(
        description="One compelling sentence introducing the article."
    )


class NewsArticleTitle(BaseModel):
    """A title for a news article."""

    title: str = Field(
        description="A concise, 5-10 words compelling title for the article."
    )

class NewsArticleVerdict(BaseModel):
    """A 1-2 sentences verdict for a news article."""

    verdict: str = Field(
        description="1-2 sentences providing an editorial opinion on the article."
    )


class NewsArticleComplete(BaseModel):
    """A complete news article with all sections, intro, and verdict."""

    article: WrittenNewsArticle = Field(
        description="The main article with all sections."
    )
    introduction: str = Field(
        description="One compelling sentence introducing the article."
    )
    verdict: str = Field(
        description="Editorial opinion on the news in 1-2 sentences."
    )


class NewsletterTitle(BaseModel):
    """A newsletter title for a list of articles."""

    title: str = Field(
        description="Newsletter title in 5 to 10 words."
    )


class NewsletterIntroduction(BaseModel):
    """A structured newsletter introduction."""

    intro_sentence: str = Field(
        description=(
            "Single sentence starting exactly with: "
            "Dans l'edition d'aujourd'hui de Market & Match,"
        )
    )
    intro_bullets: List[str] = Field(
        description="One short, punchy bullet per news item (5-10 words each)."
    )


class ArticleImagePrompt(BaseModel):
    """Image prompt for one article thumbnail generation."""

    image_prompt_en: str = Field(
        description="English landscape-oriented prompt for image generation."
    )


class SocialPost(BaseModel):
    """French social post content for one platform."""

    post_fr: str = Field(
        description="Final French post text for the target platform."
    )


class NewsletterHtml(BaseModel):
    """Assembled newsletter HTML content."""

    newsletter_html_fr: str = Field(
        description="French newsletter HTML content."
    )


class NewsletterHtmlTranslation(BaseModel):
    """Translated newsletter assets."""

    newsletter_title_en: str = Field(
        description="English translation of newsletter_title_fr."
    )
    newsletter_html_en: str = Field(
        description="English translation of the validated newsletter HTML."
    )
