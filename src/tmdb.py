import requests
from .config import TMDB_API_KEY

TMDB_BASE = "https://api.themoviedb.org/3"

def _use_headers():
    # V4 Bearer varsa header, yoksa v3 api_key querystring kullan
    return {"Authorization": f"Bearer {TMDB_API_KEY}"} if TMDB_API_KEY and len(TMDB_API_KEY) > 40 else None

def _map_movie(m, credits=None):
    poster = f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get("poster_path") else None
    year = int(m["release_date"][:4]) if m.get("release_date") else None
    out = {
        "title": m.get("title"),
        "year": year,
        "runtime": None,
        "director": None,
        "writer": None,
        "cinematography": None,
        "poster": poster,
    }
    if credits:
        crew = credits.get("crew", [])
        out["director"] = ", ".join([c["name"] for c in crew if c.get("job") == "Director"]) or None
        out["writer"]   = ", ".join([c["name"] for c in crew if c.get("job") in ("Writer","Screenplay","Author")]) or None
        dops = [c["name"] for c in crew if c.get("job") in ("Director of Photography","Cinematography")]
        out["cinematography"] = ", ".join(dops) if dops else None
    return out

def get_by_imdb(imdb_id: str):
    if not TMDB_API_KEY or not imdb_id:
        return None
    h = _use_headers()
    if h:
        r = requests.get(f"{TMDB_BASE}/find/{imdb_id}?external_source=imdb_id", headers=h, timeout=20)
    else:
        r = requests.get(f"{TMDB_BASE}/find/{imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id", timeout=20)
    if r.status_code != 200:
        return None
    js = r.json()
    results = js.get("movie_results") or []
    if not results:
        return None
    m = results[0]
    mid = m["id"]
    if h:
        cred = requests.get(f"{TMDB_BASE}/movie/{mid}/credits", headers=h, timeout=20).json()
        det  = requests.get(f"{TMDB_BASE}/movie/{mid}", headers=h, timeout=20).json()
    else:
        cred = requests.get(f"{TMDB_BASE}/movie/{mid}/credits?api_key={TMDB_API_KEY}", timeout=20).json()
        det  = requests.get(f"{TMDB_BASE}/movie/{mid}?api_key={TMDB_API_KEY}", timeout=20).json()
    out = _map_movie(m, cred)
    if det.get("runtime"):
        out["runtime"] = int(det["runtime"])
    return out

def get_by_title(title: str, year: int | None = None):
    """Başlıkla ara; yıl verilmişse ona göre en iyi eşleşmeyi seç."""
    if not TMDB_API_KEY or not title:
        return None
    h = _use_headers()
    if h:
        r = requests.get(f"{TMDB_BASE}/search/movie?query={requests.utils.quote(title)}", headers=h, timeout=20)
    else:
        r = requests.get(f"{TMDB_BASE}/search/movie?api_key={TMDB_API_KEY}&query={requests.utils.quote(title)}", timeout=20)
    if r.status_code != 200:
        return None
    js = r.json()
    res = js.get("results") or []
    if not res:
        return None

    pick = None
    if year:
        for m in res:
            try:
                if m.get("release_date") and int(m["release_date"][:4]) == int(year):
                    pick = m
                    break
            except Exception:
                pass
    if not pick:
        pick = res[0]

    mid = pick["id"]
    if h:
        cred = requests.get(f"{TMDB_BASE}/movie/{mid}/credits", headers=h, timeout=20).json()
        det  = requests.get(f"{TMDB_BASE}/movie/{mid}", headers=h, timeout=20).json()
    else:
        cred = requests.get(f"{TMDB_BASE}/movie/{mid}/credits?api_key={TMDB_API_KEY}", timeout=20).json()
        det  = requests.get(f"{TMDB_BASE}/movie/{mid}?api_key={TMDB_API_KEY}", timeout=20).json()

    out = _map_movie(pick, cred)
    if det.get("runtime"):
        out["runtime"] = int(det["runtime"])
    return out
