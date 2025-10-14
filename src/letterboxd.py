from __future__ import annotations
import json, re, requests
from dataclasses import dataclass
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 15

@dataclass
class LbMeta:
    title: Optional[str] = None
    year: Optional[int] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "year": self.year, "imdb_id": self.imdb_id, "tmdb_id": self.tmdb_id}

def _normalize(url: str) -> str:
    url = url.strip()
    if url.startswith("boxd.it/") or url.startswith("letterboxd.com/"):
        url = "https://" + url
    return url

def _resolve(url: str) -> str:
    url = _normalize(url)
    if "boxd.it/" not in url:
        return url
    r = requests.get(url, headers={"User-Agent": UA}, allow_redirects=True, timeout=TIMEOUT)
    r.raise_for_status()
    return r.url

IMDB_RX = re.compile(r"imdb\.com/title/(tt\d+)", re.I)
TMDB_RX = re.compile(r"themoviedb\.org/movie/(\d+)", re.I)
YEAR_RX = re.compile(r"\b(19\d{2}|20\d{2})\b")

def parse(url: str) -> Dict[str, Any]:
    real = _resolve(url)
    html = requests.get(real, headers={"User-Agent": UA}, timeout=TIMEOUT).text
    soup = BeautifulSoup(html, "html.parser")

    # JSON-LD
    jsonld = None
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for obj in items:
            t = obj.get("@type")
            is_movie = (t and (t == "Movie" or (isinstance(t, list) and any(tt == "Movie" for tt in t))))
            if is_movie:
                jsonld = obj
                break
        if jsonld:
            break

    meta = LbMeta()

    # title
    if jsonld and isinstance(jsonld.get("name"), str):
        meta.title = jsonld["name"].strip()
    else:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            txt = og["content"].split("–")[0]
            if txt.endswith(")") and "(" in txt:
                txt = txt[: txt.rfind("(")].strip()
            meta.title = txt.strip()

    # year
    if jsonld and isinstance(jsonld.get("datePublished"), str):
        m = YEAR_RX.search(jsonld["datePublished"])
        if m:
            meta.year = int(m.group(1))
    if not meta.year:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            m = YEAR_RX.search(og["content"])
            if m:
                meta.year = int(m.group(1))

    # ids
    same_as = jsonld.get("sameAs") if jsonld else None
    urls = same_as if isinstance(same_as, list) else ([same_as] if isinstance(same_as, str) else [])
    urls.append(real)
    for u in urls:
        if not meta.imdb_id:
            m = IMDB_RX.search(u or "")
            if m: meta.imdb_id = m.group(1)
        if not meta.tmdb_id:
            m = TMDB_RX.search(u or "")
            if m: meta.tmdb_id = m.group(1)

    return meta.to_dict()
