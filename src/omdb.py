"""
OMDb: başlık+yıl ile hızlı dene (başarısız olursa TMDb’ye bırakıyoruz).
"""
import requests
from .config import OMDB_API_KEY

BASE = "https://www.omdbapi.com/"

def _ok(js):
    return js and js.get("Response") == "True"

def get_by_title(title: str, year: int | None = None):
    if not OMDB_API_KEY or not title:
        return None
    params = {"apikey": OMDB_API_KEY, "t": title}
    if year:
        params["y"] = str(year)
    try:
        r = requests.get(BASE, params=params, timeout=20)
        js = r.json()
    except Exception:
        return None
    if not _ok(js):
        return None

    out = {
        "title": js.get("Title"),
        "year": int(js["Year"]) if js.get("Year", "").isdigit() else None,
        "runtime": None,
        "director": js.get("Director") or None,
        "writer": js.get("Writer") or None,
        "cinematography": None,  # OMDb her zaman vermez
        "poster": js.get("Poster") if js.get("Poster", "").startswith("http") else None,

        # ekstra alanlar OMDb’de zayıf olduğu için boş dönebilir
        "original_title": js.get("Title") or None,
        "synopsis": js.get("Plot") or None,
        "countries": [c.strip() for c in (js.get("Country") or "").split(",") if c.strip()] or None,
        "languages": [l.strip() for l in (js.get("Language") or "").split(",") if l.strip()] or None,
        "cast_top": None,
        "backdrop": None,
        "trailer_url": None,
    }

    # runtime "148 min" formatında gelir
    if js.get("Runtime", "").endswith(" min"):
        try:
            out["runtime"] = int(js["Runtime"].split()[0])
        except Exception:
            pass

    # görüntü yönetmeni varsa
    for k in ("Cinematography", "cinematography"):
        if js.get(k):
            out["cinematography"] = js.get(k)
            break

    # başrol listesi (ilk 3)
    actors = [a.strip() for a in (js.get("Actors") or "").split(",") if a.strip()]
    if actors:
        out["cast_top"] = ", ".join(actors[:3])

    return out
