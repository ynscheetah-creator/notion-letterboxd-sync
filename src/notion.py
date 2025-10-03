from notion_client import Client
from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

# ---------- helpers ----------

def _txt(v: str):
    if v is None or v == "":
        return {"rich_text": []}
    # Notion property rich_text için basit text obje
    return {"rich_text": [{"type": "text", "text": {"content": str(v)[:2000]}}]}

def _url(v: str):
    return {"url": (v or None)}

def _num(v):
    if v is None or v == "":
        return {"number": None}
    try:
        return {"number": int(v)}
    except Exception:
        try:
            return {"number": float(v)}
        except Exception:
            return {"number": None}

def _multi(vals):
    if not vals:
        return {"multi_select": []}
    return {"multi_select": [{"name": str(x)} for x in vals if str(x).strip()]}

def _title(v: str):
    if v is None or v == "":
        return {"title": []}
    return {"title": [{"type": "text", "text": {"content": str(v)[:200]}}]}

def read_prop(props, name):
    """Notion property değerini Python tipine çevir."""
    if name not in props:
        return None
    p = props[name]
    t = p.get("type")
    if t == "title":
        arr = p["title"]
        return arr[0]["plain_text"] if arr else None
    if t == "rich_text":
        arr = p["rich_text"]
        return "".join([x["plain_text"] for x in arr]) if arr else None
    if t == "number":
        return p.get("number")
    if t == "url":
        return p.get("url")
    if t == "multi_select":
        return [x["name"] for x in p.get("multi_select", [])]
    if t == "date":
        d = p.get("date")
        return d.get("start") if d else None
    return None

# ---------- client ----------

client = Client(auth=NOTION_TOKEN)

# Bu alanlardan biri boşsa doldurmaya aday sayılır
NEED_KEYS = (
    "year","director","writer","cinematography","runtime","poster",
    "original_title","synopsis","countries","languages","cast_top","backdrop","trailer_url"
)

def iter_pages_needing_fill(limit=200):
    """Letterboxd linki olan ve alanlarından bazıları boş olan sayfaları getirir."""
    # Basit query: Letterboxd dolu olanları çekelim
    resp = client.databases.query(
        **{
            "database_id": NOTION_DATABASE_ID,
            "page_size": limit,
            # İstersen burada filtreyi genişletebilirsin
        }
    )
    results = []
    for page in resp.get("results", []):
        props = page["properties"]
        # Letterboxd varsa aday
        lb = read_prop(props, NOTION_COLS["letterboxd"])
        if not lb:
            continue
        # en az bir ihtiyaç boş mu?
        need_any = False
        for k in NEED_KEYS:
            if NOTION_COLS.get(k) in props:
                v = read_prop(props, NOTION_COLS[k])
                if v in (None, "", [], 0) and k not in ("year","runtime"):  # sayı alanı 0 olabilir
                    need_any = True
                    break
        if need_any:
            results.append(page)
    return results

def update_page(page_id: str, data: dict):
    """Python dict -> Notion property payload dönüşümü ve update."""
    props = {}

    # Text / Rich text
    text_keys = (
        "director","writer","cinematography",
        "original_title","synopsis","cast_top"
    )
    for k in text_keys:
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _txt(data[k])

    # Numbers
    if "year" in data and NOTION_COLS.get("year"):
        props[NOTION_COLS["year"]] = _num(data["year"])
    if "runtime" in data and NOTION_COLS.get("runtime"):
        props[NOTION_COLS["runtime"]] = _num(data["runtime"])

    # URLs
    for k in ("poster","backdrop","trailer_url"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _url(data[k])

    # Multi-selects
    if "countries" in data and NOTION_COLS.get("countries"):
        props[NOTION_COLS["countries"]] = _multi(data["countries"])
    if "languages" in data and NOTION_COLS.get("languages"):
        props[NOTION_COLS["languages"]] = _multi(data["languages"])

    if not props:
        return

    client.pages.update(page_id=page_id, properties=props)
