import requests
from .config import TMDB_API_KEY

TMDB_BASE = "https://api.themoviedb.org/3"

def _headers():
    return {"Authorization": f"Bearer {TMDB_API_KEY}"} if TMDB_API_KEY and len(TMDB_API_KEY) > 40 else None

def get_by_imdb(imdb_id: str):
    if not TMDB_API_KEY:
        return None
    h = _headers()
    if not h:
        # legacy key
        url = f"{TMDB_BASE}/find/{imdb_id}?api_key={TMDB_API_KEY}&external_source=imdb_id"
        r = requests.get(url, timeout=20)
    else:
        url = f"{TMDB_BASE}/find/{imdb_id}?external_source=imdb_id"
        r = requests.get(url, headers=h, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    results = data.get("movie_results") or []
    if not results:
        return None
    movie = results[0]
    # fetch credits (for cinematography)
    movie_id = movie["id"]
    if not h:
        cred = requests.get(f"{TMDB_BASE}/movie/{movie_id}/credits?api_key={TMDB_API_KEY}", timeout=20).json()
        config = None
    else:
        cred = requests.get(f"{TMDB_BASE}/movie/{movie_id}/credits", headers=h, timeout=20).json()
    crew = cred.get("crew", [])
    director = ", ".join([c["name"] for c in crew if c.get("job") == "Director"]) or None
    writer = ", ".join([c["name"] for c in crew if c.get("job") in ("Writer", "Screenplay", "Author")]) or None
    dops = [c["name"] for c in crew if c.get("job") in ("Director of Photography", "Cinematography")]
    cinematography = ", ".join(dops) if dops else None

    poster = None
    if movie.get("poster_path"):
        poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

    out = {
        "title": movie.get("title"),
        "year": int(movie["release_date"][:4]) if movie.get("release_date") else None,
        "runtime": None,  # requires another call; omit for now
        "director": director,
        "writer": writer,
        "cinematography": cinematography,
        "poster": poster,
    }
    # fetch details for runtime
    if not h:
        det = requests.get(f"{TMDB_BASE}/movie/{movie_id}?api_key={TMDB_API_KEY}", timeout=20).json()
    else:
        det = requests.get(f"{TMDB_BASE}/movie/{movie_id}", headers=h, timeout=20).json()
    rt = det.get("runtime")
    if rt:
        out["runtime"] = int(rt)
    return out
