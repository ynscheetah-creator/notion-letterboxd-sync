import argparse
import time
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
    simple_keys = (
        "year", "runtime", "director", "writer", "cinematography",
        "poster", "original_title", "synopsis", "cast_top", "backdrop", "trailer_url"
    )
    for key in simple_keys:
        if fetched.get(key) not in (None, ""):
            out[key] = fetched[key]
    if fetched.get("countries"):
        out["countries"] = fetched["countries"]
    if fetched.get("languages"):
        out["languages"] = fetched["languages"]
    return out


def main():
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="0/specified → üst limit; boşsa config’teki")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    print("[debug] starting...", flush=True)
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows", flush=True)

    prop = NOTION_COLS
    updated = 0

for idx, page in enumerate(rows, start=1):
    time.sleep(0.5)  # ~2 istek/sn, Notion için güvenli

        pid = page["id"]
        props = page["properties"]
        url   = nz.read_prop(props, prop["letterboxd"])
        name  = nz.read_prop(props, prop["title"])
        year0 = nz.read_prop(props, prop["year"])

        needs = {k: is_empty(nz.read_prop(props, prop[k])) for k in (
            "year","director","writer","cinematography","runtime",
            "poster","original_title","synopsis","countries","languages","cast_top","backdrop","trailer_url"
        ) if k in prop}
        print(f"[debug] row {idx}: name={name!r} url={url!r} needs={needs}", flush=True)

        if not any(needs.values()) and not args.overwrite:
            continue

        title_guess, year_guess = None, None

        if url:
            try:
                ids = lb.from_boxd(url)
                title_guess = ids.get("title") or title_guess
                year_guess  = ids.get("year")  or year_guess
            except Exception as e:
                print(f"[debug] lb error: {e}", flush=True)

        if not title_guess and name:
            title_guess = name
        try:
            if not year_guess and year0 is not None:
                year_guess = int(year0)
        except Exception:
            year_guess = None

        if not title_guess:
            print(f"[debug] row {idx}: no title to query", flush=True)
            continue

        fetched = omdb.get_by_title(title_guess, year_guess)
        if not fetched:
            print(f"[debug] OMDb miss for {title_guess!r} ({year_guess})", flush=True)
            fetched = tmdb.get_by_title(title_guess, year_guess)
            if not fetched:
                print(f"[debug] TMDb miss for {title_guess!r} ({year_guess})", flush=True)

        if not fetched:
            print(f"[skip] {name or title_guess}: no data found", flush=True)
            continue

        payload = compose_update(props, fetched)
        print(f"[debug] payload={payload}", flush=True)
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
