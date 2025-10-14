from __future__ import annotations

from notion_client import Client
from typing import Any, Dict, List, Optional

from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# ---------- builders ----------
def _title(val: Optional[str]) -> Dict[str, Any]:
    """Title (Name) property writer."""
    s = (val or "").strip()
    return {"title": [{"type": "text", "text": {"content": s}}]} if s else {"title": []}

def _txt(val: Optional[str]) -> Dict[str, Any]:
    if val is None:
        return {"rich_text": []}
    s = str(val)
    return {"rich_text": [{"type": "text", "text": {"content": s}}]}

def _rich(val: Optional[str]) -> Dict[str, Any]:
    """Alias for _txt - rich text property"""
    return _txt(val)

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

def _multi(items: Optional[List[str]], *, limit: int | None = None) -> Dict[str, Any]:
    arr: List[Dict[str, str]] = []
    if items:
        for it in items:
            name = str(it).strip()
            if name:
                arr.append({"name": name})
                if limit and len(arr) >= limit:
                    break
    return {"multi_select": arr}

def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [p.strip() for p in str(x).split(",") if p.strip()]

# ---------- readers ----------
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
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

def get_page_title(props: dict) -> str | None:
    """Title property'den başlık döndür (mapping yanlışsa da bulur)."""
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        return "".join(t.get("plain_text", "") for t in props[name_col].get("title", [])).strip() or None
    for p in props.values():
        if p.get("type") == "title":
            txt = "".join(t.get("plain_text", "") for t in p.get("title", [])).strip()
            if txt:
                return txt
    return None

# ---------- debug helper ----------
def debug_page_props(props: Dict[str, Any]) -> None:
    """Debug: Bir sayfanın property'lerini yazdır"""
    print("[DEBUG] Page properties:")
    for key, col in NOTION_COLS.items():
        val = read_prop(props, col)
        print(f"  {key:20} ({col:20}): {val}")

# ---------- iterators ----------
def iter_pages_needing_fill(limit: int = 0):
    """
    Letterboxd URL'i olan ama diğer alanları boş olan sayfaları getirir.
    """
    count = 0
    for page in iter_all_pages():
        props = page["properties"]
        
        # Letterboxd URL'i olmalı
        lb_url = read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue
        
        # En az bir alan boş olmalı (doldurulacak bir şey olmalı)
        needs_fill = False
        for key in ["year", "director", "writer", "runtime", "poster"]:
            col = NOTION_COLS.get(key)
            if col and not read_prop(props, col):
                needs_fill = True
                break
        
        if needs_fill:
            yield page
            count += 1
            if limit > 0 and count >= limit:
                break

def iter_recent_pages(force_recent: int = 20, by: str = "created"):
    """
    Veritabanındaki en yeni sayfaları getirir.
    by: "created" -> created_time, "edited" -> last_edited_time
    force_recent: kaç sayfa (en yeni) döndürülsün
    """
    if force_recent <= 0:
        force_recent = 20

    ts = "created_time" if by == "created" else "last_edited_time"

    page_size = 100
    start_cursor = None
    yielded = 0

    while yielded < force_recent:
        payload = {
            "database_id": NOTION_DATABASE_ID,
            "page_size": page_size,
            "sorts": [
                {
                    "timestamp": ts,
                    "direction": "descending",
                }
            ],
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        start_cursor = resp.get("next_cursor")
        has_more = resp.get("has_more", False)

        for page in pages:
            yield page
            yielded += 1
            if yielded >= force_recent:
                return

        if not has_more:
            break

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

# ---------- updates ----------
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url:
        return
    client.pages.update(page_id=page_id, cover={"type": "external", "external": {"url": url}})

def update_page(page_id: str, properties: Dict[str, Any], existing_props: Dict[str, Any] | None = None) -> None:
    """
    Notion sayfasını günceller.
    properties: Zaten Notion formatında hazırlanmış properties dict'i
    """
    if not properties:
        return
    
    # Cover'ı ayrı handle et
    cover_payload = None
    backdrop_col = NOTION_COLS.get("backdrop")
    if backdrop_col and backdrop_col in properties:
        backdrop_data = properties[backdrop_col]
        if backdrop_data.get("url"):
            cover_payload = {"type": "external", "external": {"url": backdrop_data["url"]}}
    
    kwargs: Dict[str, Any] = {"page_id": page_id}
    if properties:
        kwargs["properties"] = properties
    if cover_payload:
        kwargs["cover"] = cover_payload
    
    if len(kwargs) > 1:
        try:
            client.pages.update(**kwargs)
        except Exception as e:
            print(f"[error] Failed to update page {page_id}: {e}")
