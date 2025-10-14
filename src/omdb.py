from __future__ import annotations
from typing import Dict, Any, Optional
import requests

from .config import OMDB_API_KEY

BASE = "https://www.omdbapi.com/"

def _get(params: Dict[str, Any]) -> Dict[str, Any]:
    p = {"apikey": OMDB_API_KEY}
    p.update(params)
    r = requests.get(BASE, params=p, timeout=20)
    r.raise_for_status()
    return r.json()

def get_by_imdb(imdb_id: str) -> Dict[str, Any]:
    if not imdb_id:
        return {}
    d = _get({"i": imdb_id, "plot": "short", "r": "json"})
    if d.get("Response") != "True":
        return {}
    return {
        "year": int(d.get("Year", "0")[:4]) if d.get("Year") else None,
        "runtime": int(d.get("Runtime", "0").split()[0]) if d.get("Runtime") else None,
        "director": d.get("Director"),
        "writer": d.get("Writer"),
        "cinematography": None,
        "poster": d.get("Poster") if (d.get("Poster") and d.get("Poster") != "N/A") else None,
        "original_title": d.get("Title"),
        "synopsis": d.get("Plot") if d.get("Plot") != "N/A" else None,
        "countries": d.get("Country"),
        "languages": d.get("Language"),
        "cast_top": d.get("Actors"),
    }

def get_by_title(title: str, year: Optional[int] = None) -> Dict[str, Any]:
    if not title:
        return {}
    params = {"t": title, "plot": "short", "r": "json"}
    if year:
        params["y"] = year
    d = _get(params)
    if d.get("Response") != "True":
        return {}
    return get_by_imdb(d.get("imdbID"))
