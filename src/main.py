# src/main.py (ilgili importların yukarıda olduğundan emin olun)
from . import notion as nz
from . import letterboxd as lb
from . import tmdb
from .config import NOTION_COLS

def refresh_mubi_all():
    print("[mubi] refreshing MUBI regions for ALL pages")
    updated = 0

    for page in nz.iter_all_pages():
        props = page["properties"]
        pid   = page["id"]

        # Kriter: Letterboxd linki olmalı
        url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not url:
            continue

        # Var olan TMDb id
        tmdb_id = nz.read_prop(props, NOTION_COLS.get("tmdb_id"))

        # Gerekirse LB parse
        if not tmdb_id:
            try:
                meta = lb.parse(url)  # {'tmdb_id', 'title', 'year', ...}
            except Exception:
                meta = {}
            tmdb_id = meta.get("tmdb_id")

        # Gerekirse search (title/year ile)
        if not tmdb_id:
            title = nz.get_page_title(props) or ""
            year  = nz.read_prop(props, NOTION_COLS.get("year"))
            tmdb_id = tmdb.search_movie_id(title, year)

        if not tmdb_id:
            # hâlâ yoksa atla
            continue

        # MUBI bölgeleri
        regions = tmdb.get_mubi_regions(tmdb_id)
        if not regions:
            # yoksa temizle (isterseniz pas geçebilirsiniz)
            nz.update_page(pid, { "mubi": [] }, existing_props=props)
            continue

        # Notion’a yaz (100 limitli multi-select)
        nz.update_page(pid, { "mubi": regions }, existing_props=props)
        updated += 1

    print(f"[mubi] done. Updated {updated} pages.")
