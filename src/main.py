import argparse
import time
import os
from dotenv import load_dotenv

from .config import NOTION_COLS, DEFAULT_LIMIT
from . import notion as nz
from . import letterboxd as lb
from . import omdb
from . import tmdb


def is_empty(val):
    return val is None or (isinstance(val, str) and not val.strip())


def compose_update(existing_props, fetched):
    """
    TMDb/OMDb'den gelen veriyi Notion property payload'ına uygun
    sade bir dict'e dönüştürür. (Gerçek dönüşüm notion.py'de yapılır.)
    """
    out = {}
    # Düz metin / sayı / url alanlar
    simple_keys = (
        "year", "runtime", "director", "writer", "cinematography",
        "poster", "original_title", "synopsis", "cast_top", "backdrop", "trailer_url"
    )
    for key in simple_keys:
        if fetched.get(key) not in (None, ""):
            out[key] = fetched[key]

    # Multi-select alanlar
    if fetched.get("countries"):
        out["countries"] = fetched["countries"]
    if fetched.get("languages"):
        out["languages"] = fetched["languages"]

    return out


def main():
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="işlenecek maksimum sayfa (0=limitsiz)")
    ap.add_argument("--dry-run", action="store_true", help="Notion'a yazmadan sadece ne olacağını göster")
    ap.add_argument("--overwrite", action="store_true", help="dolu alanları da tazeler")
    args = ap.parse_args()

    print("[debug] starting...", flush=True)
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows", flush=True)

    prop = NOTION_COLS
    updated = 0

    for idx, page in enumerate(rows, start=1):
        # --- RATE LIMIT KALKANI ---
        time.sleep(0.2)  # ~5 istek/sn; gerekirse 0.5'e çıkarabilirsin

        pid = page["id"]
        props = page["properties"]

        url = nz.read_prop(props, prop["letterboxd"])
        name = nz.read_prop(props, prop["title"])
        year0 = nz.read_prop(props, prop["year"])

        needs = {
            k: is_empty(nz.read_prop(props, prop[k]))
            for k in ("year", "director", "writer", "cinematography", "runtime",
                      "poster", "original_title", "synopsis", "countries",
                      "languages", "cast_top", "backdrop", "trailer_url")
            if k in prop
        }
        print(f"[debug] row {idx}: name={name!r} url={url!r} needs={needs}", flush=True)

        need_any = any(needs.values())
        if not need_any and not args.overwrite:
            continue

        # ---- Başlık/Yıl kestirimi ----
        title_guess = None
        year_guess = None

        # 1) boxd.it -> slug'tan başlık
        if url:
            try:
                ids = lb.from_boxd(url)
                title_guess = ids.get("title") or title_guess
                year_guess = ids.get("year") or year_guess
            except Exception as e:
                print(f"[debug] letterboxd redirect error: {e}", flush=True)

        # 2) Notion Name/Year fallback
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

        # ---- Veri çekme (önce OMDb, olmazsa TMDb) ----
        fetched = None

        # OMDb (çoğu zaman yeterli, ama limit/başlık eşleşmesi şaşabiliyor)
        fetched = omdb.get_by_title(title_guess, year_guess)
        if not fetched:
            print(f"[debug] OMDb miss for {title_guess!r} ({year_guess})", flush=True)

        # TMDb (daha güçlü arama + ekstra alanlar: synopsis, cast top, backdrop, trailer vs.)
        if not fetched:
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
