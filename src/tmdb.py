from __future__ import annotations
import requests
from typing import Any
from .config import TMDB_API_KEY

_BASE = "https://api.themoviedb.org/3"

def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    p = {"api_key": TMDB_API_KEY}
    if params: p.update(params)
    r = requests.get(f"{_BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()

def mubi_regions_for_movie(tmdb_id: str | int) -> list[str]:
    """TMDb watch/providers -> MUBI'nin bulunduğu TÜM ülke kodları (ISO 3166-1 alpha-2)."""
    if not tmdb_id: return []
    data = _get(f"/movie/{tmdb_id}/watch/providers")
    res = data.get("results", {}) or {}
    regions: set[str] = set()
    for cc, payload in res.items():
        for grp in ("flatrate", "rent", "buy", "ads"):
            for prov in payload.get(grp) or []:
                if "mubi" in (prov.get("provider_name") or "").lower():
                    regions.add(cc)
                    break
    return sorted(regions)
