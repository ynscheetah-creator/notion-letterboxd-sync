import re, json, requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def normalize_url(url: str) -> str:
    # Accept boxd.it short links and full letterboxd links
    if "boxd.it" in url or "letterboxd.com" in url:
        return url
    raise ValueError("Not a Letterboxd URL")

def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text

def parse_ld_json(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string.strip())
            # Sometimes array of graphs
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") in ("Movie", "CreativeWork"):
                        return item
            elif isinstance(data, dict):
                if data.get("@type") in ("Movie", "CreativeWork"):
                    return data
        except Exception:
            continue
    return None

def extract_from_ld(data):
    title = data.get("name")
    year = None
    if "datePublished" in data:
        try:
            year = int(str(data["datePublished"])[:4])
        except Exception:
            pass

    imdb_id = None
    same = data.get("sameAs")
    if isinstance(same, list):
        for u in same:
            m = re.search(r"imdb\.com/title/(tt\d+)", str(u))
            if m:
                imdb_id = m.group(1)
                break
    elif isinstance(same, str):
        m = re.search(r"imdb\.com/title/(tt\d+)", same)
        if m:
            imdb_id = m.group(1)

    return {"title": title, "year": year, "imdb_id": imdb_id}

def extract_ids(letterboxd_url: str):
    url = normalize_url(letterboxd_url)
    html = fetch_html(url)
    ld = parse_ld_json(html)
    if not ld:
        return {"title": None, "year": None, "imdb_id": None}
    return extract_from_ld(ld)
