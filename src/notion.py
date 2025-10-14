# src/notion.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from notion_client import Client

from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# -----------------------------
# Write helpers
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
    arr = []
    if items:
        for it in items:
            name = str(it).strip()
            if name:
                arr.append({"name": name})
    return {"multi_select": arr}


def _as_list(x: Any) -> List[str]:
    """'A, B , C' -> ['A','B','C'] ya da zaten list ise normalize et."""
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [p.strip() for p in str(x).split(",") if p.strip()]


# -----------------------------
# Read helpers
# -----------------------------
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
    """Notion property'yi sade Python değerine çevir."""
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
    """Title tipi property'den sayfa başlığını döndürür (mapping bozuksa bile)."""
    # Önce mapping ile
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type") == "title":
        txt = "".join(t.get("plain_text", "") for t in props[name_col].get("title", [])).strip()
        if txt:
            return txt
    # Bütün property'leri tara
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
    client.pages.update(
        page_id=page_id,
        cover={"type": "external", "external": {"url": url}},
    )


def update_page(page_id: str, data: Dict[str, Any], existing_props: Dict[str, Any] | None = None) -> None:
    """
    Python dict -> Notion properties + cover.
    Director / Writer / Cinematography / Cast Top 3 / Countries / Languages multi-select;
    Poster / Backdrop / Trailer URL ise URL'dür.
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
NEED_KEYS = (
    "year", "director", "writer", "cinematography", "runtime",
    "poster", "original_title", "synopsis",
    "countries", "languages", "cast_top", "backdrop", "trailer_url",
)


def _page_needs_fill(page: Dict[str, Any]) -> bool:
    """Hedef alanlardan en az biri boşsa True."""
    props = page["properties"]
    # Letterboxd linki yoksa boş sayfalara dokunma
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


def iter_pages_needing_fill(limit: int = 200) -> List[Dict[str, Any]]:
    """Veritabanını sayfalayarak, eksik alanı olan sayfaları getirir."""
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
            if _page_needs_fill(page):
                results.append(page)
                if limit and len(results) >= limit:
                    return results

        if not has_more:
            break

    return results


def iter_recent_pages(recent_count: int = 200, limit: int = 0) -> List[Dict[str, Any]]:
    """
    Son eklenen/edite edilen sayfalardan recent_count kadarını getirir.
    Sadece link olan 'yeni' satırların da çekilmesi için kullanılır.
    """
    # Notion query API'de "created_time" sort'u kullanarak sonları çekiyoruz
    payload: Dict[str, Any] = {
        "database_id": NOTION_DATABASE_ID,
        "page_size": min(100, max(1, recent_count)),
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
    }
    resp = client.databases.query(**payload)
    pages = resp.get("results", [])

    # İkinci sayfa vs gerekirse (recent_count > 100 ise) devamını da al
    results: List[Dict[str, Any]] = []
    results.extend(pages)
    next_cursor = resp.get("next_cursor")
    fetched = len(results)
    while fetched < recent_count and resp.get("has_more"):
        payload["start_cursor"] = next_cursor
        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        results.extend(pages)
        fetched = len(results)
        next_cursor = resp.get("next_cursor")
        if not resp.get("has_more"):
            break

    if limit and len(results) > limit:
        results = results[:limit]
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
