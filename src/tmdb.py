# src/tmdb.py
import os, requests

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"

def _tmdb_get(path: str, params: dict | None = None):
    p = dict(params or {})
    p["api_key"] = TMDB_API_KEY
    r = requests.get(f"{TMDB_BASE}{path}", params=p, timeout=20)
    r.raise_for_status()
    return r.json()

def get_mubi_regions(tmdb_id: str | int) -> list[str]:
    """TMDb watch/providers -> sadece MUBI olan ülke kodları (ISO-3166-1 alpha-2)."""
    if not tmdb_id:
        return []
    try:
        data = _tmdb_get(f"/movie/{tmdb_id}/watch/providers")
    except requests.HTTPError:
        return []
    results = data.get("results", {})
    regions = set()
    for country_code, country_obj in results.items():
        # flatrate içinde MUBI var mı?
        for cat in ("flatrate", "rent", "buy", "ads", "free"):
            for it in country_obj.get(cat, []) or []:
                name = (it.get("provider_name") or "").strip()
                if name.upper() == "MUBI":
                    regions.add(country_code.upper())
                    break
            if country_code.upper() in regions:
                break
    return sorted(regions)
