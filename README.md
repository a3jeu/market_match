# Market & Match (CrewAI)

Ce projet génère automatiquement une newsletter hebdomadaire **Market & Match** sur les nouveautés IA liées au **sport** et/ou à la **finance**, via une orchestration multi-agents.

Pipeline:
- recherche l'actualité récente sur le web via **SerperDevTool**,
- sélectionne 4 à 6 nouvelles non redondantes,
- lance un **sous-crew par nouvelle** (avec sections détaillées),
- génère introduction + titre via agents dédiés,
- génère un agent dédié par réseau social,
- génère un prompt image spécifique à chaque nouvelle,
- génère le HTML FR/EN avec sections en gras,
- exporte l'édition dans un dossier versionné,
- conserve l'historique pour éviter de répéter les mêmes nouvelles d'une semaine à l'autre.

## Installation

Assure-toi d'avoir Python >=3.10 <3.14. Ce projet utilise [UV](https://docs.astral.sh/uv/).

Installe `uv` si nécessaire:

```bash
pip install uv
```

Depuis la racine du projet:
```bash
crewai install
```

### Variables `.env`

Tu dois avoir au minimum:

```env
OPENAI_API_KEY=...
SERPER_API_KEY=...
MARKET_MATCH_RESEARCH_MODEL=gpt-4o-mini
MARKET_MATCH_WRITING_MODEL=gpt-5-mini

# Tracing CrewAI / OTel
CREWAI_TRACING_ENABLED=true
OTEL_SDK_DISABLED=false
OTEL_TRACES_EXPORTER=console
```

## Exécution

Lancer avec les valeurs par défaut (date du jour + prochain numéro d'édition):

```bash
crewai run
```

## Sorties générées

Chaque édition est exportée dans:

`editions/edition_{no_edition}_{YYYY-MM-DD}/`

Fichiers générés:
- `metadata.json`
- `trace_config.json`
- `title_fr.json` / `title_en.json`
- `introduction_fr.json` / `introduction_en.json`
- `news_01.json` à `news_0N.json`
- `image_prompt_news_01.json` à `image_prompt_news_0N.json`
- `thumbnail_prompt_news_01.json`
- `facebook_fr.json` / `linkedin_fr.json` / `twitter_fr.json`
- `newsletter_fr.html` / `newsletter_en.html`
- `report.md` (sortie brute de curation)

Historique des sujets déjà publiés:
- `data/published_news.json`

## Personnalisation rapide

- Agents: `src/market_match/config/agents.yaml`
- Tâches: `src/market_match/config/tasks.yaml`
- Orchestration/export: `src/market_match/crew.py`
- Entrée CLI: `src/market_match/main.py`
