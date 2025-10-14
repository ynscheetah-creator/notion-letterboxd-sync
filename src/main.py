# src/main.py
from __future__ import annotations

import argparse
import time
from typing import Dict, Any, Optional

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS


# -----------------------------
# Small helpers
# -----------------------------
def _merge_payload(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    """Copy only truthy / meaningful fields from src to dst."""
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


# -----------------------------
# Core runners
# -----------------------------
def mode_set_covers(dry_run: bool) -> None:
    """One-shot: set page cover from Backdrop URL if cover is empty."""
    print("[cover] Setting missing covers from Backdrop...", flush=True)
    scanned = 0
    fixed = 0
    for page in nz.iter_all_pages():
        scanned += 1
        props = page["properties"]
        backdrop = nz.read_prop(props, NOTION_COLS.get("backdrop"))
        current_cover = page.get("cover")
        if backdrop and current_cover is None:
            if not dry_run:
                nz.update_cover(page["id"], backdrop)
            fixed += 1
            time.sleep(0.15)
    print(f"[cover] Done. Scanned={scanned}, set={fixed}")


def _enrich_one_page(page: Dict[str, Any], dry_run: bool) -> bool:
    """
    Enrich a single Notion page. Returns True if updated.
    - If page title is empty or 'New page', try to set it from Letterboxd.
    - Then fetch & fill other fields from OMDb/TMDb.
    """
    props = page["properties"]
    pid = page["id"]

    # Letterboxd link
    lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
    if not lb_url:
        return False

    # Current title and need_title
    current_title = nz.get_page_title(props) or ""
    need_title = (not current_title) or (current_title.lower() == "new page")

    # Guess meta from Letterboxd
    title_guess: Optional[str] = None
    year_guess: Optional[int] = None
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None

    meta = None
    try:
        meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
    except Exception:
        meta = None

    if isinstance(meta, dict):
        title_guess = meta.get("title") or title_guess
        year_guess = meta.get("year") or year_guess
        imdb_id = meta.get("imdb_id") or imdb_id
        tmdb_id = meta.get("tmdb_id") or tmdb_id

    # Build payload
    payload: Dict[str, Any] = {}

    # If title is missing/placeholder —> set from Letterboxd
    if need_title and title_guess:
        payload["title"] = title_guess

    # 1) OMDb first (by id if possible, else by title/year)
    omdb_data = None
    try:
        if imdb_id and hasattr(omdb, "get_by_imdb"):
            omdb_data = omdb.get_by_imdb(imdb_id)
        elif hasattr(omdb, "get_by_title") and (title_guess or current_title):
            omdb_data = omdb.get_by_title(title_guess or current_title, year_guess)
    except Exception:
        omdb_data = None

    if omdb_data:
        _merge_payload(payload, _payload_from_omdb(omdb_data))

    # 2) TMDb fallback / completion
    need_core = any(
        k not in payload
        for k in ("year", "director", "writer", "cinematography", "runtime", "poster", "backdrop")
    )
    if need_core:
        tmdb_data = None
        try:
            if tmdb_id and hasattr(tmdb, "get_by_id"):
                tmdb_data = tmdb.get_by_id(tmdb_id)
            elif hasattr(tmdb, "get_by_title") and (title_guess or current_title):
                tmdb_data = tmdb.get_by_title(title_guess or current_title, year_guess)
        except Exception:
            tmdb_data = None
        if tmdb_data:
            _merge_payload(payload, _payload_from_tmdb(tmdb_data))

    # nothing to write
    if not payload:
        return False

    if dry_run:
        print(f"[dry] Would update '{current_title or title_guess or 'Unknown'}': {payload}")
        return False

    nz.update_page(pid, payload, existing_props=props)
    # Rate-limit safety
    time.sleep(0.2)
    return True


def mode_fill_missing(limit: int, dry_run: bool) -> None:
    rows = nz.iter_pages_needing_fill(limit=limit)
    print(f"[debug] fetched {len(rows)} rows")
    updated = 0
    for idx, page in enumerate(rows, start=1):
        ok = _enrich_one_page(page, dry_run=dry_run)
        updated += int(ok)
    print(f"Done. Updated {updated} pages.")


def mode_force_recent(n: int, dry_run: bool, sort_by: str = "edited") -> None:
    """
    Scan last N pages (by 'edited' or 'created') and enrich them regardless of NEED_KEYS.
    Requires nz.iter_recent_pages(force_recent=N, by=sort_by).
    """
    print(f"Running recent sync (last {n})")
    pages = nz.iter_recent_pages(force_recent=n, by=sort_by)
    updated = 0
    for page in pages:
        ok = _enrich_one_page(page, dry_run=dry_run)
        updated += int(ok)
    print(f"Done. Updated {updated} pages.")


# -----------------------------
# CLI
# -----------------------------
def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="Max rows to process in missing-fill mode (0=all)")
    ap.add_argument("--dry-run", action="store_true", help="Log only; do not write to Notion")
    ap.add_argument("--set-covers", action="store_true", help="One-shot: set page cover from Backdrop if empty")
    ap.add_argument(
        "--force-recent",
        type=int,
        default=0,
        help="Process the most recently edited/created N pages (ignores NEED_KEYS)",
    )
    ap.add_argument(
        "--recent-by",
        choices=("edited", "created"),
        default="edited",
        help="When using --force-recent, sort by 'edited' or 'created' time",
    )
    args = ap.parse_args()

    print("[debug] starting...")

    if args.set_covers:
        mode_set_covers(dry_run=args.dry_run)
        return

    if args.force_recent and args.force_recent > 0:
        mode_force_recent(n=args.force_recent, dry_run=args.dry_run, sort_by=args.recent_by)
        return

    # default: fill only missing target fields
    mode_fill_missing(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
