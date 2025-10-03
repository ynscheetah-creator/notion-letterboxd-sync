import argparse
from dotenv import load_dotenv
from .config import NOTION_COLS, DEFAULT_LIMIT
from . import notion as nz
from . import letterboxd as lb
from . import omdb
from . import tmdb

def is_empty(val):
    return val is None or (isinstance(val, str) and not val.strip())

def compose_update(existing_props, fetched):
    out = {}
    for key in ("year", "runtime", "director", "writer", "cinematography", "poster"):
        if fetched.get(key) is not None and fetched.get(key) != "":
            out[key] = fetched[key]
    return out

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    rows = nz.iter_pages_needing_fill(limit=args.limit)
    prop = NOTION_COLS

    updated = 0
    for page in rows:
        pid = page["id"]
        props = page["properties"]
        url = nz.read_prop(props, prop["letterboxd"])
        title_notion = nz.read_prop(props, prop["title"])
        year_notion = nz.read_prop(props, prop["year"])

        need_any = any(is_empty(nz.read_prop(props, prop[k])) for k in ("year","director","writer","cinematography","runtime","poster"))
        if not need_any and not args.overwrite:
            continue
        if not url and not title_notion:
            continue

        try:
            ids = lb.extract_ids(url) if url else {"title": None, "year": None, "imdb_id": None}
        except Exception as e:
            print(f"[skip] {title_notion or url}: letterboxd error: {e}")
            ids = {"title": None, "year": None, "imdb_id": None}

        fetched = {}

        imdb_from_lb = ids.get("imdb_id")
        title_from_lb = ids.get("title")
        year_from_lb  = ids.get("year")

        try:
            year_notion = int(year_notion) if year_notion is not None else None
        except Exception:
            year_notion = None

        # 1) IMDb -> OMDb
        if imdb_from_lb:
            data = omdb.get_by_imdb(imdb_from_lb)
            if data:
                fetched = data

        # 2) IMDb -> TMDb
        if not fetched and imdb_from_lb:
            data = tmdb.get_by_imdb(imdb_from_lb)
            if data:
                fetched = data

        # 3) Başlık+yıl -> OMDb (önce LB, sonra Notion)
        if not fetched and (title_from_lb or year_from_lb):
            data = omdb.get_by_title(title_from_lb or "", year_from_lb)
            if data:
                fetched = data

        if not fetched and title_notion:
            data = omdb.get_by_title(title_notion, year_notion)
            if data:
                fetched = data

        if not fetched:
            print(f"[skip] {title_notion or url}: no data found")
            continue

        payload = compose_update(props, fetched)
        if not payload:
            continue

        if args.dry_run:
            print(f"[dry] Would update {title_notion or url}: {payload}")
        else:
            nz.update_page(pid, payload)
            print(f"[ok] Updated {title_notion or url}: {payload}")
            updated += 1

    print(f"Done. Updated {updated} pages.")

if __name__ == "__main__":
    main()
