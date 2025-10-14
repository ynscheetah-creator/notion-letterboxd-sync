# src/main.py
from __future__ import annotations

import argparse
import time
from typing import Dict, Any, Optional, Iterable, Tuple

from . import notion as nz
from . import letterboxd as lb
from . import omdb, tmdb
from .config import NOTION_COLS


# ------------------------
# küçük yardımcılar
# ------------------------
def _merge_payload(dst: Dict[str, Any], src: Optional[Dict[str, Any]]) -> None:
    """src'de dolu gelen alanları dst'ye ekler (boşları yazmaz)."""
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


# ----------------------------------------------------
# MUBI yenileme: tek bir Notion sayfasını güncelle
# ----------------------------------------------------
def _refresh_mubi_for_page(
    page: Dict[str, Any],
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """Sayfa için MUBI ülkelerini TMDb'den bul ve 'mubi' multi-select'e yaz."""
    props = page["properties"]
    pid = page["id"]

    # Başlık & yıl & Letterboxd
    title = nz.get_page_title(props) or nz.read_prop(props, NOTION_COLS.get("name"))
    year = nz.read_prop(props, NOTION_COLS.get("year"))
    lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))

    if not (title or lb_url):
        return False, "no-title-or-link"

    # Letterboxd'tan TMDb ID çekmeyi dene
    tmdb_id = None
    try:
        if lb_url:
            meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
            tmdb_id = (meta or {}).get("tmdb_id")
            # varsa daha sağlam yıl & başlık güncellemesi için bunları kullan
            if (meta or {}).get("title"):
                title = meta.get("title")
            if (meta or {}).get("year"):
                year = meta.get("year")
    except Exception:
        pass

    # TMDb'den MUBI ülkeleri
    regions: list[str] = []
    try:
        if tmdb_id:
            regions = tmdb.get_mubi_regions_by_id(tmdb_id) or []
        if not regions and title:
            regions = tmdb.get_mubi_regions_by_title(title, year) or []
    except Exception:
        regions = []

    # Güncelle
    payload = {"mubi": sorted(set(regions))}
    if dry_run:
        return True, f"dry mubi={payload['mubi']}"
    nz.update_page(pid, payload, existing_props=props)
    time.sleep(0.15)
    return True, f"mubi={payload['mubi']}"


# ----------------------------------------------------
# “Eksikleri doldur” ana akış
# ----------------------------------------------------
def _fill_missing(args: argparse.Namespace) -> None:
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(
        f"[debug] fetched {len(rows)} rows"
        if isinstance(rows, list)
        else "[debug] fetched rows"
    )

    updated = 0
    for idx, page in enumerate(rows, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        # tahmini başlık / yıl
        title_guess = nz.get_page_title(props) or None
        year_guess = nz.read_prop(props, NOTION_COLS.get("year"))
        imdb_id = None
        tmdb_id = None

        try:
            meta = lb.parse(lb_url)  # {'title','year','imdb_id','tmdb_id'}
        except Exception:
            meta = None

        if isinstance(meta, dict):
            title_guess = meta.get("title") or title_guess
            year_guess = meta.get("year") or year_guess
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        print(
            f"[debug] row {idx}: title='{title_guess}' url='{lb_url}'"
        )

        # Kaynaklardan veri çek
        payload: Dict[str, Any] = {}

        # 1) OMDb
        try:
            omdb_data = None
            if imdb_id and hasattr(omdb, "get_by_imdb"):
                omdb_data = omdb.get_by_imdb(imdb_id)
            elif hasattr(omdb, "get_by_title") and title_guess:
                omdb_data = omdb.get_by_title(title_guess, year_guess)
        except Exception:
            omdb_data = None
        if omdb_data:
            _merge_payload(payload, _payload_from_omdb(omdb_data))

        # 2) TMDb
        try:
            tmdb_data = None
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
            time.sleep(0.2)

    print(f"Done. Updated {updated} pages.")


# ----------------------------------------------------
# MUBI yenileme akışı
# ----------------------------------------------------
def _refresh_mubi(args: argparse.Namespace) -> None:
    mode = args.refresh_mubi  # "all" | "recent"
    if mode == "all":
        pages_iter: Iterable[Dict[str, Any]] = nz.iter_all_pages()
        print("Refreshing MUBI for ALL pages (daily run)")
    else:
        # recent
        print(f"Refreshing MUBI for recent pages (last {args.mubi_recent})")
        pages_iter = nz.iter_recent_pages(force_recent=args.mubi_recent, by="created")

    touched, ok, fail = 0, 0, 0
    for page in pages_iter:
        touched += 1
        ok_one, msg = _refresh_mubi_for_page(page, dry_run=args.dry_run)
        if ok_one:
            ok += 1
        else:
            fail += 1
        # isteğe bağlı log
        name = nz.get_page_title(page["properties"]) or "?"
        print(f"[mubi] {name}: {msg}")

        # recent modunda N kadar işlediysek dur
        if mode == "recent" and touched >= args.mubi_recent:
            break

    print(f"[mubi] done. scanned={touched}, ok={ok}, fail={fail}")


# ----------------------------------------------------
# Cover set (tek seferlik)
# ----------------------------------------------------
def _set_covers(args: argparse.Namespace) -> None:
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


# ----------------------------------------------------
# main
# ----------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser("Notion × Letterboxd sync")
    ap.add_argument("--limit", type=int, default=0, help="İşlenecek satır sayısı (0=limitsiz)")
    ap.add_argument("--dry-run", action="store_true", help="Notion'a yazmadan sadece logla")

    # Tek seferlik kapak düzeltme
    ap.add_argument(
        "--set-covers",
        action="store_true",
        help="Tüm sayfalarda Backdrop URL'sini sayfa cover'ı olarak ayarla (tek seferlik)",
    )

    # Son N sayfa modu (eksik doldurma için)
    ap.add_argument(
        "--force-recent",
        type=int,
        default=0,
        metavar="N",
        help="Eksik doldurma işlemini 'son N' sayfayla sınırla (0=kapalı)",
    )

    # MUBI yenileme
    ap.add_argument(
        "--refresh-mubi",
        choices=["all", "recent"],
        help="MUBI kullanılabilirliğini güncelle (all veya recent)",
    )
    ap.add_argument(
        "--mubi-recent",
        type=int,
        default=50,
        help="--refresh-mubi recent için kaç sayfa (created) taranacak",
    )

    args = ap.parse_args()
    print("[debug] starting...")

    # 1) Cover set
    if args.set_covers:
        _set_covers(args)
        return

    # 2) MUBI yenileme
    if args.refresh_mubi:
        _refresh_mubi(args)
        return

    # 3) Eksik alanları doldurma
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by="created")
        updated = 0
        for idx, page in enumerate(pages, start=1):
            # Normal pipeline'ı kullanmak adına sahte bir liste akışı kuralım
            rows = [page]
            # args.limit varsa saygı duymak için
            tmp_args = argparse.Namespace(limit=len(rows), dry_run=args.dry_run)
            _fill_missing(tmp_args)
            updated += 1
            if args.limit and updated >= args.limit:
                break
        print(f"Done. Updated {updated} pages.")
        return

    # default
    _fill_missing(args)


if __name__ == "__main__":
    main()
