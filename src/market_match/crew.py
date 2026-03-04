from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List

from rich.console import Console
from rich.panel import Panel

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool

from market_match.tools import ReadPublishedNewsTool, SavePublishedEditionTool
from market_match.utils import extract_body_html, extract_json, format_template, safe_slug


@CrewBase
class MarketMatch:
    """MarketMatch crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    def __init__(self) -> None:
        self.serper_tool = SerperDevTool()
        self.read_history_tool = ReadPublishedNewsTool()
        self.save_history_tool = SavePublishedEditionTool()
        self.project_root = Path(__file__).resolve().parents[2]

        self.research_model = os.getenv("MARKET_MATCH_RESEARCH_MODEL", os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"))
        self.writing_model = os.getenv("MARKET_MATCH_WRITING_MODEL", "gpt-5-mini")

    @agent
    def trend_scout(self) -> Agent:
        return Agent(
            config=self.agents_config["trend_scout"],  # type: ignore[index]
            tools=[self.serper_tool, self.read_history_tool],
            llm=self.research_model,
            verbose=True,
        )

    @agent
    def fact_checker(self) -> Agent:
        return Agent(
            config=self.agents_config["fact_checker"],  # type: ignore[index]
            tools=[self.serper_tool, self.read_history_tool],
            llm=self.research_model,
            verbose=True,
        )

    @task
    def scout_news_task(self) -> Task:
        return Task(
            config=self.tasks_config["scout_news_task"],  # type: ignore[index]
        )

    @task
    def curate_and_validate_task(self) -> Task:
        return Task(
            config=self.tasks_config["curate_and_validate_task"],  # type: ignore[index]
            context=[self.scout_news_task()],
            output_file="report.md",
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[self.trend_scout(), self.fact_checker()],
            tasks=[self.scout_news_task(), self.curate_and_validate_task()],
            process=Process.sequential,
            verbose=True,
        )

    def _enable_tracing(self) -> dict[str, str]:
        self._load_dotenv_file()

        os.environ.setdefault("CREWAI_TRACING_ENABLED", "true")
        os.environ.setdefault("OTEL_SDK_DISABLED", "false")

        current_exporter = (os.environ.get("OTEL_TRACES_EXPORTER") or "").strip().lower()
        if not current_exporter or current_exporter == "console":
            os.environ["OTEL_TRACES_EXPORTER"] = "otlp"

        return {
            "CREWAI_TRACING_ENABLED": os.environ.get("CREWAI_TRACING_ENABLED", ""),
            "OTEL_SDK_DISABLED": os.environ.get("OTEL_SDK_DISABLED", ""),
            "OTEL_TRACES_EXPORTER": os.environ.get("OTEL_TRACES_EXPORTER", ""),
        }

    def _load_dotenv_file(self) -> None:
        env_path = self.project_root / ".env"
        if not env_path.exists():
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)

    def _published_history_file(self) -> Path:
        return self.project_root / "data" / "published_news.json"

    def next_edition_number(self) -> int:
        history_file = self._published_history_file()
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

    # _extract_json, _extract_body_html, and _safe_slug have been moved to market_match.utils
    # as extract_json, extract_body_html, and safe_slug.

    @staticmethod
    def _first_non_empty(*values: str | None) -> str:
        for value in values:
            if value and str(value).strip():
                return str(value).strip()
        return ""

    def _trace_info_from_inputs(self, inputs: dict[str, Any] | None) -> tuple[str, str, str]:
        if not isinstance(inputs, dict):
            return "", "", ""

        trigger_payload = inputs.get("crewai_trigger_payload")
        if not isinstance(trigger_payload, dict):
            return "", "", ""

        session_id = self._first_non_empty(
            trigger_payload.get("session_id"),
            trigger_payload.get("trace_session_id"),
            trigger_payload.get("trace_batch_id"),
        )
        access_code = self._first_non_empty(
            trigger_payload.get("access_code"),
            trigger_payload.get("trace_access_code"),
        )
        url = self._first_non_empty(
            trigger_payload.get("url"),
            trigger_payload.get("trace_url"),
        )
        return session_id, access_code, url

    def _resolve_trace_info(self, runtime_inputs: dict[str, Any]) -> tuple[str, str, str]:
        env_session_id = self._first_non_empty(
            os.environ.get("CREWAI_TRACE_SESSION_ID"),
            os.environ.get("CREWAI_TRACE_BATCH_ID"),
            os.environ.get("TRACE_SESSION_ID"),
            os.environ.get("TRACE_BATCH_ID"),
        )
        env_access_code = self._first_non_empty(
            os.environ.get("CREWAI_TRACE_ACCESS_CODE"),
            os.environ.get("TRACE_ACCESS_CODE"),
        )
        env_url = self._first_non_empty(
            os.environ.get("CREWAI_TRACE_URL"),
            os.environ.get("TRACE_URL"),
        )

        input_session_id, input_access_code, input_url = self._trace_info_from_inputs(runtime_inputs)

        session_id = self._first_non_empty(env_session_id, input_session_id)
        access_code = self._first_non_empty(env_access_code, input_access_code)
        url = self._first_non_empty(env_url, input_url)

        if not url and session_id:
            if access_code:
                url = f"https://app.crewai.com/crewai_plus/ephemeral_trace_batches/{session_id}?access_code={access_code}"
            else:
                url = f"https://app.crewai.com/crewai_plus/ephemeral_trace_batches/{session_id}"

        return session_id, access_code, url

    def _print_startup_banner(self, runtime_inputs: dict[str, Any]) -> None:
        console = Console()
        session_id, access_code, url = self._resolve_trace_info(runtime_inputs)
        exporter = (os.environ.get("OTEL_TRACES_EXPORTER") or "").strip().lower()
        tracing_enabled = (os.environ.get("CREWAI_TRACING_ENABLED") or "").strip().lower() == "true"
        has_trace_link = bool(session_id and access_code and url)
        live_web = tracing_enabled and exporter != "console" and exporter != "" and has_trace_link
        status = "[bold green]READY[/]" if live_web else "[bold yellow]PENDING[/]"
        hint = (
            "[dim]Le lien web apparaît généralement après la finalisation du batch,\n"
            "ou immédiatement si crewai_trigger_payload contient session/access/url.[/]"
        )
        content = (
            f"🌐 Live Web Trace: {status}\n"
            f"✅ Trace batch session ID: {session_id or '[dim]N/A[/]'}\n\n"
            f"🔗 View here: {url or '[dim]N/A[/]'}\n"
            f"🔑 Access Code: {access_code or '[dim]N/A[/]'}\n\n"
            f"{hint}"
        )
        console.print(
            Panel(
                content,
                title="[bold green]Trace Batch[/]",
                border_style="green",
                padding=(1, 4),
            )
        )

    def _run_topup_crew(self, runtime_inputs: dict[str, Any], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run a supplementary research+curation pass to complete a short selection."""
        needed = 4 - len(existing)
        existing_ids = json.dumps([item.get("event_id", "") for item in existing], ensure_ascii=False)

        topup_inputs = {
            **runtime_inputs,
            "found_count": len(existing),
            "needed_count": needed,
            "existing_event_ids": existing_ids,
        }

        scout_agent = Agent(
            config=self.agents_config["trend_scout"],  # type: ignore[index]
            tools=[self.serper_tool, self.read_history_tool],
            llm=self.research_model,
            verbose=True,
        )
        curator_agent = Agent(
            config=self.agents_config["fact_checker"],  # type: ignore[index]
            tools=[self.serper_tool, self.read_history_tool],
            llm=self.research_model,
            verbose=True,
        )

        scout_cfg = self.tasks_config["topup_scout_task"]  # type: ignore[index]
        scout_task = Task(
            description=format_template(scout_cfg["description"], **topup_inputs),
            expected_output=format_template(scout_cfg["expected_output"], **topup_inputs),
            agent=scout_agent,
        )
        curate_cfg = self.tasks_config["topup_curate_task"]  # type: ignore[index]
        curate_task = Task(
            description=format_template(curate_cfg["description"], **topup_inputs),
            expected_output=format_template(curate_cfg["expected_output"], **topup_inputs),
            agent=curator_agent,
            context=[scout_task],
        )

        result = Crew(
            agents=[scout_agent, curator_agent],
            tasks=[scout_task, curate_task],
            process=Process.sequential,
            verbose=True,
        ).kickoff(inputs=topup_inputs)

        payload = extract_json(getattr(result, "raw", str(result)))
        extras = payload.get("selected_news", [])
        if not isinstance(extras, list):
            return []
        existing_ids_set = {item.get("event_id", "") for item in existing}
        return [item for item in extras if isinstance(item, dict) and item.get("event_id", "") not in existing_ids_set]

    def _run_selection_crew(self, runtime_inputs: dict[str, Any]) -> list[dict[str, Any]]:
        console = Console()
        selection_result = self.crew().kickoff(inputs=runtime_inputs)
        payload = extract_json(getattr(selection_result, "raw", str(selection_result)))

        selected_news = payload.get("selected_news", [])
        if not isinstance(selected_news, list):
            selected_news = []

        selected_news = [item for item in selected_news if isinstance(item, dict)]

        if len(selected_news) < 4:
            console.print(
                f"[yellow]⚠ Seulement {len(selected_news)} nouvelle(s) trouvée(s) — "
                "lancement d'un passage de recherche complémentaire…[/]"
            )
            extras = self._run_topup_crew(runtime_inputs, selected_news)
            selected_news = (selected_news + extras)[:6]
            console.print(f"[green]✔ {len(selected_news)} nouvelle(s) après le passage complémentaire.[/]")

        if len(selected_news) == 0:
            raise ValueError("Aucune nouvelle validée après deux passages de recherche.")

        return selected_news[:6]

    def _run_single_news_crew(self, news_item: dict[str, Any], index: int) -> dict[str, Any]:
        news_json = json.dumps(news_item, ensure_ascii=False)

        def _agent(key: str) -> Agent:
            return Agent(config=self.agents_config[key], llm=self.writing_model, verbose=True)  # type: ignore[index]

        def _task(key: str, agent: Agent, **kw: Any) -> Task:
            cfg = self.tasks_config[key]  # type: ignore[index]
            return Task(
                description=format_template(cfg["description"], **kw),
                expected_output=cfg["expected_output"],
                agent=agent,
            )

        title_agent      = _agent("title_writer")
        intro_agent      = _agent("intro_writer")
        essentials_agent = _agent("essentials_analyst")
        practice_agent   = _agent("practice_analyst")
        breakdown_agent  = _agent("breakdown_analyst")
        stake_agent      = _agent("stake_analyst")
        verdict_agent    = _agent("verdict_editorialist")
        assembler_agent  = _agent("content_assembler")

        kw = {"news_json": news_json}
        title_task      = _task("title_task",      title_agent,      **kw)
        intro_task      = _task("intro_task",      intro_agent,      **kw)
        essentials_task = _task("essentials_task", essentials_agent, **kw)
        practice_task   = _task("practice_task",   practice_agent,   **kw)
        breakdown_task  = _task("breakdown_task",  breakdown_agent,  **kw)
        stake_task      = _task("stake_task",      stake_agent,      **kw)
        verdict_task    = _task("verdict_task",    verdict_agent,    **kw)

        assemble_cfg = self.tasks_config["assemble_task"]  # type: ignore[index]
        assemble_task = Task(
            description=format_template(assemble_cfg["description"], **kw),
            expected_output=assemble_cfg["expected_output"],
            agent=assembler_agent,
            context=[title_task, intro_task, essentials_task, practice_task, breakdown_task, stake_task, verdict_task],
        )

        news_crew = Crew(
            agents=[title_agent, intro_agent, essentials_agent, practice_agent, breakdown_agent, stake_agent, verdict_agent, assembler_agent],
            tasks=[title_task, intro_task, essentials_task, practice_task, breakdown_task, stake_task, verdict_task, assemble_task],
            process=Process.sequential,
            verbose=True,
        )

        output = news_crew.kickoff()
        news_payload = extract_json(getattr(output, "raw", str(output)))
        news_payload["sources"] = news_payload.get("sources", news_item.get("sources", []))

        fallback_slug = f"news-{index:02d}"
        news_payload["slug"] = safe_slug(str(news_payload.get("title_en", "")), fallback_slug)
        return news_payload

    def _run_title_crew(self, news_items: list[dict[str, Any]], edition_number: int) -> dict[str, str]:
        title_agent = Agent(config=self.agents_config["newsletter_title_writer"], llm=self.writing_model, verbose=True)  # type: ignore[index]
        cfg = self.tasks_config["newsletter_title_task"]  # type: ignore[index]
        task = Task(
            description=format_template(cfg["description"], edition_number=edition_number, news_items_json=json.dumps(news_items, ensure_ascii=False)),
            expected_output=cfg["expected_output"],
            agent=title_agent,
        )
        result = Crew(agents=[title_agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        return extract_json(getattr(result, "raw", str(result)))

    def _run_intro_crew(self, news_items: list[dict[str, Any]]) -> dict[str, Any]:
        intro_agent = Agent(config=self.agents_config["newsletter_intro_writer"], llm=self.writing_model, verbose=True)  # type: ignore[index]
        mini_news = [{"title_fr": i.get("title_fr", ""), "title_en": i.get("title_en", ""), "essentiel_fr": i.get("essentiel_fr", ""), "essentials_en": i.get("essentials_en", "")} for i in news_items]
        cfg = self.tasks_config["newsletter_intro_task"]  # type: ignore[index]
        task = Task(
            description=format_template(cfg["description"], news_items_json=json.dumps(mini_news, ensure_ascii=False)),
            expected_output=cfg["expected_output"],
            agent=intro_agent,
        )
        result = Crew(agents=[intro_agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        return extract_json(getattr(result, "raw", str(result)))

    def _run_social_agent(self, platform: str, title_fr: str, news_items: list[dict[str, Any]]) -> str:
        social_agent = Agent(config=self.agents_config["social_writer"], llm=self.writing_model, verbose=True)  # type: ignore[index]

        placeholder_rule = "Inclure le placeholder [LIEN_URL] à la fin." if platform in {"LinkedIn", "Twitter/X"} else "Ne pas inclure de placeholder URL."
        char_limit = "280 caractères max pour Twitter/X." if platform == "Twitter/X" else ""
        mini_news = [{"title_fr": i.get("title_fr", ""), "essentiel_fr": i.get("essentiel_fr", "")} for i in news_items]
        cfg = self.tasks_config["social_post_task"]  # type: ignore[index]
        task = Task(
            description=format_template(
                cfg["description"],
                platform=platform,
                placeholder_rule=placeholder_rule,
                char_limit=char_limit,
                title_fr=title_fr,
                news_items_json=json.dumps(mini_news, ensure_ascii=False),
            ),
            expected_output=cfg["expected_output"],
            agent=social_agent,
        )
        result = Crew(agents=[social_agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        payload = extract_json(getattr(result, "raw", str(result)))
        return str(payload.get("post", "")).strip()

    @staticmethod
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

    def _render_newsletter_html(
        self,
        *,
        lang: str,
        title: str,
        intro_sentence: str,
        intro_bullets: list[str],
        news_items: list[dict[str, Any]],
    ) -> str:
        html_lang = "fr" if lang == "fr" else "en"
        intro_list = "".join(f"<li>{bullet}</li>" for bullet in intro_bullets)
        news_html = "\n".join(self._build_news_html(item, lang, idx) for idx, item in enumerate(news_items, start=1))

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

        return f"""<!doctype html>
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

    def _export_edition(
        self,
        *,
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
        tracing_env: dict[str, str],
    ) -> Path:
        edition_dir = self.project_root / "editions" / f"edition_{edition_number}_{edition_date}"
        edition_dir.mkdir(parents=True, exist_ok=True)

        (edition_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "edition_number": edition_number,
                    "edition_date": edition_date,
                    "news_count": len(news_items),
                    "writing_model": self.writing_model,
                    "research_model": self.research_model,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        (edition_dir / "trace_config.json").write_text(
            json.dumps(tracing_env, ensure_ascii=False, indent=2),
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

        # --- share/ subfolder: flat text files ready to paste/publish ---
        share_dir = edition_dir / "share"
        share_dir.mkdir(parents=True, exist_ok=True)

        (share_dir / "newsletter_fr.html").write_text(
            extract_body_html(newsletter_html_fr), encoding="utf-8"
        )
        (share_dir / "newsletter_en.html").write_text(
            extract_body_html(newsletter_html_en), encoding="utf-8"
        )
        (share_dir / "title_fr.txt").write_text(title_fr, encoding="utf-8")
        (share_dir / "title_en.txt").write_text(title_en, encoding="utf-8")
        (share_dir / "facebook_fr.txt").write_text(facebook_fr, encoding="utf-8")
        (share_dir / "linkedin_fr.txt").write_text(linkedin_fr, encoding="utf-8")
        (share_dir / "twitter_fr.txt").write_text(twitter_fr, encoding="utf-8")
        thumbnail_prompt = news_items[0].get("image_prompt_en", "") if news_items else ""
        (share_dir / "thumbnail_prompt_news.txt").write_text(thumbnail_prompt, encoding="utf-8")

        return edition_dir

    def _save_publication_history(self, edition_number: int, edition_date: str, news_items: list[dict[str, Any]]) -> str:
        items = []
        for item in news_items:
            sources = item.get("sources", [])
            source = ""
            if isinstance(sources, list) and sources:
                source = str(sources[0].get("url", ""))
            items.append(
                {
                    "title": item.get("title_fr", item.get("title_en", "")),
                    "source": source,
                }
            )

        return self.save_history_tool._run(
            edition_number=edition_number,
            edition_date=edition_date,
            items_json=json.dumps(items, ensure_ascii=False),
        )

    def run_newsletter(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        tracing_env = self._enable_tracing()

        today = datetime.now().date().isoformat()
        default_inputs = {
            "topic": "AI news in sport and finance",
            "current_year": str(datetime.now().year),
            "edition_date": today,
            "edition_number": self.next_edition_number(),
        }
        runtime_inputs = default_inputs if inputs is None else {**default_inputs, **inputs}

        edition_number = int(runtime_inputs["edition_number"])
        edition_date = str(runtime_inputs["edition_date"])

        self._print_startup_banner(runtime_inputs)

        selected_news = self._run_selection_crew(runtime_inputs)

        news_items: list[dict[str, Any]] = []
        for index, selected in enumerate(selected_news, start=1):
            news_payload = self._run_single_news_crew(selected, index)
            news_items.append(news_payload)

        title_payload = self._run_title_crew(news_items, edition_number)
        intro_payload = self._run_intro_crew(news_items)

        title_fr = str(title_payload.get("title_fr", f"Market & Match #{edition_number}: IA sport & finance"))
        title_en = str(title_payload.get("title_en", f"Market & Match #{edition_number}: AI in sports & finance"))

        intro_sentence_fr = str(intro_payload.get("intro_sentence_fr", "Dans l'édition d'aujourd'hui de Market & Match, nous couvrons les actualités IA clés de la semaine."))
        intro_sentence_en = str(intro_payload.get("intro_sentence_en", "In today's edition of Market & Match, we cover the key AI stories of the week."))

        intro_bullets_fr = intro_payload.get("intro_bullets_fr", [])
        intro_bullets_en = intro_payload.get("intro_bullets_en", [])
        if not isinstance(intro_bullets_fr, list):
            intro_bullets_fr = []
        if not isinstance(intro_bullets_en, list):
            intro_bullets_en = []

        newsletter_html_fr = self._render_newsletter_html(
            lang="fr",
            title=title_fr,
            intro_sentence=intro_sentence_fr,
            intro_bullets=intro_bullets_fr,
            news_items=news_items,
        )
        newsletter_html_en = self._render_newsletter_html(
            lang="en",
            title=title_en,
            intro_sentence=intro_sentence_en,
            intro_bullets=intro_bullets_en,
            news_items=news_items,
        )

        facebook_fr = self._run_social_agent("Facebook", title_fr, news_items)
        linkedin_fr = self._run_social_agent("LinkedIn", title_fr, news_items)
        twitter_fr = self._run_social_agent("Twitter/X", title_fr, news_items)

        edition_dir = self._export_edition(
            edition_number=edition_number,
            edition_date=edition_date,
            title_fr=title_fr,
            title_en=title_en,
            intro_payload=intro_payload,
            news_items=news_items,
            newsletter_html_fr=newsletter_html_fr,
            newsletter_html_en=newsletter_html_en,
            facebook_fr=facebook_fr,
            linkedin_fr=linkedin_fr,
            twitter_fr=twitter_fr,
            tracing_env=tracing_env,
        )

        history_result = self._save_publication_history(
            edition_number=edition_number,
            edition_date=edition_date,
            news_items=news_items,
        )

        return {
            "edition_number": edition_number,
            "edition_date": edition_date,
            "news_count": len(news_items),
            "title_fr": title_fr,
            "title_en": title_en,
            "edition_dir": str(edition_dir),
            "history_update": history_result,
            "trace_enabled": tracing_env,
        }
