import json
import os
from pathlib import Path

from market_match.tools import NewsAPISearchTool


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    _load_dotenv(project_root / ".env")

    query = "perplexity finance model"

    tool = NewsAPISearchTool()
    print(f"TOOL_NAME={tool.name}")
    print(
        "ARGS_SCHEMA="
        + json.dumps(tool.args_schema.model_json_schema(), indent=2, ensure_ascii=False)
    )
    print(f"QUERY={query}")

    result = tool.run(query=query)
    print("RAW_RESULT=")
    print(result)

    # parsed = json.loads(result)
    # print(f"RESULT_COUNT={len(parsed)}")

    # for index, article in enumerate(parsed[:5], start=1):
    #     print(f"ARTICLE_{index}_TITLE={article.get('title', '')}")
    #     print(f"ARTICLE_{index}_SOURCE={article.get('source', '')}")
    #     print(f"ARTICLE_{index}_PUBLISHED_AT={article.get('published_at', '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())