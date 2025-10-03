# src/main.py
from __future__ import annotations

import argparse
import time
from typing import Dict, Any, Optional

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS


def _merge_payload(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
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


def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="İşlenecek satır sayısı (0=limitsiz)")
    ap.add_argument("--dry-run", action="store_true", help="Notion'a yazmadan sadece logla")
    ap.add_argument(
        "--set-covers",
        action="store_true",
        help="Tüm sayfalarda Backdrop URL'sini sayfa cover'ı olarak ayarla (tek seferlik)",
    )
    args = ap.parse_args()

    print("[debug] starting...")

    # ---- Tek seferlik kapak düzeltme modu ----
    if args.set_covers:
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
                time.sleep(0.15)  # Notion rate limit'e nazik
        print(f"[cover] Done. Scanned={scanned}, set={fixed}")
        return

    # ---- Normal eksik alanları doldurma ----
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows" if isinstance(rows, list) else "[debug] fetched rows")

    updated = 0
    for idx, page in enumerate(rows, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        title_guess = None
        year_guess = None
        imdb_id = None
        tmdb_id = None

        meta = None
        try:
            meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
        except Exception:
            meta = None

        if isinstance(meta, dict):
            title_guess = meta.get("title")
            year_guess = meta.get("year")
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        # Fallback: Notion Name → olmadı title property tara
        if not title_guess:
            title_guess = nz.read_prop(props, NOTION_COLS.get("name"))
        if not title_guess:
            title_guess = nz.get_page_title(props)

        print(f"[debug] row {idx}: name='{title_guess}' url='{lb_url}' needs={{'year': True, 'director': True, 'writer': True, 'cinematography': True, 'runtime': True, 'poster': True}}")

        payload: Dict[str, Any] = {}

        # 1) OMDb
        omdb_data = None
        try:
            if imdb_id and hasattr(omdb, "get_by_imdb"):
                omdb_data = omdb.get_by_imdb(imdb_id)
            elif hasattr(omdb, "get_by_title") and title_guess:
                omdb_data = omdb.get_by_title(title_guess, year_guess)
        except Exception:
            omdb_data = None
        if omdb_data:
            _merge_payload(payload, _payload_from_omdb(omdb_data))

        # 2) TMDb fallback
        if not payload or any(k not in payload for k in ("year", "director", "writer", "cinematography", "runtime", "poster", "backdrop")):
            tmdb_data = None
            try:
                if tmdb_id and hasattr(tmdb, "get_by_id"):
                    tmdb_data = tmdb.get_by_id(tmdb_id)
                elif hasattr(tmdb, "get_by_title") and title_guess:
                    tmdb_data = tmdb.get_by_title(title_guess, year_guess)
            except Exception:
                tmdb_data = None
            if tmdb_data:
                _merge_payload(payload, _payload_from_tmdb(tmdb_data))

        if not payload:
            print(f"[skip] {title_guess}: no data found")
            continue

        if args.dry_run:
            print(f"[dry] Would update {title_guess}: {payload}")
        else:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            time.sleep(0.2)  # Notion rate limit

    print(f"Done. Updated {updated} pages.")


if __name__ == "__main__":
    main()
