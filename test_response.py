#!/usr/bin/env python
"""See full response from Event Registry API."""

import json
import os
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load .env
from dotenv import load_dotenv
load_dotenv()

import requests

api_key = os.getenv("NEWSAPI_KEY")
endpoint = "https://eventregistry.org/api/v1/article/getArticles"
query = "artificial intelligence"

print("Testing without any query parameter (should return latest)...")
print("=" * 70)

response = requests.get(
    endpoint,
    params={"apiKey": api_key, "articlesCount": 5},
    timeout=5
)

data = response.json()
print(f"Status: {response.status_code}")
print(f"\nFirst article:")
if data.get("articles", {}).get("results"):
    article = data["articles"]["results"][0]
    print(json.dumps(article, indent=2, default=str)[:1000])
    print("\n...(truncated)")
else:
    print("No articles!")

print("\n\nNow testing WITH keywords parameter...")
print("=" * 70)

response = requests.get(
    endpoint,
    params={"apiKey": api_key, "keywords": query, "articlesCount": 5},
    timeout=5
)

data = response.json()
print(f"Status: {response.status_code}")
print(f"Has error: {'error' in data}")
if "error" in data:
    print(f"Error: {data['error']}")
else:
    count = len(data.get("articles", {}).get("results", []))
    print(f"Found {count} articles")
