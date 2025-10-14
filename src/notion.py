from __future__ import annotations

from typing import Any, Dict, List, Optional
from notion_client import Client

from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# --------- writers ----------
def _title(val: Optional[str]) -> Dict[str, Any]:
    if not val:
        return {"title": []}
    return {"title": [{"type": "text", "text": {"content": str(val)}}]}

def _txt(val: Optional[str]) -> Dict[str, Any]:
    if val is None:
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
            name = str(it).strip()
            if name:
                arr.append({"name": name})
    return {"multi_select": arr}

def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [p.strip() for p in str(x).split(",") if p.strip()]

# --------- readers ----------
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
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
    """Title tipindeki property’yi bularak gerçek sayfa başlığını döndür."""
    # mapping'te varsa onu dene
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        t = "".join(t.get("plain_text", "") for t in props[name_col].get("title", [])).strip()
        return t or None
    # aksi halde title tipindeki ilk property
    for p in props.values():
        if p.get("type") == "title":
            t = "".join(t.get("plain_text", "") for t in p.get("title", [])).strip()
            if t:
                return t
    return None

# --------- update ----------
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url:
        return
    client.pages.update(page_id=page_id,
                        cover={"type": "external", "external": {"url": url}})

def update_page(page_id: str, data: Dict[str, Any], existing_props: Dict[str, Any] | None = None) -> None:
    props: Dict[str, Any] = {}

    # title/name (sadece varsa yazar; istersen koşulu kaldırıp her zaman güncelleyebilirsin)
    if "name" in data and NOTION_COLS.get("name"):
        current = None
        if existing_props:
            current = read_prop(existing_props, NOTION_COLS.get("name"))
        if not current:  # boşsa yaz
            props[NOTION_COLS["name"]] = _title(data["name"])

    # numbers
    if "year" in data and NOTION_COLS.get("year"):
        props[NOTION_COLS["year"]] = _num(data["year"])
    if "runtime" in data and NOTION_COLS.get("runtime"):
        props[NOTION_COLS["runtime"]] = _num(data["runtime"])

    # rich_text
    for k in ("original_title", "synopsis"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _txt(data[k])

    # urls
    for k in ("poster", "backdrop", "trailer_url"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _url(data[k])

    # multi-select
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

# --------- query ----------
# hedef alanlar + name eklendi (başlık boş olanları da yakalamak için)
NEED_KEYS = (
    "name",  # <<< eklendi
    "year", "director", "writer", "cinematography", "runtime",
    "poster", "original_title", "synopsis",
    "countries", "languages", "cast_top", "backdrop", "trailer_url",
)

def iter_pages_needing_fill(limit: int = 200):
    page_size = 100
    start_cursor = None
    results: List[Dict[str, Any]] = []

    while True:
        payload: Dict[str, Any] = {"database_id": NOTION_DATABASE_ID, "page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        start_cursor = resp.get("next_cursor")
        has_more = resp.get("has_more", False)

        for page in pages:
            props = page["properties"]

            lb = read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb:
                continue

            need_any = False
            for k in NEED_KEYS:
                col = NOTION_COLS.get(k)
                if not col or col not in props:
                    continue
                v = read_prop(props, col)
                if k in ("year", "runtime"):
                    if v is None:
                        need_any = True
                        break
                else:
                    if v in (None, "", []):
                        need_any = True
                        break

            if need_any:
                results.append(page)
                if limit and len(results) >= limit:
                    return results

        if not has_more:
            break

    return results

def iter_recent_pages(count: int = 200):
    """Son oluşturulan/edite edilen sayfalardan belirli bir sayıda (kolay test için)."""
    page_size = min(count, 100)
    start_cursor = None
    grabbed = 0
    while True:
        payload: Dict[str, Any] = {
            "database_id": NOTION_DATABASE_ID,
            "page_size": page_size,
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        for p in pages:
            yield p
            grabbed += 1
            if grabbed >= count:
                return
        if not resp.get("has_more"):
            break
        start_cursor = resp.get("next_cursor")
