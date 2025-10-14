# src/main.py
from __future__ import annotations

import argparse
import time
from typing import Dict, Any, Optional, Iterable

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS


# -----------------------
# helpers / normalizers
# -----------------------
def _merge_payload(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    """Copy only truthy keys from src to dst (keeps zeros for numbers)."""
    if not src:
        return
    for k, v in src.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            continue
        if isinstance(v, str) and v.strip() == "":
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
        "synopsis": d.get("plot") or d.get("synopsis"),
        "countries": d.get("countries"),
        "languages": d.get("languages"),
        "cast_top": d.get("cast_top"),
        "backdrop": d.get("backdrop"),
        "trailer_url": d.get("trailer_url"),
    }


def _payload_from_tmdb(d: Dict[str, Any]) -> Dict[str, Any]:
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
        "synopsis": d.get("overview") or d.get("synopsis"),
        "countries": d.get("countries"),
        "languages": d.get("languages"),
        "cast_top": d.get("cast_top"),
        "backdrop": d.get("backdrop"),
        "trailer_url": d.get("trailer_url"),
    }


# -----------------------
# core flows
# -----------------------
def _fill_missing_for_pages(pages: Iterable[dict], *, dry: bool = False) -> int:
    """
    Fill missing fields for the given Notion page iterator.
    Returns how many pages were updated.
    """
    updated = 0

    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        # Letterboxd URL is the anchor
        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        # Try to guess title/year from LB (fast, reliable with JSON-LD)
        title_guess = None
        year_guess = None
        imdb_id = None
        tmdb_id = None

        try:
            meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
        except Exception:
            meta = None

        if isinstance(meta, dict):
            title_guess = meta.get("title")
            year_guess = meta.get("year")
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        if not title_guess:
            # fallback to existing Name (title property)
            title_guess = nz.get_page_title(props) or ""

        print(f"[debug] row {idx}: title='{title_guess}' url='{lb_url}'")

        # Build payload from sources
        payload: Dict[str, Any] = {}

        # (1) OMDb first (if we have IMDb id, use it; otherwise title/year)
        try:
            if imdb_id and hasattr(omdb, "get_by_imdb"):
                o = omdb.get_by_imdb(imdb_id)
            elif title_guess and hasattr(omdb, "get_by_title"):
                o = omdb.get_by_title(title_guess, year_guess)
            else:
                o = None
        except Exception:
            o = None
        _merge_payload(payload, _payload_from_omdb(o))

        # (2) TMDb as fallback / complement
        need_any = any(
            k not in payload
            for k in (
                "year",
                "director",
                "writer",
                "cinematography",
                "runtime",
                "poster",
                "backdrop",
            )
        )
        if need_any:
            try:
                if tmdb_id and hasattr(tmdb, "get_by_id"):
                    t = tmdb.get_by_id(tmdb_id)
                elif title_guess and hasattr(tmdb, "get_by_title"):
                    t = tmdb.get_by_title(title_guess, year_guess)
                else:
                    t = None
            except Exception:
                t = None
            _merge_payload(payload, _payload_from_tmdb(t))

        if not payload:
            print(f"[skip] {title_guess or '(no title)'}: no data found")
            continue

        if dry:
            print(f"[dry] Would update {title_guess}: {payload}")
        else:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            time.sleep(0.20)  # be gentle with Notion API

    return updated


def _refresh_mubi_for_pages(pages: Iterable[dict], *, dry: bool = False) -> int:
    """
    For each page, resolve TMDb id from Letterboxd and update the MUBI regions
    multi-select (ISO 3166-1 alpha-2 codes) using TMDb 'watch/providers' API.
    """
    updated = 0

    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        title = nz.get_page_title(props) or "(untitled)"
        print(f"[mubi] checking: {title}")

        tmdb_id = None
        try:
            meta = lb.parse(lb_url)
            if isinstance(meta, dict):
                tmdb_id = meta.get("tmdb_id")
        except Exception:
            tmdb_id = None

        if not tmdb_id:
            print(f"[mubi]  -> no TMDb id, skip")
            continue

        try:
            regions = tmdb.get_mubi_regions(tmdb_id)  # returns ['DE', 'TR', ...]
        except Exception as e:
            print(f"[mubi]  providers error ({lb_url}): {e}")
            continue

        if not regions:
            print(f"[mubi]  -> not available on MUBI")
            regions = []

        data = {"mubi": regions}
        if dry:
            print(f"[dry/mubi] Would update {title}: {regions}")
        else:
            nz.update_page(pid, data, existing_props=props)
            updated += 1
            time.sleep(0.15)

    return updated


# -----------------------
# CLI
# -----------------------
def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="Fill run: page limit (0=all)")
    ap.add_argument("--dry-run", action="store_true", help="Don't write to Notion, only log")

    # One-off cover fixer
    ap.add_argument(
        "--set-covers",
        action="store_true",
        help="Set page cover from Backdrop URL for all rows that have 'backdrop' but no cover",
    )

    # Scan only the most-recently created N pages (useful for brand new rows with only LB URL)
    ap.add_argument(
        "--force-recent",
        type=int,
        default=0,
        metavar="N",
        help="Fill: scan last N created pages (ignores 'missing-only' heuristic)",
    )

    # MUBI refresh modes
    ap.add_argument(
        "--refresh-mubi",
        choices=("all", "recent"),
        help="Refresh MUBI regions (TMDb providers) either for all pages or only the recent ones",
    )
    ap.add_argument(
        "--mubi-recent",
        type=int,
        default=200,
        help="When --refresh-mubi=recent, how many most-recently created pages to scan (default 200)",
    )

    args = ap.parse_args()
    print("[debug] starting...")

    # --- Set covers from 'backdrop' (one-off / manual) ---
    if args.set_covers:
        print("[cover] Setting missing covers from Backdrop...")
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
        return

    # --- MUBI refresh (all or recent) ---
    if args.refresh_mubi:
        print("[debug] starting MUBI refresh...")
        if args.refresh_mubi == "all":
            print("[mubi] refreshing for ALL pages (daily run)")
            pages_iter = nz.iter_all_pages()
        else:
            print(f"[mubi] refreshing for last {args.mubi_recent} pages (created)")
            pages_iter = nz.iter_recent_pages(force_recent=args.mubi_recent, by="created")
        updated = _refresh_mubi_for_pages(pages_iter, dry=args.dry_run)
        print(f"[mubi] Done. Updated {updated} pages.")
        return

    # --- Normal fill flow ---
    if args.force_recent and args.force_recent > 0:
        # Process *only* last N created rows, regardless of whether we think they are "missing".
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by="created")
        updated = _fill_missing_for_pages(pages, dry=args.dry_run)
        print(f"Done. Updated {updated} pages.")
        return

    # Missing-only heuristic (full DB, limited by --limit if provided)
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows" if isinstance(rows, list) else "[debug] fetched rows")
    updated = _fill_missing_for_pages(rows, dry=args.dry_run)
    print(f"Done. Updated {updated} pages.")


if __name__ == "__main__":
    main()
