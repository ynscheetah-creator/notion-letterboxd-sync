# src/main.py
from __future__ import annotations
import argparse, time
from typing import Dict, Any, Optional

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS

def _merge(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    if not src: return
    for k, v in src.items():
        if v in (None, "", [], {}): continue
        dst[k] = v

def _from_omdb(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d: return {}
    return {
        "year": d.get("year"), "runtime": d.get("runtime"),
        "director": d.get("director"), "writer": d.get("writer"),
        "cinematography": d.get("cinematography"),
        "poster": d.get("poster"), "backdrop": d.get("backdrop"),
        "trailer_url": d.get("trailer_url"),
        "original_title": d.get("original_title") or d.get("title"),
        "synopsis": d.get("plot") or d.get("synopsis"),
        "countries": d.get("countries"), "languages": d.get("languages"),
        "cast_top": d.get("cast_top"),
    }

def _from_tmdb(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d: return {}
    return {
        "year": d.get("year"), "runtime": d.get("runtime"),
        "director": d.get("director"), "writer": d.get("writer"),
        "cinematography": d.get("cinematography"),
        "poster": d.get("poster"), "backdrop": d.get("backdrop"),
        "trailer_url": d.get("trailer_url"),
        "original_title": d.get("original_title") or d.get("title"),
        "synopsis": d.get("overview") or d.get("synopsis"),
        "countries": d.get("countries"), "languages": d.get("languages"),
        "cast_top": d.get("cast_top"),
    }

def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--set-covers", action="store_true")
    ap.add_argument("--force-recent", type=int, default=0, help="Son N sayfa (başlığı 'New page' olanları da doldur)")
    ap.add_argument("--recent-by", choices=["created", "edited"], default="created")
    args = ap.parse_args()

    print("[debug] starting...")

    # 1) Tek seferlik cover
    if args.set_covers:
        scanned = fixed = 0
        for page in nz.iter_recent_pages(0, by=args.recent_by):  # tümü
            scanned += 1
            props = page["properties"]
            backdrop = nz.read_prop(props, NOTION_COLS.get("backdrop"))
            if backdrop and page.get("cover") is None:
                if not args.dry_run:
                    nz.update_cover(page["id"], backdrop)
                fixed += 1
                time.sleep(0.15)
        print(f"[cover] Done. scanned={scanned}, set={fixed}")
        return

    # 2) “Son N” modu (yeni eklediklerini de kapsasın diye)
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by=args.recent_by)

        updated = 0
        for page in pages:
            props = page["properties"]; pid = page["id"]

            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:
                continue

            current_title = (nz.get_page_title(props) or "").strip()
            need_title = (not current_title) or (current_title.lower() == "new page")

            meta = {}
            try:
                meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
            except Exception:
                meta = {}

            payload: Dict[str, Any] = {}
            if need_title and meta.get("title"):
                payload["name"] = meta["title"]

            # OMDb (ID varsa ID ile)
            omdb_data = None
            try:
                if meta.get("imdb_id") and hasattr(omdb, "get_by_imdb"):
                    omdb_data = omdb.get_by_imdb(meta["imdb_id"])
                elif hasattr(omdb, "get_by_title") and meta.get("title"):
                    omdb_data = omdb.get_by_title(meta["title"], meta.get("year"))
            except Exception:
                pass
            _merge(payload, _from_omdb(omdb_data or {}))

            # TMDb fallback
            if not payload or any(k not in payload for k in ("year", "poster", "backdrop")):
                tmdb_data = None
                try:
                    if meta.get("tmdb_id") and hasattr(tmdb, "get_by_id"):
                        tmdb_data = tmdb.get_by_id(meta["tmdb_id"])
                    elif hasattr(tmdb, "get_by_title") and meta.get("title"):
                        tmdb_data = tmdb.get_by_title(meta["title"], meta.get("year"))
                except Exception:
                    pass
                _merge(payload, _from_tmdb(tmdb_data or {}))

            if not payload:
                continue

            if args.dry_run:
                print(f"[dry] would update: {payload}")
            else:
                nz.update_page(pid, payload)
                updated += 1
                time.sleep(0.2)

        print(f"Done. Updated {updated} pages.")
        return

    # 3) Eski “eksikleri doldur” modu (limit opsiyonel)
    rows = []  # burada istersen eskisi gibi nz.iter_pages_needing_fill() kullanabilirsin
    print(f"[debug] fetched {len(rows)} rows")
    print("Done. Updated 0 pages.")

if __name__ == "__main__":
    main()
