from notion_client import Client
from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS
import time
from notion_client.errors import APIResponseError

# ---------- value helpers ----------

def _txt(v: str):
    if v is None or v == "":
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": str(v)[:2000]}}]}

def _url(v: str):   return {"url": (v or None)}
def _num(v):
    if v in (None, ""): return {"number": None}
    try:                 return {"number": int(v)}
    except Exception:
        try:             return {"number": float(v)}
        except Exception:return {"number": None}

def _multi(vals):
    if not vals: return {"multi_select": []}
    return {"multi_select": [{"name": str(x)} for x in vals if str(x).strip()]}

def _title(v: str):
    if v is None or v == "": return {"title": []}
    return {"title": [{"type": "text", "text": {"content": str(v)[:200]}}]}

def read_prop(props, name):
    if name not in props: return None
    p = props[name]; t = p.get("type")
    if t == "title":        return p["title"][0]["plain_text"] if p["title"] else None
    if t == "rich_text":    return "".join([x["plain_text"] for x in p["rich_text"]]) if p["rich_text"] else None
    if t == "number":       return p.get("number")
    if t == "url":          return p.get("url")
    if t == "multi_select": return [x["name"] for x in p.get("multi_select", [])]
    if t == "date":         return (p.get("date") or {}).get("start")
    return None

# ---------- client ----------
client = Client(auth=NOTION_TOKEN)

NEED_KEYS = (
    "year","director","writer","cinematography","runtime","poster",
    "original_title","synopsis","countries","languages","cast_top","backdrop","trailer_url"
)

import time
from notion_client import Client
from notion_client.errors import APIResponseError
from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

# ... read_prop ve yardımcılar aynı kalsın ...

client = Client(auth=NOTION_TOKEN)

NEED_KEYS = (
    "year","director","writer","cinematography","runtime","poster",
    "original_title","synopsis","countries","languages","cast_top","backdrop","trailer_url"
)

def _query_with_retry(payload):
    delay = 0.5
    for _ in range(6):
        try:
            return client.databases.query(**payload)
        except APIResponseError as e:
            status = getattr(e, "status", None)
            if status in (409, 429, 500, 502, 503, 504):
                time.sleep(delay)
                delay = min(delay * 2, 8)
                continue
            raise

def iter_pages_needing_fill(limit=200):
    """Letterboxd linki olan ve hedef alanlardan EN AZ BİRİ boş olan sayfaları döndürür."""
    page_size = 100
    start_cursor = None
    results = []

    while True:
        payload = {"database_id": NOTION_DATABASE_ID, "page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = _query_with_retry(payload)
        pages = resp.get("results", [])
        start_cursor = resp.get("next_cursor")
        has_more = resp.get("has_more", False)

        for page in pages:
            props = page["properties"]
            lb = read_prop(props, NOTION_COLS["letterboxd"])
            if not lb:
                continue

            # boşluk kontrolü
            need_any = False
            for k in NEED_KEYS:
                col = NOTION_COLS.get(k)
                if col and col in props:
                    v = read_prop(props, col)
                    if k in ("year","runtime"):
                        if v is None: need_any = True; break
                    else:
                        if v in (None, "", []): need_any = True; break

            if need_any:
                results.append(page)
                if limit and len(results) >= limit:
                    return results

        if not has_more:
            break

    return results

def update_page(page_id: str, data: dict):
    """Python dict -> Notion property payload dönüşümü ve update."""
    props = {}

    # ---- Text alanları ----
    text_keys = (
        "director","writer","cinematography",
        "original_title","synopsis","cast_top"
    )
    for k in text_keys:
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _txt(data[k])

    # ---- Number alanları ----
    if "year" in data and NOTION_COLS.get("year"):
        props[NOTION_COLS["year"]] = _num(data["year"])
    if "runtime" in data and NOTION_COLS.get("runtime"):
        props[NOTION_COLS["runtime"]] = _num(data["runtime"])

    # ---- URL alanları ----
    for k in ("poster","backdrop","trailer_url"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _url(data[k])

    # ---- Multi-select alanları ----
    if "countries" in data and NOTION_COLS.get("countries"):
        props[NOTION_COLS["countries"]] = _multi(data["countries"])
    if "languages" in data and NOTION_COLS.get("languages"):
        props[NOTION_COLS["languages"]] = _multi(data["languages"])

    # ---- COVER: Backdrop varsa sayfanın kapak görseli yap ----
    cover_payload = None
    if data.get("backdrop"):
        cover_payload = {
            "type": "external",
            "external": {"url": data["backdrop"]}
        }

    # ---- Notion update çağrısı ----
    kwargs = {"page_id": page_id}
    if props:
        kwargs["properties"] = props
    if cover_payload:
        kwargs["cover"] = cover_payload

    if len(kwargs) > 1:  # en az properties veya cover var
        client.pages.update(**kwargs)

    # --- 409 Conflict için exponential retry ---
    delay = 0.5
    for attempt in range(5):
        try:
            client.pages.update(page_id=page_id, properties=props)
            return
        except APIResponseError as e:
            status = getattr(e, "status", None)
            if status == 409 or "Conflict" in str(e):
                time.sleep(delay)
                delay *= 2
                continue
            raise
