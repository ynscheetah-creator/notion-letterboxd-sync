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
    # Burada TMDb tarafında ayrı detaylarınız varsa ekleyebilirsiniz.
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

def main():
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="İşlenecek satır (normal mod).")
    ap.add_argument("--dry-run", action="store_true", help="Yazmadan logla.")
    ap.add_argument("--set-covers", action="store_true", help="Backdrop -> cover (tek seferlik).")
    ap.add_argument("--force-recent", type=int, default=0, help="Son N sayfayı zorla işle.")
    ap.add_argument("--recent-by", choices=("edited","created"), default="edited",
                    help="force-recent sıralaması: edited|created")
    args = ap.parse_args()

    print("[debug] starting...")

    # ---- tek seferlik kapak
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

    # ---- force recent modu
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by=args.recent_by)
        updated = 0

        for idx, page in enumerate(pages, start=1):
            props = page["properties"]; pid = page["id"]

            lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
            if not lb_url:  # Letterboxd yoksa pas
                continue

            # sayfa başlığı
            current_title = nz.get_page_title(props) or ""
            need_title = (not current_title) or (current_title.strip().lower()=="new page")

            # Letterboxd meta
            meta = None
            try: meta = lb.parse(lb_url)
            except Exception: meta=None

            payload: Dict[str, Any] = {}

            # başlık/yıl güncelle
            if need_title and meta and meta.get("title"):
                payload["original_title"] = meta["title"]   # name'i doğrudan değiştirmek yerine burada tutuyoruz

            # OMDb -> önce IMDb id ile
            try:
                om = omdb.get_by_imdb(meta.get("imdb_id")) if meta and meta.get("imdb_id") else None
                if not om and meta and meta.get("title"):
                    om = omdb.get_by_title(meta["title"], meta.get("year"))
            except Exception: om=None
            if om: _merge(payload, _payload_from_omdb(om))

            # TMDb fallback + MUBI bölgeleri
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

    # ---- normal mod (eksik alanları doldurmak için – isterseniz burada kendi kriterinizi kullanın)
    print("[debug] normal mode disabled in this minimal template — use --force-recent")
    print("Done. Updated 0 pages.")

if __name__ == "__main__":
    main()
