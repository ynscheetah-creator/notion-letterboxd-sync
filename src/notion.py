def _as_list(x):
    """str -> ['a','b'] ya da zaten list ise normalize et."""
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return [str(i).strip() for i in x if str(i).strip()]
    # 'A, B , C' -> ['A','B','C']
    return [p.strip() for p in str(x).split(",") if p.strip()]


def update_page(page_id: str, data: dict, existing_props: dict | None = None):
    """
    Python dict -> Notion properties + cover.
    Bu sürüm Director/Writer/Cinematography/CastTop/Countries/Languages alanlarını
    MULTI-SELECT olarak yazar.
    """
    props = {}

    # ---- Numbers ----
    if "year" in data and NOTION_COLS.get("year"):
        props[NOTION_COLS["year"]] = _num(data["year"])
    if "runtime" in data and NOTION_COLS.get("runtime"):
        props[NOTION_COLS["runtime"]] = _num(data["runtime"])

    # ---- Text (rich_text) ----
    for k in ("original_title", "synopsis"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _txt(data[k])

    # ---- URLs ----
    for k in ("poster", "backdrop", "trailer_url"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _url(data[k])

    # ---- MULTI-SELECT alanlar ----
    for k in ("director", "writer", "cinematography", "cast_top", "countries", "languages"):
        if k in data and NOTION_COLS.get(k):
            props[NOTION_COLS[k]] = _multi(_as_list(data[k]))

    # ---- COVER: Backdrop varsa kapak yap ----
    cover_payload = None
    if data.get("backdrop"):
        cover_payload = {"type": "external", "external": {"url": data["backdrop"]}}

    # ---- Notion update ----
    kwargs = {"page_id": page_id}
    if props:
        kwargs["properties"] = props
    if cover_payload:
        kwargs["cover"] = cover_payload

    if len(kwargs) > 1:
        client.pages.update(**kwargs)
        # ---- NEED KEYS: hangi alanlardan en az biri boşsa dolduracağız ----
NEED_KEYS = (
    "year", "director", "writer", "cinematography", "runtime",
    "poster", "original_title", "synopsis",
    "countries", "languages", "cast_top", "backdrop", "trailer_url"
)

def iter_pages_needing_fill(limit: int = 200):
    """
    Letterboxd linki olan ve hedef alanlarından en az biri boş olan sayfaları döndürür.
    Tüm veritabanını taramak için sayfalama (start_cursor) kullanır.
    limit=0 -> limitsiz.
    """
    page_size = 100
    start_cursor = None
    results = []

    while True:
        payload = {"database_id": NOTION_DATABASE_ID, "page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = client.databases.query(**payload)
        pages = resp.get("results", [])
        start_cursor = resp.get("next_cursor")
        has_more = resp.get("has_more", False)

        for page in pages:
            props = page["properties"]

            # Letterboxd linki yoksa atla
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
    """Veritabanındaki TÜM sayfaları sayfalamayla getirir (set-covers gibi işler için)."""
    page_size = 100
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
