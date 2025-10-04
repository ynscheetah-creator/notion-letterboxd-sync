# src/notion.py
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from notion_client import Client

from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

# -----------------------------
# Notion client
# -----------------------------
client = Client(auth=NOTION_TOKEN)

# -----------------------------
# Builders (Notion property payload helpers)
# -----------------------------
def _txt(val: Optional[str]) -> Dict[str, Any]:
    if val is None:
        return {"rich_text": []}
    s = str(val)
    return {"rich_text": [{"type": "text", "text": {"content": s}}]}

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
    arr: List[Dict[str, str]] = []
    if items:
        for it in items:
            name = str(it).strip()
            if name:
                arr.append({"name": name})
    return {"multi_select": arr}

def _as_list(x: Any) -> List[str]:
    """'A, B , C' -> ['A','B','C'] (zaten listeyse normalize et)."""
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [p.strip() for p in str(x).split(",") if p.strip()]

# -----------------------------
# Read helpers (Notion -> Python)
# -----------------------------
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
    """Notion property'yi sade Python değerine çevir."""
    if not col_name or col_name not in props:
        return None

    prop = props[col_name]
    ptype = prop.get("type")

    if ptype == "title":
        return "".join([t.get("plain_text", "") for t in prop.get("title", [])]).strip()
    if ptype == "rich_text":
        return "".join([t.get("plain_text", "") for t in prop.get("rich_text", [])]).strip()
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
    """Title tipindeki property'den başlık döndür (mapping yanlış olsa bile)."""
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        s = "".join(t.get("plain_text", "") for t in props[name_col].get("title", []))
        return (s or "").strip() or None
    for p in props.values():
        if p.get("type") == "title":
            s = "".join(t.get("plain_text", "") for t in p.get("title", []))
            s = (s or "").strip()
            if s:
                return s
    return None

def find_letterboxd_url(props: Dict[str, Any]) -> Optional[str]:
    """
    Letterboxd/boxd.it linkini açıkça 'Letterboxd' kolonunda bulamazsak
    tüm başlık/rt/url alanlarının düz metninde ararız.
    """
    text_blobs: List[str] = []
    for p in props.values():
        t = p.get("type")
        if t == "url" and p.get("url"):
            text_blobs.append(str(p["url"]))
        elif t in ("rich_text", "title"):
            text_blobs.extend([r.get("plain_text", "") for r in p.get(t, [])])
    blob = " ".join(text_blobs)
    m = re.search(r"(https?://(?:boxd\.it|letterboxd\.com)/[^\s)]+)", blob)
    return m.group(1) if m else None

# -----------------------------
# Write helpers (Python -> Notion)
# -----------------------------
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url:
        return
    client.pages.update(
        page_id=page_id,
        cover={"type": "external", "external": {"url": url}},
    )

def update_page(page_id: str, data: Dict[str, Any], existing_props: Dict[str, Any] | None = None) -> None:
    """
    Python dict -> Notion properties + cover.
    Director / Writer / Cinematography / Cast Top 3 / Countries / Languages: multi-select
    Poster / Backdrop / Trailer URL: URL
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

    # Multi-select fields
    for k in ("director", "writer", "cinematography", "cast_top", "countries", "languages"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _multi(_as_list(data[k]))

    # Cover from backdrop
    cover_payload = None
    if data.get("backdrop"):
        cover_payload = {"type": "external", "external": {"url": data["backdrop"]}}

    # Final update call
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
# Hedef kolonlar (en az biri boş ise doldurulması gerekenler)
NEED_KEYS = (
    "year", "director", "writer", "cinematography", "runtime",
    "poster", "original_title", "synopsis",
    "countries", "languages", "cast_top", "backdrop", "trailer_url",
)

def iter_pages_needing_fill(limit: int = 200):
    """
    Letterboxd linki olan ve hedef alanlarından en az biri boş olan sayfaları döndürür.
    limit=0 -> limitsiz. Veritabanını sayfalayarak tarar.
    """
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

            # Letterboxd link yoksa atla
            lb = read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb:
                continue

            # En az bir hedef alan boş mu?
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

def iter_all_pages():
    """Veritabanındaki TÜM sayfaları sayfalamayla getirir (örn. toplu cover set için)."""
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

# --- NEW: son düzenlenen/eklenen sayfaları getir (eksik alan şartı yok) ---
def iter_recent_pages(hours: int = 36, limit: int = 50):
    """
    last_edited_time son 'hours' içinde olan sayfaları döndürür.
    limit=0 -> limitsiz. Eksik alan şartı aramaz; Letterboxd linki olanları
    main tarafında filtreleyeceğiz.
    """
    from datetime import datetime, timedelta, timezone

    page_size = 100
    start_cursor = None
    collected: List[Dict[str, Any]] = []

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    base_filter = {
        "filter": {
            "timestamp": "last_edited_time",
            "last_edited_time": {"on_or_after": since}
        }
    }

    while True:
        payload = {"database_id": NOTION_DATABASE_ID, "page_size": page_size, **base_filter}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        start_cursor = resp.get("next_cursor")
        has_more = resp.get("has_more", False)

        for p in pages:
            collected.append(p)
            if limit and len(collected) >= limit:
                return collected

        if not has_more:
            break

    return collected
