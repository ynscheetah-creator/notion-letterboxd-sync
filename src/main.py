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

def _safe_sleep():
    time.sleep(0.2)  # ~5 req/sn

def _fill_from_sources(title_guess: Optional[str], year_guess: Optional[int],
                       imdb_id: Optional[str], tmdb_id: Optional[str]) -> Dict[str, Any]:
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

    # 2) TMDb fallback / garnish
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

    return payload


def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="İşlenecek satır sayısı (0=limitsiz)")
    ap.add_argument("--dry-run", action="store_true", help="Notion'a yazmadan sadece logla")
    ap.add_argument("--set-covers", action="store_true",
                    help="Backdrop URL'lerini cover olarak ayarla (tek seferlik)")
    ap.add_argument("--force-recent", type=int, default=0,
                    help="Son N sayfayı başlık doldurma vb. için zorla tara")
    ap.add_argument("--recent-hours", type=int, default=0,
                    help="(opsiyonel) Son X saat içinde oluşturulan/güncellenenleri hedefle (yalın taramada sayfaya yedirilmez; basit bir üst limit amacıyla kullanılır)")
    ap.add_argument("--recent-limit", type=int, default=200,
                    help="force-recent ile birlikte kullanılacak üst sınır")
    args = ap.parse_args()

    print("[debug] starting...")

    # --- Cover set (tek sefer) ---
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
                _safe_sleep()
        print(f"[cover] Done. Scanned={scanned}, set={fixed}")
        return

    # --- Force recent (son N sayfa) ---
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent)
        updated = 0
        for idx, page in enumerate(pages, start=1):
            props = page["properties"]
            pid = page["id"]

            # Letterboxd link varsa devam edelim
            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:
                continue

            # Title boş/“New page” ise dolduralım
            current_title = nz.get_page_title(props) or ""
            need_title = (not current_title or current_title.lower() == "new page")

            # Letterboxd meta
            meta = None
            try:
                meta = lb.parse(lb_url)
            except Exception:
                meta = None

            payload: Dict[str, Any] = {}
            title_guess = None
            year_guess = None
            imdb_id = None
            tmdb_id = None

            if isinstance(meta, dict):
                title_guess = meta.get("title")
                year_guess = meta.get("year")
                imdb_id = meta.get("imdb_id")
                tmdb_id = meta.get("tmdb_id")

            # Başlık yazdırmak için name'ı taşı
            if title_guess:
                payload["name"] = title_guess

            # Ayrıntılı alanlar
            extra = _fill_from_sources(title_guess, year_guess, imdb_id, tmdb_id)
            _merge_payload(payload, extra)

            if not payload and not need_title:
                continue

            if args.dry_run:
                print(f"[dry] Would update {title_guess or current_title}: {payload}")
            else:
                nz.update_page(pid, payload, existing_props=props)
                updated += 1
                _safe_sleep()

        print(f"Done. Updated {updated} pages.")
        return

    # --- Normal eksik alan doldurma ---
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows" if isinstance(rows, list) else "[debug] fetched rows")

    updated = 0
    for idx, page in enumerate(rows, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        meta = None
        try:
            meta = lb.parse(lb_url)
        except Exception:
            meta = None

        title_guess = None
        year_guess = None
        imdb_id = None
        tmdb_id = None
        if isinstance(meta, dict):
            title_guess = meta.get("title")
            year_guess = meta.get("year")
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        payload: Dict[str, Any] = {}
        if title_guess:
            payload["name"] = title_guess

        extra = _fill_from_sources(title_guess, year_guess, imdb_id, tmdb_id)
        _merge_payload(payload, extra)

        if not payload:
            # yine de loglayalım
            print(f"[skip] {title_guess or lb_url}: no data found")
            continue

        if args.dry_run:
            print(f"[dry] Would update {title_guess}: {payload}")
        else:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            _safe_sleep()

    print(f"Done. Updated {updated} pages.")


if __name__ == "__main__":
    main()
