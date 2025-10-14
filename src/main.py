# src/main.py
from __future__ import annotations

import argparse
from typing import Any, Dict, List

from .config import NOTION_COLS
from . import notion as nz
from . import letterboxd as lb
from . import tmdb
from . import omdb


# ------------------------------
# Yardımcılar
# ------------------------------
def _norm_people(v) -> List[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    return []


def _norm_tags(v) -> List[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    return []


def _need(props: Dict[str, Any], key: str) -> bool:
    """Notion'da property boş mu?"""
    return not nz.read_prop(props, NOTION_COLS.get(key))


# ------------------------------
# Doldurma mantığı (tek sayfa)
# ------------------------------
def build_payload_for_page(props: Dict[str, Any], lb_url: str) -> Dict[str, Any]:
    """
    Bu fonksiyon, bir Notion sayfasındaki eksikleri tamamlamak için payload hazırlar.
    Yalnızca boş alanlara değer yazar.
    """
    payload: Dict[str, Any] = {}

    # --- meta getir
    meta = {}
    try:
        meta = lb.parse(lb_url) or {}
    except Exception as e:
        print(f"[warn] lb.parse failed for {lb_url}: {e}")

    tmd = {}
    if meta.get("tmdb_id"):
        try:
            tmd = tmdb.fetch_movie(meta["tmdb_id"]) or {}
        except Exception as e:
            print(f"[warn] tmdb.fetch_movie failed: {e}")

    omd = {}
    if meta.get("imdb_id"):
        try:
            omd = omdb.fetch_by_imdb(meta["imdb_id"]) or {}
        except Exception as e:
            print(f"[warn] omdb.fetch_by_imdb failed: {e}")

    # --- Title (sayfa adı)
    current_title = nz.get_page_title(props) or ""
    if (not current_title) or current_title.lower() == "new page":
        if meta.get("title"):
            payload["Name"] = nz._title(meta["title"])

    # --- Year
    if _need(props, "year"):
        y = meta.get("year") or tmd.get("year") or omd.get("Year")
        if y:
            try:
                payload[NOTION_COLS["year"]] = nz._num(int(y))
            except Exception:
                pass

    # --- Director
    if _need(props, "director"):
        vals = _norm_people(tmd.get("directors") or omd.get("Director"))
        if vals:
            payload[NOTION_COLS["director"]] = nz._multi(vals)

    # --- Writer
    if _need(props, "writer"):
        vals = _norm_people(tmd.get("writers") or omd.get("Writer"))
        if vals:
            payload[NOTION_COLS["writer"]] = nz._multi(vals)

    # --- Cinematography
    if _need(props, "cinematography"):
        vals = _norm_people(tmd.get("cinematography") or omd.get("Cinematography"))
        if vals:
            payload[NOTION_COLS["cinematography"]] = nz._multi(vals)

    # --- Runtime
    if _need(props, "runtime"):
        rt = tmd.get("runtime") or omd.get("Runtime")
        if isinstance(rt, str) and rt.endswith("min"):
            try:
                rt = int(rt.split(" ")[0])
            except Exception:
                rt = None
        if rt:
            try:
                payload[NOTION_COLS["runtime"]] = nz._num(int(rt))
            except Exception:
                pass

    # --- Languages
    if _need(props, "languages"):
        vals = _norm_tags(tmd.get("languages") or omd.get("Language"))
        if vals:
            payload[NOTION_COLS["languages"]] = nz._multi(vals)

    # --- Countries
    if _need(props, "countries"):
        vals = _norm_tags(tmd.get("production_countries") or omd.get("Country"))
        if vals:
            payload[NOTION_COLS["countries"]] = nz._multi(vals)

    # --- Poster
    if _need(props, "poster"):
        poster = tmd.get("poster_url") or omd.get("Poster")
        if poster:
            payload[NOTION_COLS["poster"]] = nz._url(poster)

    # --- Backdrop
    if _need(props, "backdrop"):
        backdrop = tmd.get("backdrop_url")
        if backdrop:
            payload[NOTION_COLS["backdrop"]] = nz._url(backdrop)

    # --- Original Title
    if _need(props, "original_title"):
        orig = tmd.get("original_title") or omd.get("Title")
        if orig:
            # Orijinal başlık, sayfa başlığı ile aynıysa yazmak istemeyebiliriz; ama
            # “orijinal title” alanı boşsa yazmak genelde işimize yarar.
            payload[NOTION_COLS["original_title"]] = nz._rich(orig)

    return payload


# ------------------------------
# Mod: Son N sayfayı tara (created/edited)
# ------------------------------
def mode_force_recent(args) -> int:
    force_recent = args.force_recent or 20
    by = "created"  # "created" -> created_time, "edited" -> last_edited_time (istersen arg ile açarsın)

    print(f"Running recent sync (last {force_recent})")
    pages = nz.iter_recent_pages(force_recent=force_recent, by=by)

    updated = 0
    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        payload = build_payload_for_page(props, lb_url)
        if payload:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1

    print(f"Done. Updated {updated} pages.")
    return updated


# ------------------------------
# Mod: Normal doldurma (gerekenleri)
# ------------------------------
def mode_normal(args) -> int:
    limit = args.limit or 0  # 0 = sınırsız
    print("[debug] starting...")

    pages = nz.iter_pages_needing_fill(limit=limit)
    updated = 0

    for page in pages:
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        payload = build_payload_for_page(props, lb_url)
        if payload:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1

    print(f"Done. Updated {updated} pages.")
    return updated


# ------------------------------
# CLI
# ------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="Notion × Letterboxd sync",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--limit", type=int, default=0, help="Normal modda güncellenecek sayfa sınırı (0=sınırsız)")
    p.add_argument("--set-covers", action="store_true", help="(opsiyonel) Kapak/backdrop tek seferlik ayarlansın")
    p.add_argument("--force-recent", type=int, default=0, help="Son N sayfayı (created/edited) modunda doldur")
    p.add_argument("--dry-run", action="store_true", help="Sadece ne yapacağını yaz, Notion'a yazma (opsiyonel)")
    return p


# src/main.py (son kısım)

def main():
    args = build_arg_parser().parse_args()

    if args.force_recent and args.force_recent > 0:
        updated = mode_force_recent(args)
    else:
        updated = mode_normal(args)

    print(f"[ok] Updated {updated} pages.")
    return 0  # <-- HER ZAMAN 0 DÖN

if __name__ == "__main__":
    import sys
    sys.exit(main())  # main 0 döndüğü için job success olur
