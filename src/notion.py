from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional

from notion_client import Client

from src.config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# -----------------------------
# Value builders (Notion payload)
# -----------------------------
def _txt(val: Optional[str]) -> Dict[str, Any]:
    if not val:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": str(val)}}]}

def _num(val: Optional[Any]) -> Dict[str, Any]:
    if val in (None, ""):
        return {"number": None}
    try:
        return {"number": int(val)}
    except Exception:
        try:
            return {"number": float(val)}
        except Exception:
            return {"number": None}

def _url(val: Optional[str]) -> Dict[str, Any]:
    return {"url": (str(val) if val else None)}

def _multi(items: Optional[List[str]]) -> Dict[str, Any]:
    arr = []
    if items:
        for it in items:
            s = str(it).strip()
            if s:
                arr.append({"name": s})
    return {"multi_select": arr}

def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [p.strip() for p in str(x).split(",") if p.strip()]

# -----------------------------
# Read helpers
# -----------------------------
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
    """Notion property -> sade Python değeri."""
    if not col_name or col_name not in props:
        return None
    prop = props[col_name]
    ptype = prop.get("type")

    if ptype == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", [])).strip()
    if ptype == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", [])).strip()
    if ptype == "number":
        return prop.get("number")
    if ptype == "url":
        return prop.get("url")
    if ptype == "multi_select":
        return [o.get("name", "") for o in prop.get("multi_select", [])]
    if ptype == "files":
        files = prop.get("files", [])
        if not files:
            return None
        f0 = files[0]
        if f0.get("type") == "external":
            return f0.get("external", {}).get("url")
        if f0.get("type") == "file":
            return f0.get("file", {}).get("url")
        return None
    return None

def get_page_title(props: Dict[str, Any]) -> Optional[str]:
    """Title kolonunu isimle eşleştiremesek de (mapping yanlışsa bile) başlığı bulur."""
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        txt = "".join(t.get("plain_text", "") for t in props[name_col].get("title", [])).strip()
        return txt or None
    for p in props.values():
        if p.get("type") == "title":
            txt = "".join(t.get("plain_text", "") for t in p.get("title", [])).strip()
            if txt:
                return txt
    return None

# -----------------------------
# Update helpers
# -----------------------------
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url:
        return
    client.pages.update(page_id=page_id, cover={"type": "external", "external": {"url": url}})

def update_page(page_id: str, data: Dict[str, Any], existing_props: Optional[Dict[str, Any]] = None) -> None:
    """
    Python dict -> Notion properties + cover.
    Multi-select alanlar düzgün yazılır; poster/backdrop/trailer url alanları URL tipinde kalır.
    """
    props: Dict[str, Any] = {}

    # Numbers
    if "year" in data and NOTION_COLS.get("year"):
        props[NOTION_COLS["year"]] = _num(data["year"])
    if "runtime" in data and NOTION_COLS.get("runtime"):
        props[NOTION_COLS["runtime"]] = _num(data["runtime"])

    # Text
    for k in ("original_title", "synopsis"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _txt(data[k])

    # URLs
    for k in ("poster", "backdrop", "trailer_url"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _url(data[k])

    # Multi-select
    for k in ("director", "writer", "cinematography", "cast_top", "countries", "languages"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _multi(_as_list(data[k]))

    cover_payload = None
    if data.get("backdrop"):
        cover_payload = {"type": "external", "external": {"url": data["backdrop"]}}

    kwargs: Dict[str, Any] = {"page_id": page_id}
    if props:
        kwargs["properties"] = props
    if cover_payload:
        kwargs["cover"] = cover_payload

    if len(kwargs) > 1:
        client.pages.update(**kwargs)

# -----------------------------
# Query helpers
# -----------------------------
# Doldurulmasını hedeflediğimiz alanlar
NEED_KEYS = (
    "year", "director", "writer", "cinematography", "runtime",
    "poster", "original_title", "synopsis",
    "countries", "languages", "cast_top", "backdrop", "trailer_url",
)

def _page_needs_fill(page: Dict[str, Any]) -> bool:
    props = page["properties"]
    # Letterboxd link yoksa hiç uğraşma
    lb = read_prop(props, NOTION_COLS.get("letterboxd"))
    if not lb:
        return False

    for k in NEED_KEYS:
        col = NOTION_COLS.get(k)
        if not col or col not in props:
            continue
        v = read_prop(props, col)
        if k in ("year", "runtime"):
            if v is None:
                return True
        else:
            if v in (None, "", []):
                return True
    return False

def iter_pages_needing_fill(limit: int = 200) -> Iterable[Dict[str, Any]]:
    """
    Letterboxd linki olan ve hedef alanlarından en az biri boş olan sayfaları döndürür.
    limit=0 -> limitsiz. Veritabanını sayfalayarak tarar.
    """
    page_size = 100
    start_cursor = None
    found = 0

    while True:
        payload: Dict[str, Any] = {"database_id": NOTION_DATABASE_ID, "page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        start_cursor = resp.get("next_cursor")
        has_more = resp.get("has_more", False)

        for page in pages:
            if _page_needs_fill(page):
                yield page
                found += 1
                if limit and found >= limit:
                    return

        if not has_more:
            break

def iter_recent_pages(force_recent: int = 10, by: str = "created") -> List[Dict[str, Any]]:
    """
    Son N sayfayı getir (varsayılan created_time’a göre).
    by = "created" | "edited"
    """
    sorts = []
    if by == "created":
        sorts = [{"property": "Created", "direction": "descending"}]  # Notion "Created time" property is system-level
    elif by == "edited":
        sorts = [{"timestamp": "last_edited_time", "direction": "descending"}]

    # Notion API’de sistem created_time için özel sort kullanılır
    # Eğer veritabanında ayrı "Created" property’niz yoksa timestamp sort kullanırız:
    if not sorts:
        sorts = [{"timestamp": "created_time", "direction": "descending"}]

    resp = client.databases.query(
        **{
            "database_id": NOTION_DATABASE_ID,
            "page_size": force_recent,
            "sorts": sorts,
        }
    )
    return resp.get("results", [])

def iter_all_pages() -> Iterable[Dict[str, Any]]:
    """Veritabanındaki TÜM sayfaları sayfalayarak getirir (örn. toplu cover için)."""
    page_size = 100
    start_cursor = None
    while True:
        payload: Dict[str, Any] = {"database_id": NOTION_DATABASE_ID, "page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = client.databases.query(**payload)
        for page in resp.get("results", []):
            yield page
        if not resp.get("has_more"):
            break
        start_cursor = resp.get("next_cursor")
