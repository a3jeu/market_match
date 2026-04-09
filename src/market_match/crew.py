from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple

from rich.console import Console
from rich.panel import Panel

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai.tasks.task_output import TaskOutput
from crewai_tools import ScrapeWebsiteTool, SerperDevTool

from market_match.models import (
    EnrichedNewsItem,
    EnrichedNewsList,
    EnrichedNewsListResearch,
    NewsletterIntroduction,
    NewsArticleIntro,
    NewsArticleTitle,
    NewsArticleVerdict,
    RecentNewsList,
    WrittenNewsArticle,
)
from market_match.tools import (
    ArxivSearchTool,
    AssembleNewsletterHtmlTool,
    LimitedScrapeWebsiteTool,
    NewsAPISearchTool,
    NewsOnlySerperDevTool,
    PlaywrightScrapeWebsiteTool,
    ReadPublishedNewsTool,
    SavePublishedEditionTool,
    SemanticScholarSearchTool,
)
from market_match.utils.utils import extract_json, format_template, safe_slug
from market_match.utils.editions import (
    create_share_bundle_callback,
    export_edition,
    next_edition_number,
    save_selected_news,
)


def _single_json_object_guardrail(task_output: TaskOutput):
    """Normalize task output to exactly one JSON object string.

    CrewAI can receive model outputs with extra trailing text around JSON.
    This guardrail extracts the JSON object and returns it as canonical JSON.
    """
    try:
        parsed = extract_json(task_output.raw)
    except Exception as exc:
        return False, f"Invalid JSON output: {exc}"

    return True, json.dumps(parsed, ensure_ascii=False)


def _compact_text(value: Any, max_len: int) -> str:
    """Normalize and cap text fields to avoid context blowups in downstream tasks."""
    text = str(value or "")

    # Drop control chars and collapse whitespace while preserving readability.
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    # If the payload looks binary/garbled, keep only a short safe prefix.
    sample = text[:2000]
    non_word = sum(1 for ch in sample if not (ch.isalnum() or ch.isspace() or ch in ",.;:!?()[]{}'\"/-_@#%&*+="))
    if sample and (non_word / len(sample)) > 0.35:
        text = "[content omitted: non-text payload detected]"

    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."

    return text


def _compact_enriched_news_item_payload(payload: dict[str, Any]) -> dict[str, Any]:
    news_item = dict(payload)

    news_item["title"] = _compact_text(news_item.get("title", ""), 220)
    news_item["topic"] = _compact_text(news_item.get("topic", ""), 40)
    news_item["url"] = _compact_text(news_item.get("url", ""), 500)
    news_item["article_content"] = _compact_text(news_item.get("article_content", ""), 1800)

    compact_sources: list[dict[str, Any]] = []
    for src in news_item.get("additional_sources", []) or []:
        if not isinstance(src, dict):
            continue
        compact_sources.append(
            {
                "title": _compact_text(src.get("title", ""), 220),
                "source": _compact_text(src.get("source", ""), 120),
                "url": _compact_text(src.get("url", ""), 500),
                "published_at": _compact_text(src.get("published_at", ""), 32),
                "article_content": _compact_text(src.get("article_content", ""), 900),
                "added_value_for_writer": _compact_text(src.get("added_value_for_writer", ""), 500),
            }
        )
    news_item["additional_sources"] = compact_sources

    market_context = news_item.get("market_context_source")
    if isinstance(market_context, dict):
        news_item["market_context_source"] = {
            "title": _compact_text(market_context.get("title", ""), 220),
            "source": _compact_text(market_context.get("source", ""), 120),
            "url": _compact_text(market_context.get("url", ""), 500),
            "published_at": _compact_text(market_context.get("published_at", ""), 32),
            "article_content": _compact_text(market_context.get("article_content", ""), 900),
            "added_value_for_writer": _compact_text(market_context.get("added_value_for_writer", ""), 500),
        }

    return news_item


def _compact_enriched_news_item_guardrail(task_output: TaskOutput):
    """Compact the extracted EnrichedNewsItem to keep writing-task context bounded."""
    try:
        parsed = extract_json(task_output.raw)
    except Exception as exc:
        return False, f"Invalid JSON output: {exc}"

    compact = _compact_enriched_news_item_payload(parsed)
    return True, json.dumps(compact, ensure_ascii=False)


