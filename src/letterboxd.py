# src/letterboxd.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
TIMEOUT = 15


@dataclass
class LbMeta:
    title: Optional[str] = None
    year: Optional[int] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "year": self.year,
            "imdb_id": self.imdb_id,
            "tmdb_id": self.tmdb_id,
        }


def _normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("boxd.it/"):
        url = "https://" + url
    if url.startswith("letterboxd.com/"):
        url = "https://" + url
    return url


def _resolve_short(url: str) -> str:
    """
    boxd.it kısa linklerini gerçek film sayfasına çözer.
    Diğer URL'leri olduğu gibi döndürür.
    """
    url = _normalize_url(url)
    if "boxd.it/" not in url:
        return url
    # GET ile redirect'i takip et (HEAD bazı CDN'lerde engellenebiliyor)
    resp = requests.get(url, headers={"User-Agent": UA}, allow_redirects=True, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.url


def _fetch(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _extract_jsonld(soup: BeautifulSoup) -> Optional[dict]:
    """
    Letterboxd film sayfalarında Movie tipinde JSON-LD bulunur.
    """
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        # Bazı sayfalarda liste, bazılarında tek obje geliyor
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            typ = obj.get("@type")
            if isinstance(typ, list):
                is_movie = any(t.lower() == "movie" for t in typ if isinstance(t, str))
            else:
                is_movie = (isinstance(typ, str) and typ.lower() == "movie")
            if is_movie:
                return obj
    return None


_IMDB_RX = re.compile(r"imdb\.com/title/(tt\d+)", re.I)
_TMDB_RX = re.compile(r"themoviedb\.org/movie/(\d+)", re.I)
_YEAR_RX = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _pick_year(jsonld: Optional[dict], soup: BeautifulSoup) -> Optional[int]:
    # 1) JSON-LD: datePublished ya da releasedEvent.startDate
    if jsonld:
        date = jsonld.get("datePublished")
        if isinstance(date, str) and _YEAR_RX.search(date):
            return int(_YEAR_RX.search(date).group(1))
        released = jsonld.get("releasedEvent")
        if isinstance(released, list):
            for ev in released:
                sd = (ev or {}).get("startDate")
                if isinstance(sd, str) and _YEAR_RX.search(sd):
                    return int(_YEAR_RX.search(sd).group(1))
    # 2) Sayfadaki meta ve görünen yıl
    #   Örn: <meta property="og:title" content="Film Name (2024) – Letterboxd">
    meta_og = soup.find("meta", attrs={"property": "og:title"})
    if meta_og and meta_og.get("content"):
        m = _YEAR_RX.search(meta_og["content"])
        if m:
            return int(m.group(1))
    # 3) Başlık H1 vb.
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        m = _YEAR_RX.search(h1.get_text(" ", strip=True))
        if m:
            return int(m.group(1))
    return None


def _pick_title(jsonld: Optional[dict], soup: BeautifulSoup) -> Optional[str]:
    if jsonld:
        name = jsonld.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    meta_og = soup.find("meta", attrs={"property": "og:title"})
    if meta_og and meta_og.get("content"):
        # "Film Name (2024) – Letterboxd" tipini sadeleştir
        txt = meta_og["content"].split("–")[0].strip()
        if txt.endswith(")") and "(" in txt:
            txt = txt[: txt.rfind("(")].strip()
        if txt:
            return txt
    # H1 fallback
    h1 = soup.find("h1")
    if h1:
        txt = h1.get_text(" ", strip=True)
        if txt:
            # Sonundaki (YYYY) varsa at
            if txt.endswith(")") and "(" in txt:
                txt = txt[: txt.rfind("(")].strip()
            return txt
    return None


def _pick_ids(jsonld: Optional[dict], html: str) -> Tuple[Optional[str], Optional[str]]:
    imdb_id = None
    tmdb_id = None

    # JSON-LD sameAs alanında olabilir
    if jsonld:
        same_as = jsonld.get("sameAs")
        urls = []
        if isinstance(same_as, list):
            urls = [u for u in same_as if isinstance(u, str)]
        elif isinstance(same_as, str):
            urls = [same_as]
        for u in urls:
            if not imdb_id:
                m = _IMDB_RX.search(u)
                if m:
                    imdb_id = m.group(1)
            if not tmdb_id:
                m = _TMDB_RX.search(u)
                if m:
                    tmdb_id = m.group(1)
            if imdb_id and tmdb_id:
                break

    # HTML genel taraması (bazı sayfalarda sameAs yok)
    if not imdb_id:
        m = _IMDB_RX.search(html)
        if m:
            imdb_id = m.group(1)
    if not tmdb_id:
        m = _TMDB_RX.search(html)
        if m:
            tmdb_id = m.group(1)

    return imdb_id, tmdb_id


def parse(url: str) -> Dict[str, Any]:
    """
    Letterboxd linkinden meta çıkarır.
    Kısa link (boxd.it/...) verilebilir; otomatik çözer.
    Dönüş: {"title", "year", "imdb_id", "tmdb_id"}
    """
    try:
        real_url = _resolve_short(url)
    except Exception:
        # Çözülemezse verilen URL ile devam etmeyi dene
        real_url = _normalize_url(url)

    html = _fetch(real_url)
    soup = BeautifulSoup(html, "html.parser")
    jsonld = _extract_jsonld(soup)

    meta = LbMeta()
    meta.title = _pick_title(jsonld, soup)
    meta.year = _pick_year(jsonld, soup)
    meta.imdb_id, meta.tmdb_id = _pick_ids(jsonld, html)
    return meta.to_dict()


# Kullanışlı yardımcılar (main.py bazı yerlerde doğrudan kullanabilir)
def get_title_year(url: str) -> Tuple[Optional[str], Optional[int]]:
    d = parse(url)
    return d.get("title"), d.get("year")


def get_title(url: str) -> Optional[str]:
    d = parse(url)
    return d.get("title")
