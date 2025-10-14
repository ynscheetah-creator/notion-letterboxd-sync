from __future__ import annotations
import argparse, time
from typing import Dict, Any, Optional
from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS

def _merge(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    if not src: return
    for k,v in src.items():
        if v in (None,"",[],{}): continue
        dst[k]=v

def _payload_from_omdb(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d: return {}
    return {
        "year": d.get("year"),
        "runtime": d.get("runtime"),
        "director": d.get("director"),
        "writer": d.get("writer"),
        "cinematography": d.get("cinematography"),
        "poster": d.get("poster"),
        "original_title": d.get("original_title") or d.get("title"),
        "synopsis": d.get("synopsis") or d.get("plot"),
        "countries": d.get("countries"),
        "languages": d.get("languages"),
        "cast_top": d.get("cast_top"),
        "backdrop": d.get("backdrop"),
        "trailer_url": d.get("trailer_url"),
    }

def _payload_from_tmdb(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d: return {}
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

def _as_set(v) -> set[str]:
    if not v: return set()
    if isinstance(v, (list, tuple, set)): return {str(x).strip() for x in v if str(x).strip()}
    return {s.strip() for s in str(v).split(",") if s.strip()}

def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--set-covers", action="store_true")
    ap.add_argument("--force-recent", type=int, default=0)
    ap.add_argument("--recent-by", choices=("edited","created"), default="edited")
    # YENİ: yalnızca MUBI alanını güncelle
    ap.add_argument("--refresh-mubi", action="store_true",
                    help="Sadece MUBI ülkelerini tazele (force-recent ile sınırla).")
    args = ap.parse_args()

    print("[debug] starting...")

    # --- tek seferlik kapak
    if args.set_covers:
        print("[cover] Set covers from Backdrop")
        scanned=fixed=0
        for page in nz.iter_recent_pages(force_recent=1000, by="created"):
            scanned+=1
            props = page["properties"]
            bd = nz.read_prop(props, NOTION_COLS.get("backdrop"))
            if bd and not page.get("cover"):
                if not args.dry_run: nz.update_cover(page["id"], bd)
                fixed+=1; time.sleep(0.15)
        print(f"[cover] Done. scanned={scanned} set={fixed}")
        return

       # --- YALNIZCA MUBI TAZELEME (tüm sayfalar veya son N sayfa) ---
    if args.refresh_mubi:
        # force_recent=0 veya verilmemişse -> TÜM SAYFALAR
        n = args.force_recent if args.force_recent is not None else 0
        scan_all = (n == 0)

        if scan_all:
            print("[mubi] refreshing MUBI regions for ALL pages")
            pages_iter = nz.iter_all_pages()
        else:
            print(f"[mubi] refreshing MUBI regions for last {n} pages (by={args.recent_by})")
            pages_iter = nz.iter_recent_pages(force_recent=max(1, n), by=args.recent_by)

        updated = 0
        scanned = 0

        for page in pages_iter:
            scanned += 1
            props = page["properties"]
            pid = page["id"]

            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:
                continue

            # Eski MUBI
            old_mubi = {*(nz.read_prop(props, NOTION_COLS.get("mubi")) or [])}

            # Letterboxd -> TMDb id
            meta = None
            try:
                meta = lb.parse(lb_url)
            except Exception:
                meta = None

            tmdb_id = (meta or {}).get("tmdb_id")
            if not tmdb_id:
                continue

            # TMDb watch/providers -> MUBI bölgeleri
            try:
                new_regions = set(tmdb.mubi_regions_for_movie(tmdb_id))
            except Exception as e:
                print(f"[mubi] providers error ({lb_url}): {e}")
                continue

            # Değişiklik yoksa geç
            if new_regions == old_mubi:
                continue

            payload = {"mubi": sorted(new_regions)}
            if args.dry_run:
                print(f"[mubi][dry] {lb_url}: {sorted(old_mubi)} -> {sorted(new_regions)}")
            else:
                nz.update_page(pid, payload)
                updated += 1
                time.sleep(0.18)  # Notion / TMDb rate-limit için minik uyku

            # İsteğe bağlı: her 200 sayfada bir durum yaz
            if scanned % 200 == 0:
                print(f"[mubi] progress: scanned={scanned}, updated={updated}")

        print(f"[mubi] Done. scanned={scanned}, updated={updated}")
        return

    # --- force recent (tam doldurma)
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by=args.recent_by)
        updated = 0

        for page in pages:
            props = page["properties"]; pid = page["id"]

            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:
                continue

            current_title = nz.get_page_title(props) or ""
            need_title = (not current_title) or (current_title.strip().lower()=="new page")

            meta = None
            try: meta = lb.parse(lb_url)
            except Exception: meta=None

            payload: Dict[str, Any] = {}

            if need_title and meta and meta.get("title"):
                payload["original_title"] = meta["title"]

            # OMDb
            try:
                om = omdb.get_by_imdb(meta.get("imdb_id")) if meta and meta.get("imdb_id") else None
                if not om and meta and meta.get("title"):
                    om = omdb.get_by_title(meta["title"], meta.get("year"))
            except Exception: om=None
            if om: _merge(payload, _payload_from_omdb(om))

            # MUBI
            try:
                if meta and meta.get("tmdb_id"):
                    regs = tmdb.mubi_regions_for_movie(meta["tmdb_id"])
                    if regs: payload["mubi"] = regs
            except Exception as e:
                print(f"[warn] MUBI regions error: {e}")

            if not payload:
                continue

            if args.dry_run:
                print(f"[dry] would update {lb_url}: {payload}")
            else:
                nz.update_page(pid, payload); updated+=1; time.sleep(0.2)

        print(f"Done. Updated {updated} pages.")
        return

    # --- normal mod devre dışı (sadece force-recent veya refresh-mubi kullanıyoruz)
    print("[debug] normal mode disabled — use --force-recent or --refresh-mubi")
    print("Done. Updated 0 pages.")

if __name__ == "__main__":
    main()
