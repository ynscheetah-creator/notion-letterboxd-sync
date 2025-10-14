# src/notion.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from notion_client import Client

from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# -----------------------------
# Value builders
# -----------------------------
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
    out: List[Dict[str, str]] = []
    if items:
        for it in items:
            s = str(it).strip()
            if s:
                out.append({"name": s})
    return {"multi_select": out}

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
    if not col_name or col_name not in props:
        return None
    prop = props[col_name]
    t = prop.get("type")
    if t == "title":
        return "".join([r.get("plain_text", "") for r in prop.get("title", [])]).strip()
    if t == "rich_text":
        return "".join([r.get("plain_text", "") for r in prop.get("rich_text", [])]).strip()
    if t == "number":
        return prop.get("number")
    if t == "url":
        return prop.get("url")
    if t == "multi_select":
        return [o.get("name", "") for o in prop.get("multi_select", [])]
    if t == "files":
        files = prop.get("files", [])
        if not files:
            return None
        f0 = files[0]
        if f0.get("type") == "external":
            return (f0.get("external") or {}).get("url")
        if f0.get("type") == "file":
            return (f0.get("file") or {}).get("url")
    return None

def get_page_title(props: Dict[str, Any]) -> Optional[str]:
    # Map ile gelirse
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        return "".join(t.get("plain_text", "") for t in props[name_col].get("title", [])).strip() or None
    # Fallback: type=title olanı bul
    for p in props.values():
        if p.get("type") == "title":
            s = "".join(t.get("plain_text", "") for t in p.get("title", [])).strip()
            if s:
                return s
    return None

# -----------------------------
# Update helpers
# -----------------------------
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url:
        return
    client.pages.update(
        page_id=page_id,
        cover={"type": "external", "external": {"url": url}},
    )

def update_page(page_id: str, data: Dict[str, Any], existing_props: Optional[Dict[str, Any]] = None) -> None:
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

    # Page title (only if provided)
    page_title = data.get("__page_title")
    if page_title:
        title_col = NOTION_COLS.get("name")
        if not title_col and existing_props:
            for key, val in existing_props.items():
                if val.get("type") == "title":
                    title_col = key
                    break
        if title_col:
            props[title_col] = {
                "title": [{"type": "text", "text": {"content": str(page_title)}}]
            }

    # Cover from backdrop
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
NEED_KEYS = (
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

def iter_recent_pages(force_recent: int = 20):
    """
    Tümü yerine 'son N sayfa'yı döndürür (oluşturulma veya son değişiklik sırasına göre).
    """
    page_size = min(max(int(force_recent), 1), 100)
    payload: Dict[str, Any] = {
        "database_id": NOTION_DATABASE_ID,
        "page_size": page_size,
        # İstersen Notion filter/sort ekleyebilirsin.
    }
    resp = client.databases.query(**payload)
    return resp.get("results", [])

def iter_all_pages():
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
