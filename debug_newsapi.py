#!/usr/bin/env python
"""Debug script for NewsAPISearchTool to see actual request."""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load .env
from dotenv import load_dotenv
load_dotenv()

import requests

api_key = os.getenv("NEWSAPI_KEY")
base_url = "https://eventregistry.org/api/v1/article/getArticles"

print("🔍 Testing Event Registry API directly...")
print("-" * 60)

query = "artificial intelligence sports"
language = "en"

request_body = {
    "$query": {
        "keywords": [query],
        "lang": language,
    },
    "resultType": "articles",
    "articlesSortBy": "-lastUpdate",
    "articlesCount": 10,
    "apiKey": api_key,
}

print(f"📤 Request body:")
print(json.dumps(request_body, indent=2))
print()

try:
    response = requests.post(base_url, json=request_body, timeout=10)
    print(f"📥 Response status: {response.status_code}")
    print(f"📥 Response body:")
    print(json.dumps(response.json(), indent=2)[:1000])
except Exception as e:
    print(f"❌ Error: {e}")
