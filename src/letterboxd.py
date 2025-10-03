import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def _title_from_slug(slug: str) -> str:
    # "before-sunrise" -> "Before Sunrise"
    words = [w for w in slug.replace("_", "-").split("-") if w]
    return " ".join(w.capitalize() for w in words)

def from_boxd(url: str):
    """
    boxd.it kısaltmasını takip etmeden (redirect header'ından) letterboxd film slug'ını al.
    ÇIKTI: {"title": "Before Sunrise", "year": None, "imdb_id": None}
    """
    if "boxd.it" not in url and "letterboxd.com" not in url:
        raise ValueError("Not a Letterboxd/boxd.it URL")
    # redirect header'ını oku
    r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=False)
    loc = r.headers.get("Location", "")
    # eğer ilk istek 301 verdiyse, Location doğrudan film sayfası olur
    if not loc:
        # bazı kısa linkler 301->302 zinciri yapar; bir GET daha deneyelim
        r2 = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        loc = r2.url

    # film slug'ını çek
    m = re.search(r"letterboxd\.com/film/([^/]+)/?", loc, re.I)
    if not m:
        # bazen /film/slug/ dışında review vb. olabilir -> yine son URL'den ara
        m = re.search(r"letterboxd\.com/film/([^/]+)/?", r.url, re.I)
    if not m:
        return {"title": None, "year": None, "imdb_id": None}

    slug = m.group(1)
    title = _title_from_slug(slug)
    return {"title": title, "year": None, "imdb_id": None}
