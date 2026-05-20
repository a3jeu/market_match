#!/usr/bin/env python
import json
import os
import sys
import warnings

from datetime import datetime

from market_match.crew import MarketMatch
from market_match.utils.editions import next_edition_number

import mlflow

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")
    
mlflow.crewai.autolog()

mlflow.set_tracking_uri("http://127.0.0.1:5000/") # Run in a PowerShell terminal > mlflow server
mlflow.set_experiment(f"market_match_{datetime.now().strftime('%Y-%m-%d_%H:%M')}")

news_per_topic = 3
news_to_keep = 5

def run():
    """
    Run the crew.
    """
    inputs = {
        'edition_date': datetime.now().date().isoformat(),
        'edition_number': next_edition_number(),
        'news_per_topic': news_per_topic,
        'news_preliminary_total': news_per_topic * 3,
        'news_to_keep': news_to_keep,
    }

    # Propagate edition metadata to task callbacks (CrewAI callback receives only TaskOutput).
    os.environ["MARKET_MATCH_EDITION_NUMBER"] = str(inputs["edition_number"])
    os.environ["MARKET_MATCH_EDITION_DATE"] = str(inputs["edition_date"])
    os.environ["MARKET_MATCH_NEWS_TO_KEEP"] = str(inputs["news_to_keep"])

    try:
        result = MarketMatch().crew().kickoff(inputs=inputs)
        print(result.raw)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")

if __name__ == "__main__":
    run()