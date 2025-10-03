import re, json, requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def normalize_url(url: str) -> str:
    if "boxd.it" in url or "letterboxd.com" in url:
        return url
    raise ValueError("Not a Letterboxd URL")

def fetch_html(url: str) -> str:
    # requests follows redirects (boxd.it -> letterboxd.com/film/...)
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text

def _first_movie_obj(obj):
    """Return the dict that represents the Movie inside many JSON-LD shapes."""
    if isinstance(obj, dict):
        # @graph variant
        if "@graph" in obj and isinstance(obj["@graph"], list):
            for item in obj["@graph"]:
                t = item.get("@type")
                if t == "Movie" or (isinstance(t, list) and "Movie" in t):
                    return item
        # single movie
        t = obj.get("@type")
        if t == "Movie" or (isinstance(t, list) and "Movie" in t):
            return obj
    elif isinstance(obj, list):
        for item in obj:
            res = _first_movie_obj(item)
            if res:
                return res
    return None

def parse_ld_json(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
        except Exception:
            continue
        movie = _first_movie_obj(data)
        if movie:
            return movie
    return None

def extract_from_ld(data, html: str):
    title = data.get("name")

    year = None
    # datePublished or genre-year patterns
    if "datePublished" in data:
        try:
            year = int(str(data["datePublished"])[:4])
        except Exception:
            pass

    imdb_id = None
    same = data.get("sameAs")
    candidates = []
    if isinstance(same, list):
        candidates.extend([str(u) for u in same])
    elif isinstance(same, str):
        candidates.append(same)

    for u in candidates:
        m = re.search(r"imdb\.com/title/(tt\d+)", u)
        if m:
            imdb_id = m.group(1)
            break

    # fallback: scan whole HTML for IMDb link
    if not imdb_id:
        m = re.search(r"https?://www\.imdb\.com/title/(tt\d+)", html)
        if m:
            imdb_id = m.group(1)

    # extra fallbacks for title/year if still missing
    if not title:
        # og:title often ends with " (YEAR) — Letterboxd"
        og = soup.find("meta", {"property": "og:title"})
        if og and og.get("content"):
            t = og["content"]
            title = re.sub(r"\s*\(\d{4}\).*", "", t).strip()

    return {"title": title, "year": year, "imdb_id": imdb_id}

def extract_ids(letterboxd_url: str):
    url = normalize_url(letterboxd_url)
    html = fetch_html(url)
    ld = parse_ld_json(html)
    if not ld:
        # last-chance regex for IMDb and title
        m = re.search(r"https?://www\.imdb\.com/title/(tt\d+)", html)
        imdb_id = m.group(1) if m else None
        # crude title from <title>
        title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        title = None
        if title_match:
            t = BeautifulSoup(title_match.group(1), "html.parser").get_text()
            title = re.sub(r"\s*\(\d{4}\).*", "", t).replace("• Letterboxd", "").strip()
        return {"title": title, "year": None, "imdb_id": imdb_id}
    return extract_from_ld(ld, html)
