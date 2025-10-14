from __future__ import annotations
from typing import Dict, Any, Optional, List
import requests

from .config import TMDB_API_KEY

BASE = "https://api.themoviedb.org/3"
HEAD = {"Accept": "application/json"}

def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = {"api_key": TMDB_API_KEY}
    if params:
        p.update(params)
    r = requests.get(url, params=p, headers=HEAD, timeout=20)
    r.raise_for_status()
    return r.json()

def get_by_id(tmdb_id: str) -> Dict[str, Any]:
    d = _get(f"{BASE}/movie/{tmdb_id}")
    out: Dict[str, Any] = {}
    out["year"] = (d.get("release_date", "")[:4] or None)
    out["runtime"] = d.get("runtime")
    out["original_title"] = d.get("original_title")
    out["synopsis"] = d.get("overview")
    out["poster"] = f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}" if d.get("poster_path") else None
    out["backdrop"] = f"https://image.tmdb.org/t/p/w780{d.get('backdrop_path')}" if d.get("backdrop_path") else None
    # countries, languages, credits vs. burada istersen genişletebilirsin
    return out

def get_by_title(title: str, year: Optional[int] = None) -> Dict[str, Any]:
    q = {"query": title}
    if year:
        q["year"] = year
    s = _get(f"{BASE}/search/movie", q)
    r = (s.get("results") or [])
    if not r:
        return {}
    best = r[0]
    return get_by_id(str(best.get("id")))

def get_providers_mubi(tmdb_id: str) -> List[str]:
    """
    TMDb watch/providers endpoint’inden MUBI’nin bulunduğu ülke kodlarını (ISO 3166-1 alpha-2) döndürür.
    """
    if not tmdb_id:
        return []
    d = _get(f"{BASE}/movie/{tmdb_id}/watch/providers")
    res = d.get("results", {})
    out: List[str] = []
    for cc, payload in res.items():
        # flatrate listesinde provider_name == 'MUBI' olanları yakala
        fl = payload.get("flatrate") or []
        if any((it.get("provider_name") == "MUBI") for it in fl):
            out.append(cc)  # TMDb zaten ISO 3166-1 alpha-2 döndürüyor
    return sorted(out)
