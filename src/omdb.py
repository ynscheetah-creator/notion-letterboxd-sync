import requests, logging
from .config import OMDB_API_KEY

BASE = "http://www.omdbapi.com/"

def _map_omdb_payload(data: dict):
    out = {
        "title": data.get("Title"),
        "year": int(data["Year"].split("–")[0]) if data.get("Year") else None,
        "runtime": None,
        "director": data.get("Director"),
        "writer": data.get("Writer"),
        "poster": data.get("Poster") if data.get("Poster") and data["Poster"] != "N/A" else None,
        "cinematography": None,  # OMDb sinematograf vermez
    }
    rt = data.get("Runtime")  # "123 min"
    if rt and rt.endswith("min"):
        try:
            out["runtime"] = int(rt.split()[0])
        except Exception:
            pass
    return out

def get_by_imdb(imdb_id: str):
    """IMDb ID ile sorgu (tercih edilen yol)."""
    if not OMDB_API_KEY or not imdb_id:
        return None
    params = {"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "short", "r": "json"}
    r = requests.get(BASE, params=params, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("Response") != "True":
        return None
    return _map_omdb_payload(data)

def get_by_title(title: str, year: int | None = None):
    """IMDb bulunamazsa başlık (+opsiyonel yıl) ile sorgu."""
    if not OMDB_API_KEY or not title:
        return None
    params = {"apikey": OMDB_API_KEY, "t": title, "plot": "short", "r": "json"}
    if year:
        params["y"] = str(year)
    r = requests.get(BASE, params=params, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("Response") != "True":
        return None
    return _map_omdb_payload(data)
