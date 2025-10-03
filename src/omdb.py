import requests, logging
from .config import OMDB_API_KEY

BASE = "http://www.omdbapi.com/"

def get_by_imdb(imdb_id: str):
    if not OMDB_API_KEY:
        return None
    params = {"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "short", "r": "json"}
    r = requests.get(BASE, params=params, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("Response") != "True":
        return None
    # Map fields
    out = {
        "title": data.get("Title"),
        "year": int(data["Year"].split("–")[0]) if data.get("Year") else None,
        "runtime": None,
        "director": data.get("Director"),
        "writer": data.get("Writer"),
        "poster": data.get("Poster") if data.get("Poster") and data["Poster"] != "N/A" else None,
        "cinematography": None,  # OMDb doesn't expose cinematographer
    }
    # Runtime like "123 min"
    rt = data.get("Runtime")
    if rt and rt.endswith("min"):
        try:
            out["runtime"] = int(rt.split()[0])
        except Exception:
            pass
    return out
