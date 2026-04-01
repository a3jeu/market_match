"""NewsAPI.AI (Event Registry) integration tools for searching recent news."""

import datetime
import json
import os

import requests
from crewai.tools import BaseTool
from pydantic import Field


class NewsAPISearchTool(BaseTool):
    """Search for news articles using NewsAPI.AI (Event Registry).
    
    Requires NEWSAPI_KEY environment variable.
    Free tier: 2,000 tokens for testing
    """
    
    name: str = "NewsAPI.AI Search Tool"
    description: str = (
        "Search for recent news articles using NewsAPI.AI (Event Registry). "
        "Query for recent news by keywords. "
        "Returns a list of articles with title, description, URL, published date, and source."
    )
    api_key: str = Field(default_factory=lambda: os.environ.get("NEWSAPI_KEY", ""))
    # base_url: str = "https://eventregistry.org/api/v1/article/getArticles"
    base_url: str = "https://newsapi.org/v2/everything"
    default_language: str = "eng"
    # default_sort_by: str = "date"
    default_sort_by: str = "relevancy"
    default_sort_ascending: bool = False
    default_from_days_ago: int = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.api_key:
            raise ValueError(
                "NEWSAPI_KEY environment variable not set. "
                "Get a free API key from https://newsapi.ai/"
            )

    def _build_request_body(self, query: str, kwargs: dict) -> dict:
        # return {
        #     "action": "getArticles",
        #     "keyword": kwargs.get("keyword", query),
        #     "articlesPage": kwargs.get("articles_page", 1),
        #     "resultType": kwargs.get("result_type", "articles"),
        #     "lang": self.default_language,
        #     "articlesSortBy": self.default_sort_by,
        #     "articlesSortByAsc": self.default_sort_ascending,
        #     "articlesCount": kwargs.get("articles_count", 10),
        #     "dataType": kwargs.get("data_type", ["news"]),
        #     "forceMaxDataTimeWindow": kwargs.get("force_max_data_time_window", 31),
        #     "includeArticleImage": True,
        #     "includeArticleAuthors": True,
        #     "includeSourceTitle": True,
        #     "includeArticleBasicInfo": True,
        #     "apiKey": self.api_key,
        # }
        return {
            "q": kwargs.get("keyword", query),
            # "page": kwargs.get("articles_page", 1),
            # "pageSize": kwargs.get("articles_count", 10),
            # "language": self.default_language,
            "sortBy": self.default_sort_by,
            "apiKey": self.api_key,
            "from": (datetime.datetime.now() - datetime.timedelta(days=self.default_from_days_ago)).strftime("%Y-%m-%d")
        }
    def _fetch_articles(self, request_body: dict) -> dict:
        # response = requests.post(self.base_url, json=request_body, timeout=10)
        
        # Print the request body for debugging        print("Request body:")
        # print(self.base_url)
        # print(json.dumps(request_body, indent=2))
        # https://newsapi.org/v2/everything?apiKey=dd004e4f08124db280215a9668f47796&q=perplexity+finance+model&from=2026-03-18&sortBy=relevancy

        # response = requests.get(self.base_url, json=request_body, timeout=10)
        response = requests.get(self.base_url, params=request_body, timeout=10)
        
        # get full url with query parameters for debugging
        # print(f"Request URL: {response.url}")
        
        # print(f"Response status code: {response.status_code}")
        # print(f"Response content: {response.text}")
        
        

        if response.status_code == 401:
            return {"error": "Invalid or expired API key. Check NEWSAPI_KEY environment variable."}
        if response.status_code == 403:
            return {"error": "API key forbidden or tokens exhausted. Check your newsapi.ai account."}

        response.raise_for_status()
        return response.json()

    def _run(self, query: str, **kwargs) -> str:
        """Execute a news search.
        
        Args:
            query: Keywords or phrases to search for in the article title and body.
            
        Returns:
            JSON string with search results
        """
        try:
            request_body = self._build_request_body(query, kwargs)
            data = self._fetch_articles(request_body)
            
            return data
            
            # Check for API errors in response
            if "error" in data:
                return f"Error: {data.get('error') or data.get('message', 'Unknown error')}"
            
            # Format articles for the agent
            articles = data.get("articles", {}).get("results", [])
            formatted_articles = []
            
            for article in articles:
                formatted_articles.append({
                    "uri": article.get("uri", ""),
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "description": article.get("summary", ""),
                    "body": article.get("body", ""),
                    "published_at": article.get("dateTimePub") or article.get("dateTime") or article.get("publishedDate", ""),
                    "source": article.get("source", {}).get("title", "") if isinstance(article.get("source"), dict) else "",
                    "author": article.get("authors", [{}])[0].get("name", "") if article.get("authors") else "",
                    "image": article.get("image", ""),
                    "language": article.get("lang", ""),
                })
            
            return json.dumps(formatted_articles, ensure_ascii=False, indent=2)
            
        except requests.exceptions.RequestException as e:
            return f"Error querying NewsAPI.AI: {str(e)}"
        except json.JSONDecodeError as e:
            return f"Error parsing NewsAPI.AI response: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"
