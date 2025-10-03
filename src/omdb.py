import requests
from .config import OMDB_API_KEY

BASE = "http://www.omdbapi.com/"

def _map(data: dict):
    out = {
        "title": data.get("Title"),
        "year": int(data["Year"].split("–")[0]) if data.get("Year") else None,
        "runtime": None,
        "director": data.get("Director"),
        "writer": data.get("Writer"),
        "poster": data.get("Poster") if data.get("Poster") and data["Poster"] != "N/A" else None,
        "cinematography": None,
    }
    rt = data.get("Runtime")  # "123 min"
    if rt and rt.endswith("min"):
        try: out["runtime"] = int(rt.split()[0])
        except Exception: pass
    return out

def get_by_imdb(imdb_id: str):
    if not OMDB_API_KEY or not imdb_id: return None
    r = requests.get(BASE, params={"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "short"}, timeout=20)
    if r.status_code != 200: return None
    data = r.json()
    if data.get("Response") != "True": return None
    return _map(data)

def get_by_title(title: str, year: int | None = None):
    if not OMDB_API_KEY or not title: return None
    p = {"apikey": OMDB_API_KEY, "t": title, "plot": "short"}
    if year: p["y"] = str(year)
    r = requests.get(BASE, params=p, timeout=20)
    if r.status_code != 200: return None
    data = r.json()
    if data.get("Response") == "True": return _map(data)
    # exact title bulunamadı → search ile en iyi eşleşmeyi al
    s = requests.get(BASE, params={"apikey": OMDB_API_KEY, "s": title, "type": "movie"}, timeout=20)
    if s.status_code != 200: return None
    js = s.json()
    results = js.get("Search") or []
    if not results: return None
    # yıl varsa aynı yılı, yoksa ilk sonucu seç
    cand = None
    if year:
        for it in results:
            try:
                if int(it.get("Year", "0")[:4]) == int(year):
                    cand = it; break
            except Exception: pass
    if not cand: cand = results[0]
    imdb = cand.get("imdbID")
    if imdb: return get_by_imdb(imdb)
    return None
