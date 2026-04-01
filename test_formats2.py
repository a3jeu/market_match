#!/usr/bin/env python
"""Test Event Registry with simple query parameter."""

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
base_url = "https://eventregistry.org/api/v1/article/getArticles"

query = "artificial intelligence"

# Try even simpler formats
formats = [
    {
        "name": "query (top-level)",
        "body": {
            "query": query,
            "apiKey": api_key
        }
    },
    {
        "name": "$query with conceptUri",
        "body": {
            "$query": {"lang": "en"},
            "search": query,
            "apiKey": api_key
        }
    },
    {
        "name": "text search",
        "body": {
            "text": query,
            "apiKey": api_key
        }
    },
    {
        "name": "searchText",
        "body": {
            "searchText": query,
            "apiKey": api_key
        }
    },
]

print("🧪 Testing alternative query parameters...")
print("=" * 60)

for format_test in formats:
    print(f"\n📋 Format: {format_test['name']}")
    try:
        response = requests.post(base_url, json=format_test['body'], timeout=5)
        data = response.json()
        
        if "error" in data:
            print(f"   ❌ Error: {data['error']}")
        elif "articles" in data:
            count = len(data.get("articles", {}).get("results", []))
            print(f"   ✅ Success! Found {count} articles")
        else:
            print(f"   ℹ️  Response keys: {list(data.keys())}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")
