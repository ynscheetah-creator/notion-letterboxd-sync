from __future__ import annotations

import argparse
import time
from typing import Dict, Any, Optional, List

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS

# ------------ small utils
def _merge(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    if not src:
        return
    for k, v in src.items():
        if v in (None, "", [], {}):
            continue
        dst[k] = v

def _payload_from_omdb(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d:
        return {}
    return {
        "year": d.get("year"),
        "runtime": d.get("runtime"),
        "director": d.get("director"),
        "writer": d.get("writer"),
        "cinematography": d.get("cinematography"),
        "poster": d.get("poster"),
        "original_title": d.get("original_title") or d.get("title"),
        "synopsis": d.get("synopsis"),
        "countries": d.get("countries"),
        "languages": d.get("languages"),
        "cast_top": d.get("cast_top"),
    }

def _payload_from_tmdb(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d:
        return {}
    return {
        "year": (int(d["year"]) if d.get("year") else None),
        "runtime": d.get("runtime"),
        "poster": d.get("poster"),
        "original_title": d.get("original_title") or d.get("title"),
        "synopsis": d.get("synopsis"),
        "backdrop": d.get("backdrop"),
    }

# ------------ main modes
def mode_fill_missing(args):
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows")

    updated = 0
    for idx, page in enumerate(rows, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        # title/year/ids
        title_guess = None
        year_guess = None
        imdb_id = None
        tmdb_id = None

        try:
            meta = lb.parse(lb_url)
        except Exception:
            meta = {}

        if isinstance(meta, dict):
            title_guess = meta.get("title")
            year_guess = meta.get("year")
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        if not title_guess:
            title_guess = nz.get_page_title(props)

        print(f"[debug] row {idx}: title='{title_guess}' url='{lb_url}'")

        payload: Dict[str, Any] = {}

        # OMDb → TMDb merge
        try:
            if imdb_id and hasattr(omdb, "get_by_imdb"):
                _merge(payload, _payload_from_omdb(omdb.get_by_imdb(imdb_id)))
            elif title_guess:
                _merge(payload, _payload_from_omdb(omdb.get_by_title(title_guess, year_guess)))
        except Exception:
            pass

        try:
            if tmdb_id:
                _merge(payload, _payload_from_tmdb(tmdb.get_by_id(tmdb_id)))
            elif title_guess:
                _merge(payload, _payload_from_tmdb(tmdb.get_by_title(title_guess, year_guess)))
        except Exception:
            pass

        if not payload:
            print(f"[skip] {title_guess}: no data found")
            continue

        if args.dry_run:
            print(f"[dry] Would update {title_guess}: {payload}")
        else:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            time.sleep(0.2)

    print(f"Done. Updated {updated} pages.")

def mode_set_covers(args):
    print("[cover] Setting missing covers from Backdrop...", flush=True)
    scanned = 0
    fixed = 0
    for page in nz.iter_all_pages():
        scanned += 1
        props = page["properties"]
        backdrop = nz.read_prop(props, NOTION_COLS.get("backdrop"))
        current_cover = page.get("cover")
        if backdrop and current_cover is None:
            if not args.dry_run:
                nz.update_cover(page["id"], backdrop)
            fixed += 1
            time.sleep(0.15)
    print(f"[cover] Done. Scanned={scanned}, set={fixed}")

def mode_force_recent(args):
    N = args.force_recent
    by = "created"
    pages = nz.iter_recent_pages(force_recent=N, by=by)
    print(f"Running recent sync (last {N})")

    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        current_title = nz.get_page_title(props) or ""
        need_title = (not current_title or current_title.lower() == "new page")

        title_guess = None
        year_guess = None
        imdb_id = None
        tmdb_id = None

        try:
            meta = lb.parse(lb_url)
        except Exception:
            meta = {}

        if isinstance(meta, dict):
            title_guess = meta.get("title") or (current_title if need_title else current_title)
            year_guess = meta.get("year")
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        payload: Dict[str, Any] = {}

        try:
            if imdb_id:
                _merge(payload, _payload_from_omdb(omdb.get_by_imdb(imdb_id)))
            elif title_guess:
                _merge(payload, _payload_from_omdb(omdb.get_by_title(title_guess, year_guess)))
        except Exception:
            pass

        try:
            if tmdb_id:
                _merge(payload, _payload_from_tmdb(tmdb.get_by_id(tmdb_id)))
            elif title_guess:
                _merge(payload, _payload_from_tmdb(tmdb.get_by_title(title_guess, year_guess)))
        except Exception:
            pass

        if not payload:
            continue

        if args.dry_run:
            print(f"[dry] Would update recent {idx}: {payload}")
        else:
            nz.update_page(pid, payload, existing_props=props)
            time.sleep(0.2)

    print(f"Done. Updated {len(pages)} pages.")

def mode_refresh_mubi(args):
    if args.refresh_mubi not in ("all", "recent"):
        print("Bad --refresh-mubi argument; use 'all' or 'recent'")
        return

    if args.refresh_mubi == "all":
        pages_iter = nz.iter_all_pages()
        print("Refreshing MUBI for ALL pages (daily run)")
    else:
        N = args.mubi_recent or 300
        pages_iter = nz.iter_recent_pages(force_recent=N, by="edited")
        print(f"Refreshing MUBI for RECENT pages (last {N})")

    updated = 0
    for page in pages_iter:
        props = page["properties"]
        pid = page["id"]
        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        # LB → TMDb id
        tmdb_id = None
        try:
            meta = lb.parse(lb_url)
            tmdb_id = meta.get("tmdb_id")
        except Exception:
            pass

        if not tmdb_id:
            # son çare: isim/yıl ara
            title_guess = nz.get_page_title(props) or None
            year_guess = nz.read_prop(props, NOTION_COLS.get("year"))
            if title_guess:
                try:
                    maybe = tmdb.get_by_title(title_guess, year_guess)
                    # get_by_title zaten geri get_by_id çağırıyor; tmdb_id tutmuyoruz ama provider için id gerekmez (bize yok)
                    # provider için id lazım olduğundan bir daha ara:
                    # basit çözüm: tekrar search yapıp first id
                    # (performans yeterli)
                    pass
                except Exception:
                    pass

        # provider regions
        regions: List[str] = []
        try:
            if tmdb_id:
                regions = tmdb.get_providers_mubi(tmdb_id)
        except Exception:
            regions = []

        if args.dry_run:
            print(f"[dry] Would set MUBI={regions} for page {pid}")
        else:
            nz.update_page(pid, {"mubi": regions}, existing_props=props)
            updated += 1
            time.sleep(0.2)

    print(f"[mubi] updated {updated} page(s).")

# ------------ CLI
def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="İşlenecek satır sayısı (fill-missing). 0=limitsiz")
    ap.add_argument("--dry-run", action="store_true")

    ap.add_argument("--set-covers", action="store_true", help="Backdrop URL’lerini cover olarak ayarla (tek seferlik)")
    ap.add_argument("--force-recent", type=int, default=0, metavar="N", help="Son N sayfayı doldurmaya zorla")

    # MUBI
    ap.add_argument("--refresh-mubi", choices=["all", "recent"], help="MUBI mevcudiyetini yenile")
    ap.add_argument("--mubi-recent", type=int, default=300, help="--refresh-mubi recent için N (default 300)")

    args = ap.parse_args()

    print("[debug] starting...")

    if args.set_covers:
        return mode_set_covers(args)

    if args.refresh_mubi:
        return mode_refresh_mubi(args)

    if args.force_recent and args.force_recent > 0:
        return mode_force_recent(args)

    return mode_fill_missing(args)

if __name__ == "__main__":
    main()
