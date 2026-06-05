"""
Simple Web Search Function for LLM Integration
Combines Bing Search API and DuckDuckGo with fallback
"""

import asyncio
import requests
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from html import unescape
from html.parser import HTMLParser
from typing import List, Dict, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse


_web_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ScoutWeb")

async def web_search(query: str, num_results: int = 5, bing_api_key: Optional[str] = None) -> str:
    """
    Simple web search function that tries Bing first, falls back to DuckDuckGo
    
    Args:
        query: Search query string
        num_results: Number of results to return (default: 5)
        bing_api_key: Optional Bing API key, if not provided uses DuckDuckGo
    
    Returns:
        Formatted string with search results ready for LLM consumption
    """

    # Fallback to DuckDuckGo's HTML endpoint. This avoids the optional ddgs package.
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        _web_executor,
        partial(_duckduckgo_search, query, num_results),
    )
    return _format_results(results, "DuckDuckGo")

class _DuckDuckGoHTMLParser(HTMLParser):
    """Small parser for DuckDuckGo HTML result pages."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        class_name = attrs.get("class", "")

        if tag == "a" and "result__a" in class_name:
            self._current = {
                "title": "",
                "url": _decode_duckduckgo_url(attrs.get("href", "")),
                "snippet": "",
            }
            self._capture = "title"
            return

        if self._current and "result__snippet" in class_name:
            self._capture = "snippet"

    def handle_data(self, data):
        if self._current and self._capture:
            self._current[self._capture] += data

    def handle_endtag(self, tag):
        if not self._current:
            return

        if self._capture == "title" and tag == "a":
            self._capture = None
            return

        if self._capture == "snippet" and tag in ("a", "div", "td"):
            self._capture = None
            return

        if tag == "div" and self._current.get("title"):
            self.results.append({
                "title": _clean_text(self._current.get("title", "")),
                "url": self._current.get("url", ""),
                "snippet": _clean_text(self._current.get("snippet", "")),
            })
            self._current = None
            self._capture = None


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())


def _decode_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    if url.startswith("//"):
        return "https:" + url
    return url


def _duckduckgo_search(query: str, num_results: int) -> List[Dict]:
    """DuckDuckGo search implementation without third-party search packages."""
    try:
        url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ITAgent/1.0)"},
            timeout=15,
        )
        response.raise_for_status()

        parser = _DuckDuckGoHTMLParser()
        parser.feed(response.text)
        return parser.results[:num_results] or _fallback_search_message(query)
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")
        return _fallback_search_message(query)


def _fallback_search_message(query: str) -> List[Dict]:
    """Fallback when all search methods fail"""
    return [{
        'title': 'Search Unavailable',
        'url': '',
        'snippet': f'Unable to search for "{query}". Please check your internet connection or API keys.'
    }]


def _format_results(results: List[Dict], source: str) -> str:
    """Format search results for LLM consumption"""
    if not results:
        return "No search results found."
    
    formatted = f"Search Results (via {source}):\n\n"
    
    for i, result in enumerate(results, 1):
        title = result.get('title', 'No title')
        url = result.get('url', '')
        snippet = result.get('snippet', 'No description available')
        
        formatted += f"{i}. **{title}**\n"
        formatted += f"   URL: {url}\n"
        formatted += f"   Summary: {snippet}\n\n"
    
    return formatted.strip()


# Enhanced version with content extraction
def web_search_with_content(query: str, num_results: int = 3, bing_api_key: Optional[str] = None) -> str:
    """
    Enhanced search that also extracts content from top results
    
    Args:
        query: Search query string
        num_results: Number of results to get content from (default: 3)
        bing_api_key: Optional Bing API key
    
    Returns:
        Formatted string with search results and extracted content
    """
    from bs4 import BeautifulSoup
    
    # Get search results
    if bing_api_key:
        results = _bing_search(query, num_results, bing_api_key)
        source = "Bing"
    else:
        results = _duckduckgo_search(query, num_results)
        source = "DuckDuckGo"
    
    if not results:
        return "No search results found."
    
    formatted = f"Search Results with Content (via {source}):\n\n"
    
    for i, result in enumerate(results, 1):
        title = result.get('title', 'No title')
        url = result.get('url', '')
        snippet = result.get('snippet', 'No description available')
        
        # Extract content from the page
        content = _extract_page_content(url)
        
        formatted += f"{i}. **{title}**\n"
        formatted += f"   URL: {url}\n"
        formatted += f"   Summary: {snippet}\n"
        
        if content:
            formatted += f"   Content Preview: {content[:500]}...\n\n"
        else:
            formatted += f"   Content: Unable to extract content from this page.\n\n"
    
    return formatted.strip()


def _extract_page_content(url: str) -> str:
    """Extract readable content from a webpage"""
    try:
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = ' '.join(chunk for chunk in chunks if chunk)
        
        return clean_text
        
    except Exception as e:
        print(f"Content extraction failed for {url}: {e}")
        return ""


# OpenAI Function Calling Schema
def get_search_function_schema():
    """Returns the function schema for OpenAI function calling"""
    return {
        "name": "web_search",
        "description": "Search the web for current information on any topic",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of search results to return (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }


# Usage Examples
if __name__ == "__main__":
    # Example 1: Simple search with DuckDuckGo (free)
    print("=== DuckDuckGo Search ===")
    result = web_search("Python AI chatbots 2024", 3)
    print(result)
    
    print("\n" + "="*50 + "\n")
    
    # Example 2: Search with Bing API (if you have a key)
    # bing_key = "your_bing_api_key_here"
    # result = web_search("Vue.js dark theme", 3, bing_api_key=bing_key)
    # print(result)
    
    # Example 3: Enhanced search with content extraction
    print("=== Enhanced Search with Content ===")
    enhanced_result = web_search_with_content("AI development tools", 2)
    print(enhanced_result)


# Quick setup function for your chat app
def setup_search_tool(bing_api_key: Optional[str] = None):
    """
    Quick setup function that returns a configured search function
    
    Usage in your chat app:
    search_func = setup_search_tool(your_bing_key)  # or None for free version
    results = search_func("your query")
    """
    def search_function(query: str, num_results: int = 5) -> str:
        return web_search(query, num_results, bing_api_key)
    
    return search_function


TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for current public information.",
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
        "handler": web_search,
    }
]
