import requests
from .config import TMDB_API_KEY

TMDB_BASE = "https://api.themoviedb.org/3"

def _use_headers():
    # V4 Bearer varsa header; yoksa v3 key’i querystring
    return {"Authorization": f"Bearer {TMDB_API_KEY}"} if TMDB_API_KEY and len(TMDB_API_KEY) > 40 else None

def _req(path, params=None):
    params = params or {}
    h = _use_headers()
    if h:
        return requests.get(f"{TMDB_BASE}{path}", headers=h, params=params, timeout=25)
    params = {"api_key": TMDB_API_KEY, **params}
    return requests.get(f"{TMDB_BASE}{path}", params=params, timeout=25)

def _poster_url(p):   return f"https://image.tmdb.org/t/p/w500{p}"  if p else None
def _backdrop_url(p): return f"https://image.tmdb.org/t/p/w780{p}"  if p else None

def _map(movie, credits=None, details=None, videos=None):
    m = {**(movie or {}), **(details or {})}
    out = {
        "title": m.get("title"),
        "original_title": m.get("original_title"),
        "year": int(m["release_date"][:4]) if m.get("release_date") else None,
        "runtime": m.get("runtime") or None,
        "synopsis": m.get("overview") or None,
        "countries": [c.get("name") for c in m.get("production_countries", [])] or None,
        "languages": [l.get("english_name") for l in m.get("spoken_languages", [])] or None,
        "poster": _poster_url(m.get("poster_path")),
        "backdrop": _backdrop_url(m.get("backdrop_path")),
        "director": None,
        "writer": None,
        "cinematography": None,
        "cast_top": None,
        "trailer_url": None,
    }
    if credits:
        crew = credits.get("crew", [])
        out["director"] = ", ".join([c["name"] for c in crew if c.get("job") == "Director"]) or None
        out["writer"]   = ", ".join([c["name"] for c in crew if c.get("job") in ("Writer","Screenplay","Author")]) or None
        dops = [c["name"] for c in crew if c.get("job") in ("Director of Photography","Cinematography")]
        out["cinematography"] = ", ".join(dops) if dops else None
        cast = credits.get("cast", [])
        if cast:
            out["cast_top"] = ", ".join([p["name"] for p in cast[:3]])
    if videos:
        vids = videos.get("results", [])
        yt = [v for v in vids if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
        if yt:
            out["trailer_url"] = f"https://youtu.be/{yt[0]['key']}"
    return out

def get_by_title(title: str, year: int | None = None):
    if not TMDB_API_KEY or not title:
        return None
    r = _req("/search/movie", {"query": title})
    if r.status_code != 200:
        return None
    res = r.json().get("results") or []
    if not res:
        return None
    pick = None
    if year:
        for m in res:
            try:
                if m.get("release_date") and int(m["release_date"][:4]) == int(year):
                    pick = m; break
            except Exception:
                pass
    if not pick:
        pick = res[0]
    mid = pick["id"]
    det  = _req(f"/movie/{mid}").json()
    cred = _req(f"/movie/{mid}/credits").json()
    vids = _req(f"/movie/{mid}/videos").json()
    return _map(pick, cred, det, vids)
