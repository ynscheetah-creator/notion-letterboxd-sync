"""
Letterboxd film sayfalarından metadata çıkarır.
IMDb ID, TMDb ID, başlık ve yıl bilgisi için multiple fallback stratejisi kullanır.

Cloudflare bypass için cloudscraper kullanır.
"""
from __future__ import annotations
import json
import re
from typing import Dict, Any, Optional

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    import requests
    HAS_CLOUDSCRAPER = False
    print("[letterboxd] WARNING: cloudscraper not installed, using requests (may get 403)")

from bs4 import BeautifulSoup

# HTTP ayarları
TIMEOUT = 20

# Regex pattern'leri
IMDB_PATTERN = re.compile(r"(?:imdb\.com/title/|imdb\.to/)(tt\d{7,10})", re.IGNORECASE)
TMDB_PATTERN = re.compile(r"themoviedb\.org/movie/(\d+)", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")

# Global scraper instance (reuse for session cookies)
_scraper = None


def _get_scraper():
    """Cloudscraper instance döndürür (singleton pattern)."""
    global _scraper
    if _scraper is None:
        if HAS_CLOUDSCRAPER:
            _scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                },
                delay=5  # Cloudflare challenge için bekle
            )
        else:
            import requests
            _scraper = requests.Session()
            _scraper.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            })
    return _scraper


def parse(url: str) -> Dict[str, Any]:
    """
    Letterboxd URL'inden film metadata'sını parse eder.
    
    Args:
        url: Letterboxd film URL'i (boxd.it/xxx veya letterboxd.com/film/xxx)
    
    Returns:
        Dict[str, Any]: {
            "title": str | None,
            "year": int | None,
            "imdb_id": str | None,  # tt1234567 formatında
            "tmdb_id": str | None   # sayı olarak
        }
    """
    result = {
        "title": None,
        "year": None,
        "imdb_id": None,
        "tmdb_id": None,
    }
    
    scraper = _get_scraper()
    
    try:
        # 1. URL'i normalize et ve çöz
        resolved_url = _resolve_url(url, scraper)
        print(f"[letterboxd] Fetching: {resolved_url}")
        
        # 2. Sayfayı indir
        response = scraper.get(resolved_url, timeout=TIMEOUT)
        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        
        # 3. JSON-LD'den parse et (en güvenilir)
        jsonld = _extract_jsonld(soup)
        if jsonld:
            result = _parse_jsonld(jsonld, result)
        
        # 4. OpenGraph meta tags'den parse et (fallback)
        result = _parse_meta_tags(soup, result)
        
        # 5. Sayfadaki tüm linklerden ID'leri bul
        result = _find_ids_in_page(soup, html, result)
        
        # 6. Sonuçları logla
        _log_result(result)
        
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg:
            print(f"[letterboxd] HTTP error: 403 Forbidden - Cloudflare block. Try installing cloudscraper: pip install cloudscraper")
        else:
            print(f"[letterboxd] Error: {e}")
    
    return result


def _resolve_url(url: str, scraper) -> str:
    """
    boxd.it kısa linklerini tam URL'e çevirir.
    
    Args:
        url: Ham URL (boxd.it/xxx veya letterboxd.com/film/xxx)
        scraper: HTTP client instance
    
    Returns:
        str: Çözülmüş tam URL
    """
    url = url.strip()
    
    # https:// ekle
    if not url.startswith(("http://", "https://")):
        if url.startswith(("boxd.it/", "letterboxd.com/")):
            url = "https://" + url
        else:
            url = "https://" + url
    
    # boxd.it kısa linklerini takip et
    if "boxd.it/" in url:
        try:
            response = scraper.get(url, allow_redirects=True, timeout=TIMEOUT)
            return response.url
        except Exception as e:
            print(f"[letterboxd] Failed to resolve short URL: {e}")
    
    return url


