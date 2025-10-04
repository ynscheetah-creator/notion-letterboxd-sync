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
# Merge helpers
# -----------------------------
def _merge_payload(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    """src'de dolu gelen alanları dst'ye ekler (boşları yazmaz)."""
    if not src:
        return
    for k, v in src.items():
        if v in (None, "", [], {}):
            continue
        dst[k] = v  # 0 gibi değerler geçerli olabilir


# -----------------------------
# Source -> Notion payload mappers
# -----------------------------
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
    ap.add_argument("--limit", type=int, default=0, help="Eksik alan taramada işlenecek satır sayısı (0=limitsiz)")
    ap.add_argument("--dry-run", action="store_true", help="Notion'a yazmadan sadece logla")
    ap.add_argument(
        "--set-covers",
        action="store_true",
        help="Tüm sayfalarda Backdrop URL'sini sayfa cover'ı olarak ayarla (tek seferlik)",
    )
    ap.add_argument("--recent-hours", type=int, default=0,
                    help="Son N saatte düzenlenen sayfaları dene (eksik alan şartı yok). 0=kapalı")
    ap.add_argument("--recent-limit", type=int, default=50,
                    help="--recent-hours açıkken maksimum sayfa sayısı (0=limitsiz)")

    args = ap.parse_args()

    print("[debug] starting...")

    # --- Tek seferlik kapak düzeltme modu ---
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
                time.sleep(0.15)
        print(f"[cover] Done. Scanned={scanned}, set={fixed}")
        return

    # --- Hangi sayfaları işleyeceğiz? ---
    pages = None
    if args.recent_hours and args.recent_hours > 0:
        pages = nz.iter_recent_pages(hours=args.recent_hours, limit=args.recent_limit)
        print(f"[debug] fetched {len(pages)} recent pages")
        # Sadece Letterboxd linki olanları bırak
        filtered = []
        for p in pages:
            props = p["properties"]
            if (nz.read_prop(props, NOTION_COLS.get("letterboxd")) or
                nz.find_letterboxd_url(props)):
                filtered.append(p)
        pages = filtered
    else:
        pages = nz.iter_pages_needing_fill(limit=args.limit)
        print(f"[debug] fetched {len(pages)} rows")

    updated = 0

    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        # Letterboxd link
        lb_url = (nz.read_prop(props, NOTION_COLS.get("letterboxd"))
                  or nz.find_letterboxd_url(props))
        if not lb_url:
            continue

        # Tahmini başlık & yıl + ID'ler
        title_guess = nz.get_page_title(props) or None
        year_guess = None
        imdb_id = None
        tmdb_id = None

        meta = None
        # Önce güçlü parser'ın varsa onu dene
        try:
            if hasattr(lb, "parse"):
                meta = lb.parse(lb_url)
        except Exception:
            meta = None

        # Basit slug tahmini (from_boxd) fallback
        if not meta:
            try:
                if hasattr(lb, "from_boxd"):
                    meta = lb.from_boxd(lb_url)
            except Exception:
                meta = None

        if isinstance(meta, dict):
            title_guess = meta.get("title") or title_guess
            year_guess  = meta.get("year")  or year_guess
            imdb_id     = meta.get("imdb_id") or imdb_id
            tmdb_id     = meta.get("tmdb_id") or tmdb_id

        print(f"[debug] row {idx}: title='{title_guess}' url='{lb_url}'")

        # Kaynaklardan veri çek
        payload: Dict[str, Any] = {}

        # 1) OMDb (ID varsa ID ile, yoksa başlık+yıl)
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

        # 2) TMDb fallback (ID varsa ID ile, yoksa başlık+yıl)
        needs_core = any(k not in payload for k in (
            "year", "director", "writer", "cinematography", "runtime", "poster", "backdrop"
        ))
        if not payload or needs_core:
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
            print(f"[skip] {title_guess or 'Unknown'}: no data found")
            continue

        # Notion update
        if args.dry_run:
            print(f"[dry] Would update {title_guess or 'Unknown'}: {payload}")
        else:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            time.sleep(0.2)  # Notion rate-limit güvenliği

    print(f"Done. Updated {updated} pages.")


if __name__ == "__main__":
    main()