@dataclass
class WritingArticleTasks:
    extractor: Task | None = None
    article: Task | None = None
    title: Task | None = None
    intro: Task | None = None
    verdict: Task | None = None

    def all_tasks(self) -> List[Task]:
        return [
            task
            for task in [self.extractor, self.article, self.title, self.intro, self.verdict]
            if task is not None
        ]


@dataclass
class WritingTaskGroups:
    extractors: List[Task] = field(default_factory=list)
    articles: List[Task] = field(default_factory=list)
    titles: List[Task] = field(default_factory=list)
    intros: List[Task] = field(default_factory=list)
    verdicts: List[Task] = field(default_factory=list)
    newsletter_intro: Task | None = None

    def all_tasks(self) -> List[Task]:
        tasks = [
            *self.extractors,
            *self.articles,
            *self.titles,
            *self.intros,
            *self.verdicts,
        ]
        if self.newsletter_intro is not None:
            tasks.append(self.newsletter_intro)
        return tasks

    def marketing_context(self) -> List[Task]:
        context = [*self.articles, *self.titles, *self.intros, *self.verdicts]
        if self.newsletter_intro is not None:
            context.append(self.newsletter_intro)
        return context

    def article_count(self) -> int:
        return max(
            len(self.extractors),
            len(self.articles),
            len(self.titles),
            len(self.intros),
            len(self.verdicts),
        )

    def for_article(self, article_no: int) -> WritingArticleTasks:
        if article_no < 1:
            raise ValueError("article_no must be >= 1")

        index = article_no - 1
        return WritingArticleTasks(
            extractor=self.extractors[index] if index < len(self.extractors) else None,
            article=self.articles[index] if index < len(self.articles) else None,
            title=self.titles[index] if index < len(self.titles) else None,
            intro=self.intros[index] if index < len(self.intros) else None,
            verdict=self.verdicts[index] if index < len(self.verdicts) else None,
        )


@dataclass
class MarketingTaskGroups:
    image_prompts: List[Task] = field(default_factory=list)
    newsletter_title: Task | None = None
    validated_html: Task | None = None
    translated_title: Task | None = None
    translated_html: Task | None = None
    facebook_post: Task | None = None
    linkedin_post: Task | None = None
    twitter_post: Task | None = None

    def all_tasks(self) -> List[Task]:
        return [
            task
            for task in [
                *self.image_prompts,
                self.newsletter_title,
                self.validated_html,
                self.translated_title,
                self.translated_html,
                self.facebook_post,
                self.linkedin_post,
                self.twitter_post,
            ]
            if task is not None
        ]

