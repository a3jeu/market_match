#!/usr/bin/env python
import json
import sys
import warnings

from datetime import datetime

from market_match.crew import MarketMatch

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

def _default_inputs() -> dict:
    runner = MarketMatch()
    return {
        'topic': 'AI news in sport and finance',
        'current_year': str(datetime.now().year),
        'edition_date': datetime.now().date().isoformat(),
        'edition_number': runner.next_edition_number(),
    }


def _inputs_from_cli_or_default() -> dict:
    if len(sys.argv) < 2:
        return _default_inputs()

    try:
        cli_payload = json.loads(sys.argv[1])
        if not isinstance(cli_payload, dict):
            raise ValueError("CLI payload must be a JSON object")
        return {**_default_inputs(), **cli_payload}
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON payload provided: {e}")

def run():
    """
    Run the crew.
    """
    inputs = _inputs_from_cli_or_default()

    try:
        summary = MarketMatch().run_newsletter(inputs=inputs)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = _default_inputs()
    try:
        MarketMatch().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        MarketMatch().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = _default_inputs()

    try:
        MarketMatch().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

def run_with_trigger():
    """
    Run the crew with trigger payload.
    """
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        **_default_inputs(),
        "crewai_trigger_payload": trigger_payload,
    }

    try:
        result = MarketMatch().run_newsletter(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
