from __future__ import annotations
import json, re, requests
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 15

@dataclass
class LbMeta:
    title: Optional[str] = None
    year: Optional[int] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "year": self.year,
                "imdb_id": self.imdb_id, "tmdb_id": self.tmdb_id}

def _normalize_url(url: str) -> str:
    u = url.strip()
    if u.startswith("boxd.it/"): u = "https://" + u
    if u.startswith("letterboxd.com/"): u = "https://" + u
    return u

def _resolve_short(url: str) -> str:
    u = _normalize_url(url)
    if "boxd.it/" not in u: return u
    r = requests.get(u, headers={"User-Agent": UA}, allow_redirects=True, timeout=TIMEOUT)
    r.raise_for_status()
    return r.url

def _fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def _extract_jsonld(soup: BeautifulSoup) -> Optional[dict]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try: data = json.loads(tag.string or "")
        except Exception: continue
        items = data if isinstance(data, list) else [data]
        for obj in items:
            typ = obj.get("@type")
            if (isinstance(typ, list) and any(t.lower()=="movie" for t in typ if isinstance(t,str))) \
               or (isinstance(typ, str) and typ.lower()=="movie"):
                return obj
    return None

_IMDB_RX = re.compile(r"imdb\.com/title/(tt\d+)", re.I)
_TMDB_RX = re.compile(r"themoviedb\.org/movie/(\d+)", re.I)
_YEAR_RX = re.compile(r"\b(19\d{2}|20\d{2})\b")

def _pick_year(jsonld: Optional[dict], soup: BeautifulSoup) -> Optional[int]:
    if jsonld:
        d = jsonld.get("datePublished")
        m = _YEAR_RX.search(d or "")
        if m: return int(m.group(1))
        for ev in jsonld.get("releasedEvent") or []:
            m = _YEAR_RX.search((ev or {}).get("startDate") or "")
            if m: return int(m.group(1))
    meta = soup.find("meta", attrs={"property":"og:title"})
    if meta and meta.get("content"):
        m = _YEAR_RX.search(meta["content"])
        if m: return int(m.group(1))
    h1 = soup.find("h1")
    if h1:
        m = _YEAR_RX.search(h1.get_text(" ", strip=True))
        if m: return int(m.group(1))
    return None

def _pick_title(jsonld: Optional[dict], soup: BeautifulSoup) -> Optional[str]:
    if jsonld:
        name = (jsonld.get("name") or "").strip()
        if name: return name
    meta = soup.find("meta", attrs={"property":"og:title"})
    if meta and meta.get("content"):
        txt = meta["content"].split("–")[0].strip()
        if txt.endswith(")") and "(" in txt: txt = txt[:txt.rfind("(")].strip()
        if txt: return txt
    h1 = soup.find("h1")
    if h1:
        txt = h1.get_text(" ", strip=True)
        if txt.endswith(")") and "(" in txt: txt = txt[:txt.rfind("(")].strip()
        if txt: return txt
    return None

def _pick_ids(jsonld: Optional[dict], html: str) -> Tuple[Optional[str], Optional[str]]:
    imdb_id = tmdb_id = None
    if jsonld:
        same_as = jsonld.get("sameAs")
        urls = same_as if isinstance(same_as, list) else [same_as] if isinstance(same_as, str) else []
        for u in urls:
            if not imdb_id:
                m = _IMDB_RX.search(u or "")
                if m: imdb_id = m.group(1)
            if not tmdb_id:
                m = _TMDB_RX.search(u or "")
                if m: tmdb_id = m.group(1)
            if imdb_id and tmdb_id: break
    if not imdb_id:
        m = _IMDB_RX.search(html); imdb_id = m.group(1) if m else None
    if not tmdb_id:
        m = _TMDB_RX.search(html); tmdb_id = m.group(1) if m else None
    return imdb_id, tmdb_id

def parse(url: str) -> Dict[str, Any]:
    real = _resolve_short(url)
    html = _fetch(real)
    soup = BeautifulSoup(html, "html.parser")
    jsonld = _extract_jsonld(soup)
    meta = LbMeta()
    meta.title = _pick_title(jsonld, soup)
    meta.year = _pick_year(jsonld, soup)
    meta.imdb_id, meta.tmdb_id = _pick_ids(jsonld, html)
    return meta.to_dict()

def get_title_year(url: str) -> Tuple[Optional[str], Optional[int]]:
    d = parse(url); return d.get("title"), d.get("year")

def get_title(url: str) -> Optional[str]:
    return parse(url).get("title")
