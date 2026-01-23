"""
Letterboxd film sayfalarından metadata çıkarır.
IMDb ID, TMDb ID, başlık ve yıl bilgisi için multiple fallback stratejisi kullanır.
"""
from __future__ import annotations
import json
import re
from typing import Dict, Any, Optional

try:
    import cloudscraper
    _scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
except ImportError:
    import requests
    _scraper = requests.Session()
    _scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

from bs4 import BeautifulSoup

TIMEOUT = 15

IMDB_PATTERN = re.compile(r"(?:imdb\.com/title/|imdb\.to/)(tt\d{7,10})", re.IGNORECASE)
TMDB_PATTERN = re.compile(r"themoviedb\.org/movie/(\d+)", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")


def parse(url: str) -> Dict[str, Any]:
    """
    Letterboxd URL'inden film metadata'sını parse eder.
    
    Args:
        url: Letterboxd film URL'i (boxd.it/xxx veya letterboxd.com/film/xxx)
    
    Returns:
        Dict[str, Any]: {
            "title": str | None,
            "year": int | None,
            "imdb_id": str | None,
            "tmdb_id": str | None,
            "resolved_url": str | None  # Çözülmüş tam URL
        }
    """
    result = {
        "title": None,
        "year": None,
        "imdb_id": None,
        "tmdb_id": None,
        "resolved_url": None,
    }
    
    try:
        resolved_url = _resolve_url(url)
        result["resolved_url"] = resolved_url
        print(f"[letterboxd] Fetching: {resolved_url}")
        
        response = _scraper.get(resolved_url, timeout=TIMEOUT)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        jsonld = _extract_jsonld(soup)
        if jsonld:
            result = _parse_jsonld(jsonld, result)
        
        result = _parse_meta_tags(soup, result)
        result = _find_ids_in_page(soup, html, result)
        
        _log_result(result)
        
    except Exception as e:
        print(f"[letterboxd] HTTP error: {e}")
        # 403 olsa bile resolved_url'i döndürmeye çalış
        if not result.get("resolved_url"):
            result["resolved_url"] = _resolve_url_safe(url)
    
    return result


def _resolve_url(url: str) -> str:
    url = url.strip()
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    if "boxd.it/" in url:
        try:
            response = _scraper.get(url, allow_redirects=True, timeout=TIMEOUT)
            return response.url
        except Exception as e:
            print(f"[letterboxd] Failed to resolve short URL: {e}")
    
    return url


def _resolve_url_safe(url: str) -> Optional[str]:
    """Sadece redirect'i çöz, hata olursa None dön"""
    url = url.strip()
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    if "boxd.it/" in url:
        try:
            response = _scraper.head(url, allow_redirects=True, timeout=10)
            return response.url
        except:
            pass
    
    return url if "letterboxd.com" in url else None


def _extract_jsonld(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string or "{}")
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                item_type = item.get("@type", "")
                is_movie = (
                    item_type == "Movie"
                    or (isinstance(item_type, list) and "Movie" in item_type)
                )
                if is_movie:
                    return item
        except (json.JSONDecodeError, AttributeError):
            continue
    return None


def _parse_jsonld(jsonld: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    if not result["title"]:
        title = jsonld.get("name")
        if isinstance(title, str):
            result["title"] = title.strip()
    
    if not result["year"]:
        date_published = jsonld.get("datePublished", "")
        if date_published:
            match = YEAR_PATTERN.search(str(date_published))
            if match:
                result["year"] = int(match.group(1))
    
    same_as = jsonld.get("sameAs", [])
    if isinstance(same_as, str):
        same_as = [same_as]
    elif not isinstance(same_as, list):
        same_as = []
    
    for link in same_as:
        if not link:
            continue
        if not result["imdb_id"]:
            match = IMDB_PATTERN.search(str(link))
            if match:
                result["imdb_id"] = match.group(1)
        if not result["tmdb_id"]:
            match = TMDB_PATTERN.search(str(link))
            if match:
                result["tmdb_id"] = match.group(1)
    
    # resolved_url'i koru
    return result


def _parse_meta_tags(soup: BeautifulSoup, result: Dict[str, Any]) -> Dict[str, Any]:
    og_title_tag = soup.find("meta", property="og:title")
    
    if og_title_tag and og_title_tag.get("content"):
        content = og_title_tag["content"]
        
        if not result["title"]:
            title = content.split("—")[0].split(" - ")[0].strip()
            if "(" in title and title.endswith(")"):
                title = title[:title.rfind("(")].strip()
            result["title"] = title
        
        if not result["year"]:
            match = YEAR_PATTERN.search(content)
            if match:
                result["year"] = int(match.group(1))
    
    return result


def _find_ids_in_page(soup: BeautifulSoup, html: str, result: Dict[str, Any]) -> Dict[str, Any]:
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not result["imdb_id"]:
            match = IMDB_PATTERN.search(href)
            if match:
                result["imdb_id"] = match.group(1)
        if not result["tmdb_id"]:
            match = TMDB_PATTERN.search(href)
            if match:
                result["tmdb_id"] = match.group(1)
    
    if not result["imdb_id"]:
        match = IMDB_PATTERN.search(html)
        if match:
            result["imdb_id"] = match.group(1)
    
    if not result["tmdb_id"]:
        match = TMDB_PATTERN.search(html)
        if match:
            result["tmdb_id"] = match.group(1)
    
    return result


def _log_result(result: Dict[str, Any]) -> None:
    print(
        f"[debug] Letterboxd meta: "
        f"title={result['title']}, "
        f"year={result['year']}, "
        f"imdb={result['imdb_id']}"
    )
