#!/usr/bin/env python
"""Test different Event Registry query formats."""

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

query = "artificial intelligence"

# Try different query formats
formats = [
    {
        "name": "keyword (singular, string)",
        "body": {
            "$query": {"keyword": query},
            "apiKey": api_key
        }
    },
    {
        "name": "keyword (singular, array)",
        "body": {
            "$query": {"keyword": [query]},
            "apiKey": api_key
        }
    },
    {
        "name": "keywords (plural, string)",
        "body": {
            "$query": {"keywords": query},
            "apiKey": api_key
        }
    },
    {
        "name": "keywords (plural, array)",
        "body": {
            "$query": {"keywords": [query]},
            "apiKey": api_key
        }
    },
    {
        "name": "keywordOper OR",
        "body": {
            "$query": {"keywords": query, "keywordOper": "or"},
            "apiKey": api_key
        }
    },
]

print("🧪 Testing different query formats...")
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
            print(f"   ⚠️  Unexpected response: {str(data)[:100]}")
    except Exception as e:
        print(f"   ❌ Exception: {e}")
