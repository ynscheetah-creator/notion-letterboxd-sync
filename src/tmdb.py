from __future__ import annotations
from typing import Dict, Any, Optional, List
import requests

from .config import TMDB_API_KEY

BASE = "https://api.themoviedb.org/3"
HEAD = {"Accept": "application/json"}

def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not TMDB_API_KEY:
        return {}
    p = {"api_key": TMDB_API_KEY}
    if params:
        p.update(params)
    try:
        r = requests.get(url, params=p, headers=HEAD, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[warn] TMDb API error: {e}")
        return {}

def fetch_movie(tmdb_id: str) -> Dict[str, Any]:
    """Ana fonksiyon - main.py'den çağrılır"""
    if not tmdb_id:
        return {}
    
    # Film bilgilerini al
    d = _get(f"{BASE}/movie/{tmdb_id}")
    if not d:
        return {}
    
    # Credits (yönetmen, senarist, görüntü yönetmeni)
    credits = _get(f"{BASE}/movie/{tmdb_id}/credits")
    
    directors = []
    writers = []
    cinematography = []
    cast_top = []
    
    if credits:
        crew = credits.get("crew", [])
        for person in crew:
            job = person.get("job", "")
            name = person.get("name", "")
            if name:
                if job == "Director":
                    directors.append(name)
                elif job in ["Writer", "Screenplay", "Story"]:
                    if name not in writers:
                        writers.append(name)
                elif job == "Director of Photography":
                    cinematography.append(name)
        
        # İlk 3 oyuncu
        cast = credits.get("cast", [])[:3]
        cast_top = [person.get("name", "") for person in cast if person.get("name")]
    
    # Diller ve ülkeler
    languages = [lang.get("english_name", "") for lang in d.get("spoken_languages", [])]
    countries = [c.get("name", "") for c in d.get("production_countries", [])]
    
    out: Dict[str, Any] = {}
    out["year"] = int(d.get("release_date", "")[:4]) if d.get("release_date") else None
    out["runtime"] = d.get("runtime")
    out["original_title"] = d.get("original_title")
    out["synopsis"] = d.get("overview")
    out["poster_url"] = f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}" if d.get("poster_path") else None
    out["backdrop_url"] = f"https://image.tmdb.org/t/p/w1280{d.get('backdrop_path')}" if d.get("backdrop_path") else None
    out["directors"] = directors
    out["writers"] = writers
    out["cinematography"] = cinematography
    out["cast_top"] = cast_top
    out["languages"] = languages
    out["production_countries"] = countries
    
    return out

def fetch_by_title(title: str, year: Optional[int] = None) -> Dict[str, Any]:
    """Başlığa göre arama"""
    if not title:
        return {}
    q = {"query": title}
    if year:
        q["year"] = year
    s = _get(f"{BASE}/search/movie", q)
    r = (s.get("results") or [])
    if not r:
        return {}
    best = r[0]
    return fetch_movie(str(best.get("id")))

def get_providers_mubi(tmdb_id: str) -> List[str]:
    """
    TMDb watch/providers endpoint'inden MUBI'nin bulunduğu ülke kodlarını döndürür.
    """
    if not tmdb_id:
        return []
    d = _get(f"{BASE}/movie/{tmdb_id}/watch/providers")
    if not d:
        return []
    res = d.get("results", {})
    out: List[str] = []
    for cc, payload in res.items():
        fl = payload.get("flatrate") or []
        if any((it.get("provider_name") == "MUBI") for it in fl):
            out.append(cc)
    return sorted(out)

# Geriye uyumluluk için eski isimler
get_by_id = fetch_movie
get_by_title = fetch_by_title
