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