def _extract_jsonld(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """
    Sayfadaki JSON-LD script tag'ini bulur ve Movie type'ını döndürür.
    
    Args:
        soup: BeautifulSoup nesnesi
    
    Returns:
        Optional[Dict]: Movie type JSON-LD objesi veya None
    """
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string or "{}")
            
            # Liste veya tek obje olabilir
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                item_type = item.get("@type", "")
                
                # @type "Movie" veya ["Movie", "Thing"] olabilir
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
    """
    JSON-LD objesinden metadata çıkarır.
    
    Args:
        jsonld: JSON-LD Movie objesi
        result: Mevcut sonuç dict'i
    
    Returns:
        Dict: Güncellenmiş sonuç
    """
    # Title
    if not result["title"]:
        title = jsonld.get("name")
        if isinstance(title, str):
            result["title"] = title.strip()
    
    # Year (datePublished'dan)
    if not result["year"]:
        date_published = jsonld.get("datePublished", "")
        if date_published:
            match = YEAR_PATTERN.search(str(date_published))
            if match:
                result["year"] = int(match.group(1))
    
    # IMDb ve TMDb ID'leri (sameAs array'inden)
    same_as = jsonld.get("sameAs", [])
    
    # Tek string olabilir veya list
    if isinstance(same_as, str):
        same_as = [same_as]
    elif not isinstance(same_as, list):
        same_as = []
    
    for url in same_as:
        if not url:
            continue
        
        # IMDb ID
        if not result["imdb_id"]:
            match = IMDB_PATTERN.search(str(url))
            if match:
                result["imdb_id"] = match.group(1)
        
        # TMDb ID
        if not result["tmdb_id"]:
            match = TMDB_PATTERN.search(str(url))
            if match:
                result["tmdb_id"] = match.group(1)
    
    return result


def _parse_meta_tags(soup: BeautifulSoup, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    OpenGraph meta tags'den bilgi çıkarır (fallback).
    
    Args:
        soup: BeautifulSoup nesnesi
        result: Mevcut sonuç dict'i
    
    Returns:
        Dict: Güncellenmiş sonuç
    """
    og_title_tag = soup.find("meta", property="og:title")
    
    if og_title_tag and og_title_tag.get("content"):
        content = og_title_tag["content"]
        
        # Title (eğer hala yoksa)
        if not result["title"]:
            # "Title (Year) — Letterboxd" formatından temizle
            title = content.split("—")[0].split(" - ")[0].strip()
            
            # Parantez içindeki yılı kaldır
            if "(" in title and title.endswith(")"):
                title = title[:title.rfind("(")].strip()
            
            result["title"] = title
        
        # Year (eğer hala yoksa)
        if not result["year"]:
            match = YEAR_PATTERN.search(content)
            if match:
                result["year"] = int(match.group(1))
    
    return result


def _find_ids_in_page(
    soup: BeautifulSoup,
    html: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Sayfa içindeki tüm linklerden ve raw HTML'den ID'leri arar.
    
    Args:
        soup: BeautifulSoup nesnesi
        html: Raw HTML string
        result: Mevcut sonuç dict'i
    
    Returns:
        Dict: Güncellenmiş sonuç
    """
    # Tüm link tag'lerini tara
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        
        # IMDb ID
        if not result["imdb_id"]:
            match = IMDB_PATTERN.search(href)
            if match:
                result["imdb_id"] = match.group(1)
        
        # TMDb ID
        if not result["tmdb_id"]:
            match = TMDB_PATTERN.search(href)
            if match:
                result["tmdb_id"] = match.group(1)
    
    # Raw HTML'de regex ara (bazen JavaScript içinde gömülü olur)
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
    """Debug için sonuçları loglar."""
    print(
        f"[letterboxd] Parsed → "
        f"title={result['title']}, "
        f"year={result['year']}, "
        f"imdb_id={result['imdb_id']}, "
        f"tmdb_id={result['tmdb_id']}"
    )
