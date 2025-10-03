import os, argparse
from dotenv import load_dotenv
from .config import NOTION_COLS, DEFAULT_LIMIT
from . import notion as nz
from . import letterboxd as lb
from . import omdb
from . import tmdb

def is_empty(val):
    return val is None or (isinstance(val, str) and not val.strip())

def compose_update(existing, fetched):
    # Do not overwrite existing unless --overwrite
    out = {}
    for key in ("year", "runtime", "director", "writer", "cinematography", "poster"):
        if fetched.get(key) is not None:
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
        title = nz.read_prop(props, prop["title"])

        # determine if update needed
        need_any = any(is_empty(nz.read_prop(props, prop[k])) for k in ("year","director","writer","cinematography","runtime","poster"))
        if not need_any and not args.overwrite:
            continue

        if not url:
            continue

        try:
            ids = lb.extract_ids(url)
        except Exception as e:
            print(f"[skip] {title}: letterboxd error: {e}")
            continue

        fetched = {}
        if ids.get("imdb_id"):
            data = omdb.get_by_imdb(ids["imdb_id"])
            if data:
                fetched = data
        # Fallback to TMDb
        if not fetched:
            data = tmdb.get_by_imdb(ids.get("imdb_id", "")) if ids.get("imdb_id") else None
            if data:
                fetched = data

        if not fetched:
            print(f"[skip] {title}: no data found for {url}")
            continue

        payload = compose_update(props, fetched)
        if not payload:
            continue

        if args.dry_run:
            print(f"[dry] Would update {title}: {payload}")
        else:
            nz.update_page(pid, payload)
            print(f"[ok] Updated {title}: {payload}")
            updated += 1

    print(f"Done. Updated {updated} pages.")

if __name__ == "__main__":
    main()
