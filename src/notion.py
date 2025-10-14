from __future__ import annotations
from typing import Any, Dict, List, Optional
from notion_client import Client
from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

# -------- writers
def _txt(val: Optional[str]) -> Dict[str, Any]:
    if not val: return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": str(val)}}]}

def _num(val: Optional[Any]) -> Dict[str, Any]:
    if val in (None, ""): return {"number": None}
    try: return {"number": int(val)}
    except Exception:
        try: return {"number": float(val)}
        except Exception: return {"number": None}

def _url(val: Optional[str]) -> Dict[str, Any]:
    return {"url": (str(val) if val else None)}

def _multi(items: Optional[List[str]], limit: int | None = None) -> Dict[str, Any]:
    """
    Build a Notion multi_select payload from a list of names.
    - Boşları ve tekrarları eler.
    - `limit` verilirse (örn 100) en fazla o kadar seçenek döner (Notion limiti).
    """
    arr: List[Dict[str, str]] = []
    if items:
        seen: set[str] = set()
        for it in items:
            name = str(it).strip()
            if not name or name in seen:
                continue
            arr.append({"name": name})
            seen.add(name)
            if limit and len(arr) >= limit:
                break
    return {"multi_select": arr}
# -------- readers
def read_prop(props: Dict[str, Any], col_name: Optional[str]) -> Any:
    if not col_name or col_name not in props: return None
    p = props[col_name]; t = p.get("type")
    if t == "title":
        return "".join(x.get("plain_text","") for x in p.get("title",[])).strip()
    if t == "rich_text":
        return "".join(x.get("plain_text","") for x in p.get("rich_text",[])).strip()
    if t == "number": return p.get("number")
    if t == "url": return p.get("url")
    if t == "multi_select": return [o.get("name","") for o in p.get("multi_select",[])]
    if t == "files":
        f = (p.get("files") or [None])[0] or {}
        if f.get("type") == "external": return (f.get("external") or {}).get("url")
        if f.get("type") == "file": return (f.get("file") or {}).get("url")
        return None
    return None

def get_page_title(props: dict) -> str | None:
    name_col = NOTION_COLS.get("name")
    if name_col and name_col in props and props[name_col].get("type")=="title":
        txt = "".join(t.get("plain_text","") for t in props[name_col].get("title",[])).strip()
        if txt: return txt
    for p in props.values():
        if p.get("type")=="title":
            txt = "".join(t.get("plain_text","") for t in p.get("title",[])).strip()
            if txt: return txt
    return None

# -------- updates
def update_cover(page_id: str, url: Optional[str]) -> None:
    if not url: return
    client.pages.update(page_id=page_id, cover={"type":"external","external":{"url":url}})
# --- Yardımcı: Multi-select listelerini güvenli biçimde oluştur ---
def _multi(items: list[str], limit: int = 100) -> dict:
    """
    Notion multi_select alanına güvenli biçimde liste verir.
    Maksimum 100 etiketi aşmaz, tekrarlardan kaçınır.
    """
    uniq = []
    seen = set()
    for it in items:
        name = str(it).strip()
        if not name or name in seen:
            continue
        uniq.append({"name": name})
        seen.add(name)
        if len(uniq) >= limit:
            break
    return {"multi_select": uniq}
def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    return [p.strip() for p in str(x).split(",") if p.strip()]

def _multi(items: Optional[List[str]], limit: int | None = None) -> Dict[str, Any]:
    """
    Notion multi_select payload. Boşları ve tekrarları eler.
    limit verilirse en fazla o kadar seçenek döner (Notion limiti genelde 100).
    """
    arr: List[Dict[str, str]] = []
    if items:
        seen: set[str] = set()
        for it in items:
            name = str(it).strip()
            if not name or name in seen:
                continue
            arr.append({"name": name})
            seen.add(name)
            if limit and len(arr) >= limit:
                break
    return {"multi_select": arr}

def update_page(page_id: str, data: Dict[str, Any], existing_props: Dict[str, Any] | None = None) -> None:
    """
    Python dict -> Notion properties + cover.
    Multi-select: director/writer/cinematography/cast_top/countries/languages + MUBI
    URL: poster/backdrop/trailer_url
    Number: year/runtime
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

    # Multi-select (standart alanlar)
    for k in ("director", "writer", "cinematography", "cast_top", "countries", "languages"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _multi(_as_list(data[k]))

    # MUBI (ülke kodları multi-select) — Notion sınırı için limit=100
    if "mubi" in data and NOTION_COLS.get("mubi"):
        props[NOTION_COLS["mubi"]] = _multi(_as_list(data["mubi"]), limit=100)

    # Cover: backdrop varsa kapak yap
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

# -------- queries
def iter_recent_pages(force_recent: int = 50, by: str = "edited"):
    """
    Son N sayfayı getir (varsayılan editedTime). by='created' dersen CreatedTime'a göre.
    """
    sorts = [{
        "property": "last_edited_time" if by!="created" else "created_time",
        "direction": "descending",
    }]
    payload = {"database_id": NOTION_DATABASE_ID, "sorts": sorts, "page_size": force_recent}
    resp = client.databases.query(**payload)
    return resp.get("results", [])
# --- Tüm sayfaları sayfalayarak döndür (MUBI taraması vb. için) ---
def iter_all_pages(page_size: int = 100):
    """
    Veritabanındaki TÜM sayfaları döndürür.
    Notion pagination (start_cursor) kullanır.
    """
    start_cursor = None
    while True:
        payload = {"database_id": NOTION_DATABASE_ID, "page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = client.databases.query(**payload)

        for page in resp.get("results", []):
            yield page

        if not resp.get("has_more"):
            break
        start_cursor = resp.get("next_cursor")
