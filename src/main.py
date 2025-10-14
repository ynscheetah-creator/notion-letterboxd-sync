# src/main.py
from __future__ import annotations

import argparse
import time
from typing import Any, Dict, Optional

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS


# -----------------------------
# Helpers to build payloads
# -----------------------------
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


# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="İşlenecek satır sayısı (0=limitsiz)")
    ap.add_argument("--dry-run", action="store_true", help="Notion'a yazmadan sadece logla")
    ap.add_argument("--set-covers", action="store_true",
                    help="Tüm sayfalarda Backdrop URL'sini sayfa cover'ı olarak ayarla (tek seferlik)")
    ap.add_argument("--force-recent", type=int, default=0,
                    help="TÜM veritabanı yerine son N sayfa üzerinde çalış (0=kapalı)")
    args = ap.parse_args()

    print("[debug] starting...")

    # --- Tek seferlik cover düzeltme
    if args.set_covers:
        print("[cover] Setting missing covers from Backdrop...")
        scanned = fixed = 0
        for page in nz.iter_all_pages():
            scanned += 1
            props = page["properties"]
            backdrop = nz.read_prop(props, NOTION_COLS.get("backdrop"))
            if backdrop and page.get("cover") is None:
                if not args.dry_run:
                    nz.update_cover(page["id"], backdrop)
                fixed += 1
                time.sleep(0.15)
        print(f"[cover] Done. Scanned={scanned}, set={fixed}")
        return

    # --- Force recent mod (son N sayfa)
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent)
        updated = 0

        for idx, page in enumerate(pages, start=1):
            props = page["properties"]
            pid = page["id"]

            # Letterboxd link yoksa atla
            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:
                continue

            # Title boş mu?
            current_title = nz.get_page_title(props) or ""
            need_title = (not current_title or current_title.lower() == "new page")

            # LB meta
            meta = None
            try:
                meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
            except Exception:
                meta = None

            payload: Dict[str, Any] = {}
            # Eğer sayfa adı boşsa LB başlığıyla doldur
            if need_title and meta and meta.get("title"):
                payload["__page_title"] = meta["title"]

            # Önce OMDb (ID varsa ID)
            omdb_data = None
            try:
                if meta and meta.get("imdb_id") and hasattr(omdb, "get_by_imdb"):
                    omdb_data = omdb.get_by_imdb(meta["imdb_id"])
                elif hasattr(omdb, "get_by_title") and (meta and meta.get("title")):
                    omdb_data = omdb.get_by_title(meta["title"], meta.get("year"))
            except Exception:
                omdb_data = None
            _merge_payload(payload, _payload_from_omdb(omdb_data) if omdb_data else None)

            # TMDb fallback
            need_any_main = any(k not in payload for k in ("year", "director", "writer",
                                                           "cinematography", "runtime", "poster", "backdrop"))
            if need_any_main:
                tmdb_data = None
                try:
                    if meta and meta.get("tmdb_id") and hasattr(tmdb, "get_by_id"):
                        tmdb_data = tmdb.get_by_id(meta["tmdb_id"])
                    elif hasattr(tmdb, "get_by_title") and (meta and meta.get("title")):
                        tmdb_data = tmdb.get_by_title(meta["title"], meta.get("year"))
                except Exception:
                    tmdb_data = None
                _merge_payload(payload, _payload_from_tmdb(tmdb_data) if tmdb_data else None)

            if not payload:
                print(f"[skip] row {idx}: no data for '{current_title or meta and meta.get('title') or '∅'}'")
                continue

            if args.dry_run:
                print(f"[dry] Would update '{current_title or payload.get('__page_title','(no title)')}' -> {payload}")
            else:
                nz.update_page(pid, payload, existing_props=props)
                updated += 1
                time.sleep(0.2)

        print(f"Running recent sync (last {args.force_recent})")
        print(f"Done. Updated {updated} pages.")
        return

    # --- Normal mod (eksik alanları doldur)
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows" if isinstance(rows, list) else "[debug] fetched rows")

    updated = 0
    for idx, page in enumerate(rows, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        # Basit başlık, log amacıyla
        title_guess = nz.get_page_title(props) or "New page"
        print(f"[debug] row {idx}: title='{title_guess}' url='{lb_url}'")

        payload: Dict[str, Any] = {}

        # OMDb
        omdb_data = None
        try:
            omdb_data = omdb.get_by_title(title_guess, None) if hasattr(omdb, "get_by_title") else None
        except Exception:
            omdb_data = None
        _merge_payload(payload, _payload_from_omdb(omdb_data) if omdb_data else None)

        # TMDb fallback
        need_any_main = any(k not in payload for k in ("year", "director", "writer",
                                                       "cinematography", "runtime", "poster", "backdrop"))
        if need_any_main and hasattr(tmdb, "get_by_title"):
            try:
                tmdb_data = tmdb.get_by_title(title_guess, None)
            except Exception:
                tmdb_data = None
            _merge_payload(payload, _payload_from_tmdb(tmdb_data) if tmdb_data else None)

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


if __name__ == "__main__":
    main()
