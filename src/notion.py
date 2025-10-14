# src/notion.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from notion_client import Client

from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# ---------- builders ----------
def _title(val: Optional[str]) -> Dict[str, Any]:
    s = (val or "").strip()
    return {"title": []} if not s else {"title": [{"type": "text", "text": {"content": s}}]}

def _txt(val: Optional[str]) -> Dict[str, Any]:
    s = "" if val is None else str(val)
    return {"rich_text": []} if not s else {"rich_text": [{"type": "text", "text": {"content": s}}]}

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
            name = str(it).strip()
            if name:
                out.append({"name": name})
    return {"multi_select": out}

# ---------- readers ----------
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
    if not col_name or col_name not in props:
        return None
    prop = props[col_name]; ptype = prop.get("type")
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
        if not files: return None
        f0 = files[0]
        if f0.get("type") == "external":
            return f0.get("external", {}).get("url")
        if f0.get("type") == "file":
            return f0.get("file", {}).get("url")
    return None

def get_page_title(props: dict) -> Optional[str]:
    # mapping doğruysa
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        txt = "".join(t.get("plain_text", "") for t in props[name_col].get("title", []))
        return txt.strip() or None
    # yoksa title tipini ara
    for p in props.values():
        if p.get("type") == "title":
            txt = "".join(t.get("plain_text", "") for t in p.get("title", []))
            txt = txt.strip()
            if txt:
                return txt
    return None

# ---------- updates ----------
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url:
        return
    client.pages.update(page_id=page_id, cover={"type": "external", "external": {"url": url}})

def update_page(page_id: str, data: Dict[str, Any]) -> None:
    """
    data: { 'name', 'year','runtime','director','writer','cinematography',
            'poster','backdrop','trailer_url',
            'original_title','synopsis',
            'countries','languages','cast_top' }
    """
    props: Dict[str, Any] = {}

    # --- title (Name)
    if "name" in data and NOTION_COLS.get("name"):
        props[NOTION_COLS["name"]] = _title(data["name"])

    # --- numbers
    if "year" in data and NOTION_COLS.get("year"):
        props[NOTION_COLS["year"]] = _num(data["year"])
    if "runtime" in data and NOTION_COLS.get("runtime"):
        props[NOTION_COLS["runtime"]] = _num(data["runtime"])

    # --- texts
    for k in ("original_title", "synopsis"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _txt(data[k])

    # --- urls
    for k in ("poster", "backdrop", "trailer_url"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _url(data[k])

    # --- multi-selects
    for k in ("director", "writer", "cinematography", "cast_top", "countries", "languages"):
        if k in data and NOTION_COLS.get(k):
            vals = data[k]
            if vals is None:
                vals = []
            elif not isinstance(vals, (list, tuple, set)):
                vals = [v.strip() for v in str(vals).split(",") if v.strip()]
            props[NOTION_COLS[k]] = _multi(list(vals))

    # cover
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

# ---------- queries ----------
def iter_recent_pages(force_recent: int = 20, by: str = "created") -> List[Dict[str, Any]]:
    """
    Son N sayfayı getirir. by='created' => created_time’a göre, 'edited' => last_edited_time’a göre.
    """
    sort_ts = "created_time" if by == "created" else "last_edited_time"
    out: List[Dict[str, Any]] = []
    start_cursor = None
    fetched = 0
    while True:
        payload: Dict[str, Any] = {
            "database_id": NOTION_DATABASE_ID,
            "page_size": min(100, max(1, force_recent - fetched)) if force_recent else 100,
            "sorts": [{"timestamp": sort_ts, "direction": "descending"}],
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        out.extend(pages)
        fetched += len(pages)
        if not resp.get("has_more") or (force_recent and fetched >= force_recent):
            break
        start_cursor = resp.get("next_cursor")
    return out[:force_recent] if force_recent else out
