#!/usr/bin/env python3
"""
web_tools.py - Reliable web access for AI entities

Provides multiple methods to fetch news and web content with fallbacks.
Designed to work around common issues: paywalls, JavaScript requirements,
rate limits, and unreliable search APIs.

Usage:
    from web_tools import WebTools
    web = WebTools()
    
    # Get news headlines
    news = web.get_news()
    
    # Search for specific topics
    results = web.search("iran protests 2026")
    
    # Fetch a specific page
    content = web.fetch("https://example.com")

Command line:
    python3 web_tools.py news
    python3 web_tools.py search "iran protests"
    python3 web_tools.py fetch "https://example.com"
"""

import subprocess
import json
import re
import sys
import html
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import quote, urlparse
import xml.etree.ElementTree as ET


class WebTools:
    """Multi-source web access with intelligent fallbacks."""
    
    # Text-only news sources (most reliable)
    TEXT_NEWS_SOURCES = [
        ("NPR Text", "https://text.npr.org"),
        ("CNN Lite", "https://lite.cnn.com"),
    ]
    
    # RSS feeds for real-time news
    RSS_FEEDS = {
        "google_news": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
        "google_world": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en",
        "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "bbc_tech": "http://feeds.bbci.co.uk/news/technology/rss.xml",
        "reuters_world": "https://www.rssboard.org/files/sample-rss-2.xml",  # Backup
        "hn_front": "https://hnrss.org/frontpage",
        "hn_best": "https://hnrss.org/best",
    }
    
    # Search endpoints
    SEARCH_ENDPOINTS = {
        "ddg_html": "https://html.duckduckgo.com/html/?q=",
        "ddg_lite": "https://lite.duckduckgo.com/lite/?q=",
        "google_news_search": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    }
    
    def __init__(self, timeout: int = 30, verbose: bool = False):
        self.timeout = timeout
        self.verbose = verbose
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[WebTools] {msg}", file=sys.stderr)
    
    def _curl(self, url: str, follow_redirects: bool = True) -> Optional[str]:
        """Execute curl with proper headers and error handling."""
        cmd = [
            "curl", "-s",
            "-m", str(self.timeout),
            "-A", "Mozilla/5.0 (compatible; NewsBot/1.0)",
            "--compressed",
        ]
        if follow_redirects:
            cmd.append("-L")
        cmd.append(url)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + 5)
            if result.returncode == 0 and result.stdout:
                return result.stdout
            self._log(f"curl failed for {url}: {result.stderr}")
        except subprocess.TimeoutExpired:
            self._log(f"timeout for {url}")
        except Exception as e:
            self._log(f"error fetching {url}: {e}")
        return None
    
    def _parse_rss(self, xml_content: str) -> List[Dict[str, str]]:
        """Parse RSS/Atom feed into list of items."""
        items = []
        try:
            root = ET.fromstring(xml_content)
            # Handle RSS 2.0
            for item in root.findall('.//item'):
                entry = {}
                title = item.find('title')
                link = item.find('link')
                desc = item.find('description')
                pub_date = item.find('pubDate')
                if title is not None and title.text:
                    entry['title'] = html.unescape(title.text.strip())
                if link is not None and link.text:
                    entry['link'] = link.text.strip()
                if desc is not None and desc.text:
                    # Clean HTML from description
                    clean_desc = re.sub(r'<[^>]+>', '', desc.text)
                    entry['description'] = html.unescape(clean_desc.strip())[:500]
                if pub_date is not None and pub_date.text:
                    entry['date'] = pub_date.text.strip()
                if entry.get('title'):
                    items.append(entry)
            # Handle Atom feeds
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('.//atom:entry', ns):
                item = {}
                title = entry.find('atom:title', ns)
                link = entry.find('atom:link', ns)
                summary = entry.find('atom:summary', ns)
                if title is not None and title.text:
                    item['title'] = html.unescape(title.text.strip())
                if link is not None:
                    item['link'] = link.get('href', '')
                if summary is not None and summary.text:
                    item['description'] = html.unescape(summary.text.strip())[:500]
                if item.get('title'):
                    items.append(item)
        except ET.ParseError as e:
            self._log(f"RSS parse error: {e}")
        return items
    
    def _extract_text_links(self, html_content: str, base_url: str = "") -> List[Dict[str, str]]:
        """Extract links and text from HTML."""
        results = []
        # Find all links with text
        link_pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>'
        for match in re.finditer(link_pattern, html_content, re.IGNORECASE):
            href, text = match.groups()
            text = html.unescape(text.strip())
            if len(text) > 10 and not text.startswith('http'):  # Filter noise
                if href.startswith('/') and base_url:
                    href = base_url.rstrip('/') + href
                results.append({'title': text, 'link': href})
        return results
    
    def _clean_html(self, html_content: str) -> str:
        """Remove HTML tags and clean up text."""
        # Remove script and style elements
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        # Unescape HTML entities
        text = html.unescape(text)
        return text.strip()
    
    # ==================== NEWS METHODS ====================
    
    def get_news(self, max_items: int = 20) -> Dict[str, Any]:
        """
        Get current news from multiple sources.
        Returns structured data with headlines from various sources.
        """
        result = {
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'sources': {},
            'top_stories': []
        }
        # Try Google News RSS first (most comprehensive)
        self._log("Fetching Google News RSS...")
        content = self._curl(self.RSS_FEEDS['google_news'])
        if content:
            items = self._parse_rss(content)[:max_items]
            if items:
                result['sources']['google_news'] = items
                result['top_stories'].extend(items[:10])
        # Try BBC World
        self._log("Fetching BBC World RSS...")
        content = self._curl(self.RSS_FEEDS['bbc_world'])
        if content:
            items = self._parse_rss(content)[:max_items]
            if items:
                result['sources']['bbc_world'] = items
                # Add unique stories
                existing_titles = {s['title'].lower()[:50] for s in result['top_stories']}
                for item in items[:5]:
                    if item['title'].lower()[:50] not in existing_titles:
                        result['top_stories'].append(item)
        # Try NPR Text (very reliable, no JS)
        self._log("Fetching NPR Text...")
        content = self._curl(self.TEXT_NEWS_SOURCES[0][1])
        if content:
            links = self._extract_text_links(content, "https://text.npr.org")
            # Filter to actual news stories
            news_links = [l for l in links if '/story/' in l.get('link', '') or '/news/' in l.get('link', '')]
            if news_links:
                result['sources']['npr_text'] = news_links[:max_items]
        # Try Hacker News
        self._log("Fetching Hacker News RSS...")
        content = self._curl(self.RSS_FEEDS['hn_front'])
        if content:
            items = self._parse_rss(content)[:10]
            if items:
                result['sources']['hacker_news'] = items
        return result
    
    def get_news_text(self, max_items: int = 15) -> str:
        """Get news as formatted text for easy reading."""
        news = self.get_news(max_items)
        lines = []
        lines.append(f"=== NEWS UPDATE ===")
        lines.append(f"Retrieved: {news['timestamp']}")
        lines.append("")
        if news['top_stories']:
            lines.append("TOP STORIES:")
            lines.append("-" * 40)
            for i, story in enumerate(news['top_stories'][:max_items], 1):
                lines.append(f"{i}. {story['title']}")
                if story.get('description'):
                    desc = story['description'][:200]
                    if len(story['description']) > 200:
                        desc += "..."
                    lines.append(f"   {desc}")
                if story.get('link'):
                    lines.append(f"   Link: {story['link']}")
                lines.append("")
        for source, items in news['sources'].items():
            if source not in ['google_news'] and items:  # Skip duplicates
                lines.append(f"\n--- {source.upper().replace('_', ' ')} ---")
                for item in items[:5]:
                    lines.append(f"• {item['title']}")
        return '\n'.join(lines)
    
    # ==================== SEARCH METHODS ====================
    
    def search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        Search for information across multiple sources.
        Uses news search and DuckDuckGo as fallbacks.
        """
        result = {
            'query': query,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'results': []
        }
        encoded_query = quote(query)
        # Try Google News search RSS
        self._log(f"Searching Google News for: {query}")
        url = self.SEARCH_ENDPOINTS['google_news_search'].format(query=encoded_query)
        content = self._curl(url)
        if content:
            items = self._parse_rss(content)[:max_results]
            for item in items:
                item['source'] = 'google_news'
                result['results'].append(item)
        # Try DuckDuckGo HTML
        if len(result['results']) < max_results:
            self._log(f"Searching DuckDuckGo for: {query}")
            url = self.SEARCH_ENDPOINTS['ddg_html'] + encoded_query
            content = self._curl(url)
            if content:
                # Extract result links from DDG HTML
                # Pattern for DDG result links
                ddg_pattern = r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
                for match in re.finditer(ddg_pattern, content):
                    href, title = match.groups()
                    # DDG uses redirect URLs, extract actual URL
                    actual_url_match = re.search(r'uddg=([^&]+)', href)
                    if actual_url_match:
                        from urllib.parse import unquote
                        actual_url = unquote(actual_url_match.group(1))
                        result['results'].append({
                            'title': html.unescape(title.strip()),
                            'link': actual_url,
                            'source': 'duckduckgo'
                        })
                        if len(result['results']) >= max_results:
                            break
        return result
    
    def search_text(self, query: str, max_results: int = 10) -> str:
        """Search and return formatted text results."""
        results = self.search(query, max_results)
        lines = []
        lines.append(f"=== SEARCH: {query} ===")
        lines.append(f"Retrieved: {results['timestamp']}")
        lines.append("")
        if results['results']:
            for i, r in enumerate(results['results'], 1):
                lines.append(f"{i}. {r['title']}")
                if r.get('description'):
                    lines.append(f"   {r['description'][:200]}")
                if r.get('link'):
                    lines.append(f"   {r['link']}")
                lines.append("")
        else:
            lines.append("No results found.")
        return '\n'.join(lines)
    
    # ==================== FETCH METHODS ====================
    
    def _extract_article_content(self, html_content: str) -> str:
        """Extract main article content using common patterns."""
        # Try to find article/main content areas
        patterns = [
            # Article body patterns
            (r'<article[^>]*>(.*?)</article>', re.DOTALL | re.IGNORECASE),
            (r'<div[^>]+class="[^"]*article[^"]*"[^>]*>(.*?)</div>\s*(?:</div>|<div[^>]+class="[^"]*(?:footer|sidebar|comment))', re.DOTALL | re.IGNORECASE),
            (r'<div[^>]+class="[^"]*content[^"]*"[^>]*>(.*?)</div>\s*(?:</div>|<footer)', re.DOTALL | re.IGNORECASE),
            (r'<main[^>]*>(.*?)</main>', re.DOTALL | re.IGNORECASE),
            # GitHub issue body
            (r'<div[^>]+class="[^"]*markdown-body[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
            (r'class="[^"]*issue-body[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
            # Generic post/entry
            (r'<div[^>]+class="[^"]*post-content[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
            (r'<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
        ]
        for pattern, flags in patterns:
            match = re.search(pattern, html_content, flags)
            if match:
                extracted = match.group(1)
                cleaned = self._clean_html(extracted)
                if len(cleaned) > 200:  # Only use if substantial
                    return cleaned
        return ""
    
    def _try_reader_apis(self, url: str) -> Optional[str]:
        """Try various reader/text extraction APIs."""
        encoded_url = quote(url, safe='')
        # Try 12ft.io (paywall bypass)
        twelve_ft = f"https://12ft.io/{url}"
        content = self._curl(twelve_ft)
        if content and len(self._clean_html(content)) > 1000:
            self._log("12ft.io succeeded")
            extracted = self._extract_article_content(content)
            if extracted:
                return extracted
            return self._clean_html(content)
        # Try Webcache (Google cache)
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        content = self._curl(cache_url)
        if content and 'sorry' not in content.lower()[:500]:
            self._log("Google cache succeeded")
            extracted = self._extract_article_content(content)
            if extracted:
                return extracted
        return None
    
    def _try_archive(self, url: str) -> Optional[str]:
        """Try to fetch from web archives."""
        encoded_url = quote(url, safe='')
        # Try Wayback Machine (most recent snapshot)
        wayback_api = f"https://archive.org/wayback/available?url={encoded_url}"
        api_response = self._curl(wayback_api)
        if api_response:
            try:
                data = json.loads(api_response)
                if data.get('archived_snapshots', {}).get('closest', {}).get('available'):
                    archive_url = data['archived_snapshots']['closest']['url']
                    self._log(f"Found archive: {archive_url}")
                    content = self._curl(archive_url)
                    if content:
                        extracted = self._extract_article_content(content)
                        if extracted:
                            return extracted
                        return self._clean_html(content)
            except json.JSONDecodeError:
                pass
        return None
    
    def fetch(self, url: str, try_alternatives: bool = True) -> Dict[str, Any]:
        """
        Fetch a web page with intelligent content extraction.
        Tries multiple methods: direct fetch, article extraction, reader APIs, archives.
        Auto-detects GitHub URLs and uses API instead.
        """
        # Auto-detect GitHub issues/PRs and use API
        if re.match(r'https?://github\.com/[^/]+/[^/]+/(issues|pull)/\d+', url):
            gh_result = self.fetch_github_issue(url)
            if gh_result['success']:
                return {
                    'url': url,
                    'timestamp': gh_result['timestamp'],
                    'success': True,
                    'content': f"Title: {gh_result['title']}\nState: {gh_result['state']}\nAuthor: {gh_result['author']}\nLabels: {', '.join(gh_result['labels'])}\n\n{gh_result['body']}",
                    'title': gh_result['title'],
                    'method': 'github_api',
                    'raw_length': 0
                }
        result = {
            'url': url,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'success': False,
            'content': '',
            'title': '',
            'method': '',
            'raw_length': 0
        }
        # Direct fetch first
        self._log(f"Fetching: {url}")
        raw_content = self._curl(url)
        if not raw_content:
            result['method'] = 'failed'
            return result
        result['raw_length'] = len(raw_content)
        result['success'] = True
        # Extract title
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', raw_content, re.IGNORECASE)
        if title_match:
            result['title'] = html.unescape(title_match.group(1).strip())
        # Try article extraction first (best for actual content)
        extracted = self._extract_article_content(raw_content)
        if extracted and len(extracted) > 300:
            result['content'] = extracted
            result['method'] = 'article_extraction'
            return result
        # Fall back to full clean
        cleaned = self._clean_html(raw_content)
        # Check if content is too short (likely JS-dependent)
        is_js_dependent = (
            len(cleaned) < 500 or
            'enable javascript' in raw_content.lower() or
            'javascript is required' in raw_content.lower() or
            '<noscript>' in raw_content.lower() and len(cleaned) < 1000
        )
        if is_js_dependent and try_alternatives:
            self._log("Content appears JS-dependent, trying alternatives...")
            # Try reader APIs
            reader_content = self._try_reader_apis(url)
            if reader_content and len(reader_content) > len(cleaned):
                result['content'] = reader_content
                result['method'] = 'reader_api'
                return result
            # Try archive
            archive_content = self._try_archive(url)
            if archive_content and len(archive_content) > len(cleaned):
                result['content'] = archive_content
                result['method'] = 'archive'
                return result
        # Use cleaned content as last resort
        result['content'] = cleaned
        result['method'] = 'direct_clean'
        return result
    
    def fetch_text(self, url: str) -> str:
        """Fetch URL and return clean text content."""
        result = self.fetch(url)
        lines = []
        lines.append(f"=== {result.get('title', 'Page')} ===")
        lines.append(f"URL: {url}")
        lines.append(f"Fetched: {result['timestamp']}")
        lines.append("")
        if result['success']:
            content = result['content'][:10000]  # Limit output
            if len(result['content']) > 10000:
                content += "\n\n[Content truncated...]"
            lines.append(content)
        else:
            lines.append("Failed to fetch content.")
        return '\n'.join(lines)
    
    # ==================== TOPIC-SPECIFIC METHODS ====================
    
    def get_topic_news(self, topic: str, max_items: int = 10) -> Dict[str, Any]:
        """Get news about a specific topic."""
        return self.search(topic, max_items)
    
    def get_tech_news(self, max_items: int = 10) -> Dict[str, Any]:
        """Get technology news from reliable sources."""
        result = {
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'sources': {}
        }
        # BBC Tech RSS
        content = self._curl(self.RSS_FEEDS['bbc_tech'])
        if content:
            result['sources']['bbc_tech'] = self._parse_rss(content)[:max_items]
        # Hacker News
        content = self._curl(self.RSS_FEEDS['hn_best'])
        if content:
            result['sources']['hacker_news'] = self._parse_rss(content)[:max_items]
        return result
    
    def get_ai_news(self, max_items: int = 10) -> Dict[str, Any]:
        """Get AI-specific news."""
        return self.search("artificial intelligence AI news", max_items)
    
    # ==================== GITHUB-SPECIFIC METHODS ====================
    
    def fetch_github_issue(self, url: str) -> Dict[str, Any]:
        """
        Fetch GitHub issue/PR content using the API.
        Works better than HTML scraping for GitHub.
        """
        result = {
            'url': url,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'success': False,
            'title': '',
            'body': '',
            'state': '',
            'author': '',
            'comments': [],
            'labels': []
        }
        # Parse GitHub URL: /owner/repo/issues/number or /owner/repo/pull/number
        match = re.match(r'https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)', url)
        if not match:
            result['error'] = 'Not a valid GitHub issue/PR URL'
            return result
        owner, repo, issue_type, number = match.groups()
        # Use GitHub API (no auth needed for public repos)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
        self._log(f"Fetching GitHub API: {api_url}")
        content = self._curl(api_url)
        if not content:
            result['error'] = 'Failed to fetch from GitHub API'
            return result
        try:
            data = json.loads(content)
            result['success'] = True
            result['title'] = data.get('title', '')
            result['body'] = data.get('body', '') or ''
            result['state'] = data.get('state', '')
            result['author'] = data.get('user', {}).get('login', '')
            result['labels'] = [l.get('name', '') for l in data.get('labels', [])]
            result['created_at'] = data.get('created_at', '')
            result['comments_count'] = data.get('comments', 0)
            # Fetch comments if any
            if data.get('comments', 0) > 0:
                comments_url = f"{api_url}/comments"
                comments_content = self._curl(comments_url)
                if comments_content:
                    comments_data = json.loads(comments_content)
                    for c in comments_data[:10]:  # Limit to first 10
                        result['comments'].append({
                            'author': c.get('user', {}).get('login', ''),
                            'body': c.get('body', ''),
                            'created_at': c.get('created_at', '')
                        })
        except json.JSONDecodeError as e:
            result['error'] = f'JSON parse error: {e}'
        return result
    
    def fetch_github_issue_text(self, url: str) -> str:
        """Fetch GitHub issue and return as formatted text."""
        result = self.fetch_github_issue(url)
        lines = []
        if result['success']:
            lines.append(f"=== {result['title']} ===")
            lines.append(f"State: {result['state']} | Author: {result['author']}")
            lines.append(f"Labels: {', '.join(result['labels']) if result['labels'] else 'none'}")
            lines.append(f"URL: {result['url']}")
            lines.append("")
            lines.append("--- Issue Body ---")
            lines.append(result['body'] or '(empty)')
            if result['comments']:
                lines.append("")
                lines.append(f"--- Comments ({result['comments_count']} total) ---")
                for c in result['comments']:
                    lines.append(f"\n@{c['author']} ({c['created_at'][:10]}):")
                    lines.append(c['body'][:1000])
        else:
            lines.append(f"Failed to fetch: {result.get('error', 'unknown error')}")
            lines.append(f"URL: {url}")
        return '\n'.join(lines)
    
    def fetch_github_repo(self, url: str) -> Dict[str, Any]:
        """Fetch GitHub repo info and README."""
        result = {
            'url': url,
            'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'success': False
        }
        # Parse repo URL
        match = re.match(r'https?://github\.com/([^/]+)/([^/]+)/?$', url.rstrip('/'))
        if not match:
            result['error'] = 'Not a valid GitHub repo URL'
            return result
        owner, repo = match.groups()
        # Fetch repo info
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        content = self._curl(api_url)
        if content:
            try:
                data = json.loads(content)
                result['success'] = True
                result['name'] = data.get('name', '')
                result['description'] = data.get('description', '')
                result['stars'] = data.get('stargazers_count', 0)
                result['forks'] = data.get('forks_count', 0)
                result['language'] = data.get('language', '')
                result['topics'] = data.get('topics', [])
            except json.JSONDecodeError:
                pass
        # Fetch README
        readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        readme_content = self._curl(readme_url)
        if readme_content:
            try:
                readme_data = json.loads(readme_content)
                if readme_data.get('content'):
                    import base64
                    result['readme'] = base64.b64decode(readme_data['content']).decode('utf-8', errors='replace')
            except (json.JSONDecodeError, Exception):
                pass
        return result


# ==================== CONVENIENCE FUNCTIONS ====================

def news(max_items: int = 15, verbose: bool = False) -> str:
    """Quick function to get news."""
    web = WebTools(verbose=verbose)
    return web.get_news_text(max_items)

def search(query: str, max_results: int = 10, verbose: bool = False) -> str:
    """Quick function to search."""
    web = WebTools(verbose=verbose)
    return web.search_text(query, max_results)

def fetch(url: str, verbose: bool = False) -> str:
    """Quick function to fetch a URL."""
    web = WebTools(verbose=verbose)
    return web.fetch_text(url)


# ==================== COMMAND LINE INTERFACE ====================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage:")
        print("  python3 web_tools.py news [max_items]")
        print("  python3 web_tools.py search <query>")
        print("  python3 web_tools.py fetch <url>")
        print("  python3 web_tools.py tech")
        print("  python3 web_tools.py ai")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    verbose = '-v' in sys.argv or '--verbose' in sys.argv
    web = WebTools(verbose=verbose)
    if cmd == 'news':
        max_items = 15
        if len(sys.argv) > 2 and sys.argv[2].isdigit():
            max_items = int(sys.argv[2])
        print(web.get_news_text(max_items))
    elif cmd == 'search':
        if len(sys.argv) < 3:
            print("Usage: python3 web_tools.py search <query>")
            sys.exit(1)
        query = ' '.join([a for a in sys.argv[2:] if not a.startswith('-')])
        print(web.search_text(query))
    elif cmd == 'fetch':
        if len(sys.argv) < 3:
            print("Usage: python3 web_tools.py fetch <url>")
            sys.exit(1)
        url = sys.argv[2]
        print(web.fetch_text(url))
    elif cmd == 'tech':
        result = web.get_tech_news()
        print(f"=== TECH NEWS ===")
        print(f"Retrieved: {result['timestamp']}")
        for source, items in result['sources'].items():
            print(f"\n--- {source.upper()} ---")
            for item in items[:10]:
                print(f"• {item['title']}")
                if item.get('link'):
                    print(f"  {item['link']}")
    elif cmd == 'ai':
        print(web.search_text("AI artificial intelligence news"))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == '__main__':
    main()
