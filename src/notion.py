from typing import Dict, Any, List, Optional
from notion_client import Client
from .config import NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_COLS

client = Client(auth=NOTION_TOKEN)

def iter_pages_needing_fill(limit: int = 100) -> List[Dict[str, Any]]:
    db_id = NOTION_DATABASE_ID
    prop = NOTION_COLS

    # Query pages where Letterboxd URL exists
    has_url_filter = {
        "property": prop["letterboxd"],
        "url": {"is_not_empty": True}
    }

    # We don't set complex "any empty" filter, just fetch and filter in Python
    results = []
    cursor = None
    while True:
        resp = client.databases.query(
            **({"start_cursor": cursor} if cursor else {}),
            database_id=db_id,
            page_size=min(100, limit - len(results)),
            filter=has_url_filter,
            sorts=[{"property": prop["title"], "direction": "ascending"}]
        )
        results.extend(resp["results"])
        cursor = resp.get("next_cursor")
        if not cursor or len(results) >= limit:
            break
    return results

def read_prop(props: Dict[str, Any], name: str) -> Any:
    p = props.get(name)
    if not p:
        return None
    t = p["type"]
    if t == "title":
        return "".join([x["plain_text"] for x in p["title"]])
    if t == "url":
        return p["url"]
    if t == "number":
        return p["number"]
    if t == "rich_text":
        return "".join([x["plain_text"] for x in p["rich_text"]])
    return None

def update_page(page_id: str, data: Dict[str, Any]):
    prop = NOTION_COLS
    payload = {"properties": {}}

    if "year" in data and data["year"] is not None:
        payload["properties"][prop["year"]] = {"number": int(data["year"])}

    if "runtime" in data and data["runtime"] is not None:
        payload["properties"][prop["runtime"]] = {"number": int(data["runtime"])}

    if "director" in data and data["director"]:
        payload["properties"][prop["director"]] = {"rich_text": [{"text": {"content": data["director"]}}]}

    if "writer" in data and data["writer"]:
        payload["properties"][prop["writer"]] = {"rich_text": [{"text": {"content": data["writer"]}}]}

    if "cinematography" in data and data["cinematography"]:
        payload["properties"][prop["cinematography"]] = {"rich_text": [{"text": {"content": data["cinematography"]}}]}

    if "poster" in data and data["poster"]:
        payload["properties"][prop["poster"]] = {"url": data["poster"]}

    if payload["properties"]:
        client.pages.update(page_id=page_id, **payload)
