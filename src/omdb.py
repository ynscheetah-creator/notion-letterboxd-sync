from __future__ import annotations
from typing import Dict, Any, Optional
import requests

from .config import OMDB_API_KEY

BASE = "https://www.omdbapi.com/"

def _get(params: Dict[str, Any]) -> Dict[str, Any]:
    if not OMDB_API_KEY:
        return {}
    p = {"apikey": OMDB_API_KEY}
    p.update(params)
    try:
        r = requests.get(BASE, params=p, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[warn] OMDb API error: {e}")
        return {}

def fetch_by_imdb(imdb_id: str) -> Dict[str, Any]:
    """Ana fonksiyon - main.py'den çağrılır"""
    if not imdb_id:
        return {}
    d = _get({"i": imdb_id, "plot": "short", "r": "json"})
    if d.get("Response") != "True":
        return {}
    return {
        "Year": d.get("Year"),
        "Runtime": d.get("Runtime"),
        "Director": d.get("Director"),
        "Writer": d.get("Writer"),
        "Cinematography": None,  # OMDb'de yok genelde
        "Poster": d.get("Poster") if (d.get("Poster") and d.get("Poster") != "N/A") else None,
        "Title": d.get("Title"),
        "Plot": d.get("Plot") if d.get("Plot") != "N/A" else None,
        "Country": d.get("Country"),
        "Language": d.get("Language"),
        "Actors": d.get("Actors"),
    }

def fetch_by_title(title: str, year: Optional[int] = None) -> Dict[str, Any]:
    """Başlığa göre arama"""
    if not title:
        return {}
    params = {"t": title, "plot": "short", "r": "json"}
    if year:
        params["y"] = year
    d = _get(params)
    if d.get("Response") != "True":
        return {}
    return fetch_by_imdb(d.get("imdbID"))

# Geriye uyumluluk için eski isimler
get_by_imdb = fetch_by_imdb
get_by_title = fetch_by_title