@CrewBase
class MarketMatch:
    """MarketMatch crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    ##############################################
    # --------- RESEARCH DEPARTMENT --------------
    ##############################################
    @agent
    def ai_sports_news_scout(self) -> Agent:
        return Agent(
            config=self.agents_config["ai_sports_news_scout"], 
            tools=[NewsOnlySerperDevTool(), NewsAPISearchTool(), ReadPublishedNewsTool(), PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool()],
            verbose=True,
        )
        
    @agent
    def ai_finance_news_scout(self) -> Agent:
        return Agent(
            config=self.agents_config["ai_finance_news_scout"], 
            tools=[NewsOnlySerperDevTool(), NewsAPISearchTool(), ReadPublishedNewsTool(), PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool()],
            verbose=True,
        )
        
    @agent
    def ai_economy_news_scout(self) -> Agent:
        return Agent(
            config=self.agents_config["ai_economy_news_scout"], 
            tools=[NewsOnlySerperDevTool(), NewsAPISearchTool(), ReadPublishedNewsTool(), PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool()],
            verbose=True,
        )

    @agent
    def ai_research_paper_scout(self) -> Agent:
        return Agent(
            config=self.agents_config["ai_research_paper_scout"],
            tools=[
                ArxivSearchTool(), 
                # SemanticScholarSearchTool(), # No API Key yet
                SerperDevTool(),
                ReadPublishedNewsTool(), 
                PlaywrightScrapeWebsiteTool(),
                LimitedScrapeWebsiteTool()
            ],
            verbose=True,
        )

    @agent
    def news_enricher(self) -> Agent:
        return Agent(
            config=self.agents_config["news_enricher"],
            tools=[NewsOnlySerperDevTool(), PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool()],
            verbose=True,
        )

    @agent
    def market_context_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["market_context_researcher"],
            tools=[NewsOnlySerperDevTool(), PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool()],
            verbose=True,
        )
        
    @agent
    def news_selector(self) -> Agent:
        return Agent(
            config=self.agents_config["news_selector"],
            tools=[PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool(), SavePublishedEditionTool(), ReadPublishedNewsTool()],
            verbose=True,
        )

    @task
    def find_ai_sports_news(self) -> Task:
        return Task(
            config=self.tasks_config["find_ai_sports_news"],
            # output_pydantic=RecentNewsList,
            async_execution=False,
        )
        
    @task
    def find_ai_finance_news(self) -> Task:
        return Task(
            config=self.tasks_config["find_ai_finance_news"],
            # output_pydantic=RecentNewsList,
            async_execution=False,
        )
        
    @task
    def find_ai_economy_news(self) -> Task:
        return Task(
            config=self.tasks_config["find_ai_economy_news"],
            # output_pydantic=RecentNewsList,
            async_execution=False,
        )

    @task
    def find_ai_research_papers(self) -> Task:
        return Task(
            config=self.tasks_config["find_ai_research_papers"],
            async_execution=False,
        )

    @task
    def enrich_news_research(self) -> Task:
        return Task(
            config=self.tasks_config["enrich_news_research"],
            # output_pydantic=EnrichedNewsListResearch,
            # guardrail=_single_json_object_guardrail,
            async_execution=False,
        )

    @task
    def enrich_news_market_context(self) -> Task:
        return Task(
            config=self.tasks_config["enrich_news_market_context"],
            # output_pydantic=EnrichedNewsList,
            # guardrail=_single_json_object_guardrail,
            async_execution=False,
        )
        
    @task
    def select_best_news(self) -> Task:
        return Task(
            config=self.tasks_config["select_best_news"],
            output_pydantic=EnrichedNewsList,
            guardrail=_single_json_object_guardrail,
            async_execution=False,
            callback=save_selected_news,
        )
        
    ##############################################
    # ---------- WRITING DEPARTMENT --------------
    ##############################################
    
    @agent
    def news_item_extractor(self) -> Agent:
        return Agent(
            config=self.agents_config["news_item_extractor"],
            verbose=True,
        )

    @agent
    def article_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["article_writer"],
            tools=[PlaywrightScrapeWebsiteTool(), LimitedScrapeWebsiteTool()],
            verbose=True,
        )

    @agent
    def intro_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["intro_writer"],
            verbose=True,
        )

    @agent
    def title_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["title_writer"],
            verbose=True,
        )

    @agent
    def verdict_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["verdict_writer"],
            verbose=True,
        )
        
    @agent
    def newsletter_intro_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["newsletter_intro_writer"],
            verbose=True,
        )


    def _build_writing_tasks(self) -> WritingTaskGroups:
        """Build writing tasks for each news article.
        
        For each article, create three tasks:
        0. extract_news_item: Extract the single news item to work on
        1. write_news_article_content: Write the article with structured sections
        2.1. write_news_title: Write a concise article title
        2.2. write_news_intro: Write a single-sentence introduction
        2.3. write_news_verdict: Write editorial opinion
        """

        # Get the actual number of news articles from environment
        news_count = int(
            os.environ.get("MARKET_MATCH_ACTUAL_NEWS_COUNT", # src\market_match\utils\editions.py
            os.environ.get("MARKET_MATCH_NEWS_TO_KEEP", "3"))     # main.py
        )

        task_groups = WritingTaskGroups()

        for news_no in range(1, news_count + 1):
            # Task 0: Extract only this item from the selected list
            extract_news_item = Task(
                config=self.tasks_config["extract_news_item"],
                agent=self.news_item_extractor(),
                async_execution=False,
                description=self.tasks_config["extract_news_item"]["description"].format(
                    news_no=news_no
                ),
                expected_output=self.tasks_config["extract_news_item"]["expected_output"].format(
                    news_no=news_no
                ),
                output_file=self.tasks_config["extract_news_item"]["output_file"].replace(
                    "{news_no}", str(news_no)
                ),
                # output_pydantic=EnrichedNewsItem,
                # guardrail=_compact_enriched_news_item_guardrail,
                context=[self.select_best_news()],
            )
            task_groups.extractors.append(extract_news_item)

            # Task 1: Write article content — receives only the single extracted item
            write_news_article_content = Task(
                config=self.tasks_config["write_news_article_content"],
                agent=self.article_writer(),
                async_execution=False,
                expected_output=self.tasks_config["write_news_article_content"]["expected_output"].format(
                    news_no=news_no
                ),
                output_file=self.tasks_config["write_news_article_content"]["output_file"].replace(
                    "{news_no}", str(news_no)
                ),
                output_pydantic=WrittenNewsArticle,
                context=[extract_news_item],
            )
            task_groups.articles.append(write_news_article_content)

            # Task 2.1: Write title
            write_news_title = Task(
                config=self.tasks_config["write_news_title"],
                agent=self.title_writer(),
                async_execution=False,
                expected_output=self.tasks_config["write_news_title"]["expected_output"].format(
                    news_no=news_no
                ),
                output_file=self.tasks_config["write_news_title"]["output_file"].replace(
                    "{news_no}", str(news_no)
                ),
                # output_pydantic=NewsArticleTitle,
                context=[write_news_article_content],
            )
            task_groups.titles.append(write_news_title)

            # Task 2.2: Write introduction
            write_news_intro = Task(
                config=self.tasks_config["write_news_intro"],
                agent=self.intro_writer(),
                async_execution=False,
                expected_output=self.tasks_config["write_news_intro"]["expected_output"].format(
                    news_no=news_no
                ),
                output_file=self.tasks_config["write_news_intro"]["output_file"].replace(
                    "{news_no}", str(news_no)
                ),
                # output_pydantic=NewsArticleIntro,
                context=[write_news_article_content],
            )
            task_groups.intros.append(write_news_intro)

            # Task 2.3: Write verdict
            write_news_verdict = Task(
                config=self.tasks_config["write_news_verdict"],
                agent=self.verdict_writer(),
                async_execution=False,
                expected_output=self.tasks_config["write_news_verdict"]["expected_output"].format(
                    news_no=news_no
                ),
                output_file=self.tasks_config["write_news_verdict"]["output_file"].replace(
                    "{news_no}", str(news_no)
                ),
                # output_pydantic=NewsArticleVerdict,
                context=[write_news_article_content],
            )
            task_groups.verdicts.append(write_news_verdict)

        # Newsletter intro from all written article contents
        write_newsletter_intro = Task(
            config=self.tasks_config["write_newsletter_intro"],
            agent=self.newsletter_intro_writer(),
            async_execution=False,
            output_pydantic=NewsletterIntroduction,
            context=task_groups.articles,
        )
        task_groups.newsletter_intro = write_newsletter_intro

        return task_groups
    
    ##############################################
    # ---------- MARKETING DEPARTMENT ------------
    ##############################################
    
    @agent
    def newsletter_title_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["newsletter_title_writer"],
            verbose=True,
        )
        
    @agent
    def image_prompt_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["image_prompt_writer"],
            verbose=True,
        )

    @agent
    def facebook_post_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["facebook_post_writer"],
            verbose=True,
        )

    @agent
    def linkedin_post_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["linkedin_post_writer"],
            verbose=True,
        )

    @agent
    def twitter_post_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["twitter_post_writer"],
            verbose=True,
        )

    @agent
    def newsletter_html_validator(self) -> Agent:
        return Agent(
            config=self.agents_config["newsletter_html_validator"],
            tools=[AssembleNewsletterHtmlTool()],
            verbose=True,
        )

    @agent
    def newsletter_translator(self) -> Agent:
        return Agent(
            config=self.agents_config["newsletter_translator"],
            verbose=True,
        )

    def _build_marketing_tasks(self, writing_tasks: WritingTaskGroups) -> MarketingTaskGroups:
        """Build marketing tasks from all written article outputs.
        
        For each article, create three tasks:
        1. write_image_prompt: Write an image prompt for the article thumbnail
        
        Then create tasks for the overall newsletter:
        2. write_newsletter_title: Write a concise newsletter title
        3. validate_newsletter_html: Validate the assembled newsletter HTML
        4. translate_newsletter_title: Translate the newsletter title to English
        5. translate_newsletter_html: Translate the newsletter HTML to English
        6. write_facebook_post: Write a Facebook post for the edition
        7. write_linkedin_post: Write a LinkedIn post for the edition
        8. write_twitter_post: Write a Twitter/X post for the edition
        """
        task_groups = MarketingTaskGroups()

        for news_no in range(1, writing_tasks.article_count() + 1):
            article_tasks = writing_tasks.for_article(news_no)
            if article_tasks.article is None:
                print(f"❌ Skipping marketing tasks for article {news_no} because the article content task is missing.")
                continue

            # Task 1: Write image prompt for article thumbnail
            write_image_prompt = Task(
                config=self.tasks_config["write_image_prompt"],
                agent=self.image_prompt_writer(),
                async_execution=False,
                expected_output=self.tasks_config["write_image_prompt"]["expected_output"].format(
                    news_no=news_no
                ),
                output_file=self.tasks_config["write_image_prompt"]["output_file"].replace(
                    "{news_no}", str(news_no)
                ),
                context=[article_tasks.article],
            )
            task_groups.image_prompts.append(write_image_prompt)

        # Task 2: Write newsletter title from all article titles and intros
        write_newsletter_title = Task(
            config=self.tasks_config["write_newsletter_title"],
            agent=self.newsletter_title_writer(),
            async_execution=False,
            context=writing_tasks.marketing_context(),
        )
        task_groups.newsletter_title = write_newsletter_title

        # Task 3: Validate newsletter HTML
        validate_newsletter_html = Task(
            config=self.tasks_config["validate_newsletter_html"],
            agent=self.newsletter_html_validator(),
            async_execution=False,
            context=[write_newsletter_title, *writing_tasks.marketing_context()],
        )
        task_groups.validated_html = validate_newsletter_html

        # Task 4: Translate newsletter title to English
        translate_newsletter_title = Task(
            config=self.tasks_config["translate_newsletter_title"],
            agent=self.newsletter_translator(),
            async_execution=False,
            context=[write_newsletter_title],
        )
        task_groups.translated_title = translate_newsletter_title

        # Task 5: Translate newsletter HTML to English
        translate_newsletter_html = Task(
            config=self.tasks_config["translate_newsletter_html"],
            agent=self.newsletter_translator(),
            async_execution=False,
            context=[validate_newsletter_html],
        )
        task_groups.translated_html = translate_newsletter_html

        # Task 6: Write social media posts for each platform (Facebook)
        write_facebook_post = Task(
            config=self.tasks_config["write_facebook_post"],
            agent=self.facebook_post_writer(),
            async_execution=False,
            context=[write_newsletter_title, validate_newsletter_html],
        )
        task_groups.facebook_post = write_facebook_post

        # Task 7: Write social media posts for each platform (LinkedIn)
        write_linkedin_post = Task(
            config=self.tasks_config["write_linkedin_post"],
            agent=self.linkedin_post_writer(),
            async_execution=False,
            context=[write_newsletter_title, validate_newsletter_html],
        )
        task_groups.linkedin_post = write_linkedin_post

        # Task 8: Write social media posts for each platform (Twitter/X)
        write_twitter_post = Task(
            config=self.tasks_config["write_twitter_post"],
            agent=self.twitter_post_writer(),
            async_execution=False,
            context=[write_newsletter_title, validate_newsletter_html],
            callback=create_share_bundle_callback,
        )
        task_groups.twitter_post = write_twitter_post

        return task_groups
        
        
    # ---------- CREW ------------

    @crew
    def crew(self) -> Crew:
        # RESEARCH DEPARTMENT
        tasks = list(self.tasks)

        # WRITING DEPARTMENT
        writing_tasks = self._build_writing_tasks()
        tasks.extend(writing_tasks.all_tasks())
        
        # MARKETING DEPARTMENT
        marketing_tasks = self._build_marketing_tasks(writing_tasks)
        tasks.extend(marketing_tasks.all_tasks())
        
        return Crew(
            agents=self.agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
            tracing=True
        )