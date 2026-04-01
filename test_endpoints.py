#!/usr/bin/env python
"""Test different Event Registry endpoints."""

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
query = "artificial intelligence"

endpoints = [
    ("newsapi.ai REST endpoint", "https://newsapi.ai/api/v1/search"),
    ("EventRegistry /article/getArticles", "https://eventregistry.org/api/v1/article/getArticles"),
    ("EventRegistry /articles", "https://eventregistry.org/api/v1/articles"),
    ("newsapi.ai /search", "https://newsapi.ai/api/search"),
]

print("🎯 Testing endpoints...")
print("=" * 70)

for name, endpoint in endpoints:
    print(f"\n📍 {name}")
    print(f"   {endpoint}")
    
    try:
        # Try POST
        response = requests.post(
            endpoint,
            json={"keywords": [query], "apiKey": api_key},
            timeout=3
        )
        print(f"   POST {response.status_code}: {str(response.text)[:100]}")
    except Exception as e:
        print(f"   POST Error: {type(e).__name__}")
    
    try:
        # Try GET with params
        response = requests.get(
            endpoint,
            params={"keywords": query, "apiKey": api_key},
            timeout=3
        )
        print(f"   GET {response.status_code}: {str(response.text)[:100]}")
    except Exception as e:
        print(f"   GET Error: {type(e).__name__}")
