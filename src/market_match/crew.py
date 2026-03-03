from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool

from market_match.tools import ReadPublishedNewsTool, SavePublishedEditionTool


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
        os.environ.setdefault("CREWAI_TRACING_ENABLED", "true")
        os.environ.setdefault("OTEL_SDK_DISABLED", "false")
        os.environ.setdefault("OTEL_TRACES_EXPORTER", "console")
        return {
            "CREWAI_TRACING_ENABLED": os.environ.get("CREWAI_TRACING_ENABLED", ""),
            "OTEL_SDK_DISABLED": os.environ.get("OTEL_SDK_DISABLED", ""),
            "OTEL_TRACES_EXPORTER": os.environ.get("OTEL_TRACES_EXPORTER", ""),
        }

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

    @staticmethod
    def _extract_json(raw_output: str) -> dict[str, Any]:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        if cleaned.startswith("{") and cleaned.endswith("}"):
            return json.loads(cleaned)

        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            raise ValueError("No JSON object found in output.")

        return json.loads(cleaned[first_brace:last_brace + 1])

    @staticmethod
    def _extract_body_html(full_html: str) -> str:
        """Return only the content inside <body>…</body>, stripping the outer tags."""
        import re
        match = re.search(r"<body[^>]*>(.*?)</body>", full_html, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return full_html

    @staticmethod
    def _safe_slug(text: str, fallback: str) -> str:
        base = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
        compact = "-".join(part for part in base.split("-") if part)
        return compact[:70] if compact else fallback

    def _run_selection_crew(self, runtime_inputs: dict[str, Any]) -> list[dict[str, Any]]:
        selection_result = self.crew().kickoff(inputs=runtime_inputs)
        payload = self._extract_json(getattr(selection_result, "raw", str(selection_result)))

        selected_news = payload.get("selected_news", [])
        if not isinstance(selected_news, list):
            raise ValueError("Selection payload does not contain 'selected_news' list.")

        selected_news = [item for item in selected_news if isinstance(item, dict)]
        if len(selected_news) < 4:
            raise ValueError("Selection returned fewer than 4 validated news.")

        return selected_news[:6]

    def _run_single_news_crew(self, news_item: dict[str, Any], index: int) -> dict[str, Any]:
        news_json = json.dumps(news_item, ensure_ascii=False)

        title_agent = Agent(
            role="Titreur bilingue Market & Match",
            goal="Écrire un titre court, percutant, actionnable en FR et EN.",
            backstory="Tu écris des titres qui capturent un résultat concret.",
            llm=self.writing_model,
            verbose=True,
        )
        intro_agent = Agent(
            role="Rédacteur d'accroches",
            goal="Rédiger une phrase introductrice claire et contextualisée en FR et EN.",
            backstory="Tu poses le contexte en une phrase, sans jargon inutile.",
            llm=self.writing_model,
            verbose=True,
        )
        essentials_agent = Agent(
            role="Analyste L'essentiel",
            goal="Résumer l'événement en 1-2 phrases en FR et EN.",
            backstory="Tu extrais l'information indispensable sans digression.",
            llm=self.writing_model,
            verbose=True,
        )
        practice_agent = Agent(
            role="Analyste En pratique",
            goal="Expliquer la mécanique en 3-5 phrases en FR et EN.",
            backstory="Tu démystifies le fonctionnement technique de manière pédagogique.",
            llm=self.writing_model,
            verbose=True,
        )
        breakdown_agent = Agent(
            role="Analyste Décryptage",
            goal="Donner le contexte de fond en 3-5 phrases en FR et EN.",
            backstory="Tu relies le fait de la semaine aux tendances structurelles.",
            llm=self.writing_model,
            verbose=True,
        )
        stake_agent = Agent(
            role="Analyste L'enjeu",
            goal="Analyser les gagnants/perdants en 3-5 phrases en FR et EN.",
            backstory="Tu identifies des impacts concrets et les parties prenantes.",
            llm=self.writing_model,
            verbose=True,
        )
        verdict_agent = Agent(
            role="Éditorialiste Verdict",
            goal="Prendre position en 1-2 phrases en FR et EN.",
            backstory="Tu es développeur, passionné de sports, de finances et de technologie. Tu assumes un point de vue tranché et argumenté.  Tu es l'auteur de la lettre et tu dois prendre position. ",
            llm=self.writing_model,
            verbose=True,
        )
        assembler_agent = Agent(
            role="Assembleur de nouvelle bilingue",
            goal="Assembler les sections en un JSON strict et ajouter un prompt image spécifique à cette nouvelle.",
            backstory="Tu garantis conformité de structure, clarté et cohérence éditoriale.",
            llm=self.writing_model,
            verbose=True,
        )

        title_task = Task(
            description=(
                "Écris un titre FR et un titre EN pour la nouvelle suivante. "
                "Le titre doit décrire une action ou un résultat concret.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"title_fr":"...", "title_en":"..."}'
            ),
            expected_output="JSON strict avec title_fr et title_en.",
            agent=title_agent,
        )

        intro_task = Task(
            description=(
                "Rédige une phrase introductrice FR et EN (une seule phrase par langue), basée sur la nouvelle validée.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"intro_fr":"...", "intro_en":"..."}'
            ),
            expected_output="JSON strict avec intro_fr et intro_en.",
            agent=intro_agent,
        )

        essentials_task = Task(
            description=(
                "Rédige la section L’essentiel (FR) et The Essentials (EN) en 1 à 2 phrases par langue.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"essentiel_fr":"...", "essentials_en":"..."}'
            ),
            expected_output="JSON strict avec essentiel_fr et essentials_en.",
            agent=essentials_agent,
        )

        practice_task = Task(
            description=(
                "Rédige la section En pratique (FR) et In Practice (EN) en 3 à 5 phrases par langue.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"pratique_fr":"...", "in_practice_en":"..."}'
            ),
            expected_output="JSON strict avec pratique_fr et in_practice_en.",
            agent=practice_agent,
        )

        breakdown_task = Task(
            description=(
                "Rédige la section Décryptage (FR) et Breakdown (EN) en 3 à 5 phrases par langue.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"decryptage_fr":"...", "breakdown_en":"..."}'
            ),
            expected_output="JSON strict avec decryptage_fr et breakdown_en.",
            agent=breakdown_agent,
        )

        stake_task = Task(
            description=(
                "Rédige la section L'enjeu (FR) et What's at Stake (EN) en 3 à 5 phrases par langue, "
                "avec bénéficiaires et perdants potentiels.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"enjeu_fr":"...", "whats_at_stake_en":"..."}'
            ),
            expected_output="JSON strict avec enjeu_fr et whats_at_stake_en.",
            agent=stake_agent,
        )

        verdict_task = Task(
            description=(
                "Rédige un verdict tranché en 1 à 2 phrases par langue (FR/EN).\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "Réponds uniquement en JSON: "
                '{"verdict_fr":"...", "verdict_en":"..."}'
            ),
            expected_output="JSON strict avec verdict_fr et verdict_en.",
            agent=verdict_agent,
        )

        assemble_task = Task(
            description=(
                "Assemble toutes les sections précédentes dans UN JSON strict avec les clés EXACTES:\n"
                "title_fr, title_en, intro_fr, intro_en, essentiel_fr, essentials_en, pratique_fr, in_practice_en, "
                "decryptage_fr, breakdown_en, enjeu_fr, whats_at_stake_en, verdict_fr, verdict_en, image_prompt_en, sources.\n"
                "image_prompt_en doit être spécifique à CETTE nouvelle (pas générique), format paysage.\n"
                f"NOUVELLE SOURCE: {news_json}\n"
                "sources doit être une liste de 2 à 3 objets {\"label\":\"...\",\"url\":\"https://...\"}."
            ),
            expected_output="JSON strict final pour une nouvelle.",
            agent=assembler_agent,
            context=[
                title_task,
                intro_task,
                essentials_task,
                practice_task,
                breakdown_task,
                stake_task,
                verdict_task,
            ],
        )

        news_crew = Crew(
            agents=[
                title_agent,
                intro_agent,
                essentials_agent,
                practice_agent,
                breakdown_agent,
                stake_agent,
                verdict_agent,
                assembler_agent,
            ],
            tasks=[
                title_task,
                intro_task,
                essentials_task,
                practice_task,
                breakdown_task,
                stake_task,
                verdict_task,
                assemble_task,
            ],
            process=Process.sequential,
            verbose=True,
        )

        output = news_crew.kickoff()
        news_payload = self._extract_json(getattr(output, "raw", str(output)))
        news_payload["sources"] = news_payload.get("sources", news_item.get("sources", []))

        fallback_slug = f"news-{index:02d}"
        news_payload["slug"] = self._safe_slug(str(news_payload.get("title_en", "")), fallback_slug)
        return news_payload

    def _run_title_crew(self, news_items: list[dict[str, Any]], edition_number: int) -> dict[str, str]:
        title_agent = Agent(
            role="Rédacteur titre de newsletter",
            goal="Créer un titre accrocheur FR/EN au format Market & Match #N: ...",
            backstory="Tu condenses les angles forts de l'édition en une promesse éditoriale.",
            llm=self.writing_model,
            verbose=True,
        )
        task = Task(
            description=(
                f"Crée les titres FR/EN pour l'édition #{edition_number}. "
                "Respecte strictement le format: Market & Match #N: ...\n"
                f"NOUVELLES: {json.dumps(news_items, ensure_ascii=False)}\n"
                "Réponds uniquement en JSON: "
                '{"title_fr":"Market & Match #N: ...", "title_en":"Market & Match #N: ..."}'
            ),
            expected_output="JSON strict avec title_fr/title_en.",
            agent=title_agent,
        )
        result = Crew(agents=[title_agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        return self._extract_json(getattr(result, "raw", str(result)))

    def _run_intro_crew(self, news_items: list[dict[str, Any]]) -> dict[str, Any]:
        intro_agent = Agent(
            role="Rédacteur introduction newsletter",
            goal="Écrire l'introduction FR/EN et des bullet-points courts et accrocheurs.",
            backstory="Tu annonces le programme avec l'énergie d'un bon editor : concis, percutant, engageant.",
            llm=self.writing_model,
            verbose=True,
        )
        mini_news = [{"title_fr": i.get("title_fr", ""), "title_en": i.get("title_en", ""), "essentiel_fr": i.get("essentiel_fr", ""), "essentials_en": i.get("essentials_en", "")} for i in news_items]
        task = Task(
            description=(
                "Génère l'introduction FR/EN de la newsletter.\n"
                "CONTRAINTES intro_sentence_fr:\n"
                "- Commence EXACTEMENT par : \"Dans l'édition d'aujourd'hui de Market & Match,\"\n"
                "- Termine en 1 seule phrase, sans liste.\n"
                "CONTRAINTES intro_bullets_fr / intro_bullets_en:\n"
                "- 1 bullet par nouvelle (4 à 6 bullets au total).\n"
                "- Chaque bullet : 1 phrase courte et percutante, max 15 mots.\n"
                "- Commence par un verbe d'action ou un angle fort, pas par le nom de l'entreprise.\n"
                "- Pas de répétition entre bullets.\n"
                f"NOUVELLES: {json.dumps(mini_news, ensure_ascii=False)}\n"
                "Réponds uniquement en JSON: "
                '{"intro_sentence_fr":"...", "intro_bullets_fr":["..."], "intro_sentence_en":"...", "intro_bullets_en":["..."]}'
            ),
            expected_output="JSON strict avec intro sentence + bullet lists courts et accrocheurs FR/EN.",
            agent=intro_agent,
        )
        result = Crew(agents=[intro_agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        return self._extract_json(getattr(result, "raw", str(result)))

    def _run_social_agent(self, platform: str, title_fr: str, news_items: list[dict[str, Any]]) -> str:
        social_agent = Agent(
            role=f"Rédacteur {platform} FR",
            goal=f"Créer un texte {platform} personnel et engageant en français.",
            backstory="Tu écris comme quelqu'un qui partage une découverte à ses abonnés, pas comme un communiqué de presse.",
            llm=self.writing_model,
            verbose=True,
        )

        placeholder_rule = "Inclure le placeholder [LIEN_URL] à la fin." if platform in {"LinkedIn", "Twitter/X"} else "Ne pas inclure de placeholder URL."
        char_limit = "280 caractères max pour Twitter/X." if platform == "Twitter/X" else ""
        mini_news = [{"title_fr": i.get("title_fr", ""), "essentiel_fr": i.get("essentiel_fr", "")} for i in news_items]
        task = Task(
            description=(
                f"Rédige un texte {platform} en français pour partager la newsletter Market & Match.\n"
                "RÈGLES DE TON:\n"
                "- Commence par une phrase personnelle du style : \"Cette semaine dans Market & Match, on décortique…\"\n"
                "- Ton naturel, direct, comme si tu partageais une découverte à tes abonnés.\n"
                "- Quelques hashtags pertinents à la fin.\n"
                f"- {placeholder_rule}\n"
                f"- {char_limit}\n"
                f"TITRE: {title_fr}\n"
                f"NOUVELLES: {json.dumps(mini_news, ensure_ascii=False)}\n"
                "Réponds uniquement en JSON: {" + '"post":"..."' + "}"
            ),
            expected_output="JSON strict avec post.",
            agent=social_agent,
        )
        result = Crew(agents=[social_agent], tasks=[task], process=Process.sequential, verbose=True).kickoff()
        payload = self._extract_json(getattr(result, "raw", str(result)))
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
        news_html = "".join(self._build_news_html(item, lang, idx) for idx, item in enumerate(news_items, start=1))

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
            self._extract_body_html(newsletter_html_fr), encoding="utf-8"
        )
        (share_dir / "newsletter_en.html").write_text(
            self._extract_body_html(newsletter_html_en), encoding="utf-8"
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
