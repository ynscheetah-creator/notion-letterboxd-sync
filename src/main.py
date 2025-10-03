import argparse
from dotenv import load_dotenv
from .config import NOTION_COLS, DEFAULT_LIMIT
from . import notion as nz
from . import letterboxd as lb
from . import omdb

def is_empty(val):
    return val is None or (isinstance(val, str) and not val.strip())

def compose_update(existing_props, fetched):
    out = {}
    for key in ("year", "runtime", "director", "writer", "cinematography", "poster"):
        if fetched.get(key) not in (None, ""):
            out[key] = fetched[key]
    return out

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    print("[debug] starting...", flush=True)
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows from Notion with a Letterboxd URL filter", flush=True)

    prop = NOTION_COLS
    updated = 0

    for idx, page in enumerate(rows, start=1):
        pid = page["id"]
        props = page["properties"]
        url   = nz.read_prop(props, prop["letterboxd"])
        name  = nz.read_prop(props, prop["title"])
        year0 = nz.read_prop(props, prop["year"])

        # hangi alanlar boş?
        needs = {k: is_empty(nz.read_prop(props, prop[k])) for k in ("year","director","writer","cinematography","runtime","poster")}
        print(f"[debug] row {idx}: name='{name}' url='{url}' needs={needs}", flush=True)

        need_any = any(needs.values())
        if not need_any and not args.overwrite:
            print(f"[debug] row {idx}: nothing needed, skipping", flush=True)
            continue

        title_guess = None
        year_guess = None

        # 1) boxd.it -> slug'tan title üret
        if url:
            try:
                ids = lb.from_boxd(url)
                title_guess = ids.get("title") or title_guess
                year_guess  = ids.get("year") or year_guess
                print(f"[debug] row {idx}: title from boxd.it = {title_guess!r}, year={year_guess}", flush=True)
            except Exception as e:
                print(f"[debug] row {idx}: letterboxd error: {e}", flush=True)

        # 2) Notion Name/Year fallback
        if not title_guess and name:
            title_guess = name
        try:
            if not year_guess and year0 is not None:
                year_guess = int(year0)
        except Exception:
            year_guess = None

        if not title_guess:
            print(f"[debug] row {idx}: no title to query → skip", flush=True)
            continue

        data = omdb.get_by_title(title_guess, year_guess)
        if not data:
            print(f"[debug] row {idx}: OMDb no data for title='{title_guess}' year={year_guess}", flush=True)
            continue

        payload = compose_update(props, data)
        print(f"[debug] row {idx}: payload={payload}", flush=True)
        if not payload:
            continue

        if args.dry_run:
            print(f"[dry] Would update {name or title_guess}: {payload}", flush=True)
        else:
            nz.update_page(pid, payload)
            print(f"[ok] Updated {name or title_guess}: {payload}", flush=True)
            updated += 1

    print(f"Done. Updated {updated} pages.", flush=True)

if __name__ == "__main__":
    main()
