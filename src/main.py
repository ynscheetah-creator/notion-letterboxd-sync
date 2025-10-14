from __future__ import annotations
import argparse
import time
from typing import Dict, Any

import src.notion as nz
import src.letterboxd as lb
import src.omdb as omdb
import src.tmdb as tmdb
from src.config import NOTION_COLS


def _merge_payload(base: Dict[str, Any], new: Dict[str, Any]) -> None:
    """Yeni alanları mevcut payload’a ekler (boş olmayanları)."""
    if not new:
        return
    for k, v in new.items():
        if v in (None, "", [], {}):
            continue
        if k not in base:
            base[k] = v


def _payload_from_omdb(d: Dict[str, Any]) -> Dict[str, Any]:
    """OMDb sözlüğünü Notion alanlarına çevir."""
    if not d:
        return {}
    p: Dict[str, Any] = {}
    p["director"] = d.get("Director")
    p["writer"] = d.get("Writer")
    p["languages"] = d.get("Language")
    p["countries"] = d.get("Country")
    p["runtime"] = d.get("Runtime")
    poster = d.get("Poster")
    if poster and poster != "N/A":
        p["poster"] = poster
    return {k: v for k, v in p.items() if v}


def _payload_from_tmdb(d: Dict[str, Any]) -> Dict[str, Any]:
    """TMDb sözlüğünü Notion alanlarına çevir."""
    if not d:
        return {}
    p: Dict[str, Any] = {}
    p["director"] = d.get("director")
    p["writer"] = d.get("writer")
    p["runtime"] = d.get("runtime")
    p["poster"] = d.get("poster")
    p["backdrop"] = d.get("backdrop")
    if d.get("countries"):
        p["countries"] = ", ".join(d["countries"])
    if d.get("languages"):
        p["languages"] = ", ".join(d["languages"])
    return {k: v for k, v in p.items() if v}


def main():
    ap = argparse.ArgumentParser(description="Notion × Letterboxd sync")
    ap.add_argument("--set-covers", action="store_true",
                    help="Backdrop URL’lerini sayfa kapağı olarak ayarla (tek seferlik temizlik)")
    ap.add_argument("--force-recent", type=int, default=0,
                    help="Son N sayfayı (created_time) zorla yenile")
    ap.add_argument("--limit", type=int, default=200,
                    help="Eksik alanlı kaç sayfa işlenecek (0 = limitsiz)")
    args = ap.parse_args()

    print("[debug] starting...")

    # --- Tek seferlik kapak düzeltme
    if args.set_covers:
        print("[cover] Setting missing covers from Backdrop...")
        scanned = 0
        fixed = 0
        for page in nz.iter_all_pages():
            scanned += 1
            props = page["properties"]
            backdrop = nz.read_prop(props, NOTION_COLS.get("backdrop"))
            if backdrop and page.get("cover") is None:
                nz.update_cover(page["id"], backdrop)
                fixed += 1
                time.sleep(0.15)
        print(f"[cover] Done. Scanned={scanned}, set={fixed}")
        return

    # --- Force recent (son N sayfa)
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by="created")
        updated = 0

        for idx, page in enumerate(pages, start=1):
            props = page["properties"]
            pid = page["id"]

            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:
                continue

            # Başlık gerekirse (New page vs.) dolduralım
            current_title = nz.get_page_title(props) or ""
            need_title = (not current_title or current_title.lower() == "new page")

            # Letterboxd meta
            meta = None
            try:
                meta = lb.parse(lb_url)
            except Exception:
                meta = None

            payload: Dict[str, Any] = {}
            if meta:
                if need_title and meta.get("title"):
                    payload["original_title"] = meta["title"]
                if meta.get("year"):
                    payload["year"] = meta["year"]

            # OMDb
            omdb_data = None
            try:
                if meta and meta.get("imdb_id"):
                    omdb_data = omdb.get_by_imdb(meta["imdb_id"])
                elif meta and meta.get("title"):
                    omdb_data = omdb.get_by_title(meta["title"], meta.get("year"))
            except Exception:
                omdb_data = None
            _merge_payload(payload, _payload_from_omdb(omdb_data or {}))

            # TMDb
            tmdb_data = None
            try:
                if meta and meta.get("tmdb_id"):
                    tmdb_data = tmdb.get_by_id(meta["tmdb_id"])
                elif meta and meta.get("title"):
                    tmdb_data = tmdb.get_by_title(meta["title"], meta.get("year"))
            except Exception:
                tmdb_data = None
            _merge_payload(payload, _payload_from_tmdb(tmdb_data or {}))

            if not payload:
                continue

            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            time.sleep(0.2)

        print(f"Done. Updated {updated} pages.")
        return

    # --- Normal: eksik alanları doldur
    rows = list(nz.iter_pages_needing_fill(limit=args.limit))
    print(f"[debug] fetched {len(rows)} rows")

    updated = 0
    for page in rows:
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        current_title = nz.get_page_title(props) or ""
        need_title = (not current_title or current_title.lower() == "new page")

        meta = None
        try:
            meta = lb.parse(lb_url)
        except Exception:
            meta = None

        payload: Dict[str, Any] = {}
        if meta:
            if need_title and meta.get("title"):
                payload["original_title"] = meta["title"]
            if meta.get("year"):
                payload["year"] = meta["year"]

        omdb_data = None
        try:
            if meta and meta.get("imdb_id"):
                omdb_data = omdb.get_by_imdb(meta["imdb_id"])
            elif meta and meta.get("title"):
                omdb_data = omdb.get_by_title(meta["title"], meta.get("year"))
        except Exception:
            omdb_data = None
        _merge_payload(payload, _payload_from_omdb(omdb_data or {}))

        tmdb_data = None
        try:
            if meta and meta.get("tmdb_id"):
                tmdb_data = tmdb.get_by_id(meta["tmdb_id"])
            elif meta and meta.get("title"):
                tmdb_data = tmdb.get_by_title(meta["title"], meta.get("year"))
        except Exception:
            tmdb_data = None
        _merge_payload(payload, _payload_from_tmdb(tmdb_data or {}))

        if not payload:
            continue

        nz.update_page(pid, payload, existing_props=props)
        updated += 1
        time.sleep(0.2)

    print(f"Done. Updated {updated} pages.")


if __name__ == "__main__":
    main()
