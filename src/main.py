# src/main.py
from __future__ import annotations
import argparse, time
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
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--set-covers", action="store_true")
    ap.add_argument("--force-recent", type=int, default=0)
    args = ap.parse_args()

    print("[debug] starting...")

    # --- Tek seferlik kapak düzeltme ---
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

    # --- Son N (created_time) sayfayı doldur: ---
    if args.force_recent and args.force_recent > 0:
        print(f"Running recent sync (last {args.force_recent})")
        pages = nz.iter_recent_pages(force_recent=args.force_recent, by="created")

        updated = 0
        for idx, page in enumerate(pages, start=1):
            props = page["properties"]
            pid = page["id"]

# -------- letterboxd link var mı?
lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
if not lb_url:
    continue

def is_empty(key: str) -> bool:
    return not nz.read_prop(props, NOTION_COLS.get(key))

current_title = nz.get_page_title(props) or ""
need_title = (not current_title or current_title.lower() == "new page")

# hedef alanlardan herhangi biri boş mu?
targets = [
    "year", "director", "writer", "cinematography", "runtime",
    "languages", "countries", "poster", "backdrop", "original_title",
]
need_fields = any(is_empty(k) for k in targets)

if not (need_title or need_fields):
    continue  # bu sayfada yapacak iş yok

# -------- meta topla
lb_meta = {}
try:
    lb_meta = lb.parse(lb_url) or {}
except Exception as e:
    print(f"[warn] lb.parse failed: {e}")

tm = {}
om = {}

# TMDb (varsa)
if lb_meta.get("tmdb_id"):
    try:
        tm = tmdb.fetch_movie(lb_meta["tmdb_id"]) or {}
    except Exception as e:
        print(f"[warn] tmdb.fetch_movie failed: {e}")

# OMDb (varsa)
if lb_meta.get("imdb_id"):
    try:
        om = omdb.fetch_by_imdb(lb_meta["imdb_id"]) or {}
    except Exception as e:
        print(f"[warn] omdb.fetch_by_imdb failed: {e}")

# -------- payload hazırla (SADECE boş olanları doldur)
payload: Dict[str, Any] = {}

# Title
if need_title and (lb_meta.get("title")):
    payload["Name"] = nz._title(lb_meta["title"])

# Year
if is_empty("year"):
    y = lb_meta.get("year") or tm.get("year") or om.get("Year")
    if y:
        try:
            payload[NOTION_COLS["year"]] = nz._num(int(y))
        except Exception:
            pass

# Director / Writer / Cinematography  (multi-select)
def norm_people(v):
    if not v: return []
    if isinstance(v, str):  # "A, B, C"
        return [s.strip() for s in v.split(",") if s.strip()]
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    return []

if is_empty("director"):
    vals = norm_people(tm.get("directors") or om.get("Director"))
    if vals:
        payload[NOTION_COLS["director"]] = nz._multi(vals)

if is_empty("writer"):
    vals = norm_people(tm.get("writers") or om.get("Writer"))
    if vals:
        payload[NOTION_COLS["writer"]] = nz._multi(vals)

if is_empty("cinematography"):
    vals = norm_people(tm.get("cinematography") or om.get("Cinematography"))
    if vals:
        payload[NOTION_COLS["cinematography"]] = nz._multi(vals)

# Runtime (dakika)
if is_empty("runtime"):
    rt = tm.get("runtime") or om.get("Runtime")
    # OMDb "118 min" gibi gelebilir
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

# Languages / Countries (multi-select)
def norm_tags(v):
    if not v: return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    return []

if is_empty("languages"):
    vals = norm_tags(tm.get("languages") or om.get("Language"))
    if vals:
        payload[NOTION_COLS["languages"]] = nz._multi(vals)

if is_empty("countries"):
    vals = norm_tags(tm.get("production_countries") or om.get("Country"))
    if vals:
        payload[NOTION_COLS["countries"]] = nz._multi(vals)

# Poster / Backdrop (url)
if is_empty("poster"):
    poster = tm.get("poster_url") or om.get("Poster")
    if poster:
        payload[NOTION_COLS["poster"]] = nz._url(poster)

if is_empty("backdrop"):
    backdrop = tm.get("backdrop_url")
    if backdrop:
        payload[NOTION_COLS["backdrop"]] = nz._url(backdrop)

# Original Title
if is_empty("original_title"):
    orig = tm.get("original_title") or om.get("Title")  # OMDb'de farklı dil yoksa Title
    if orig and (not lb_meta.get("title") or orig != lb_meta.get("title")):
        payload[NOTION_COLS["original_title"]] = nz._rich(orig)

# Son olarak güncelle
if payload:
    nz.update_page(pid, payload, existing_props=props)

            payload: Dict[str, Any] = {}

            # “New page” ise Name'i Letterboxd başlığıyla doldur
            if (not title_now) or title_now.strip().lower() == "new page":
                if isinstance(meta, dict) and meta.get("title"):
                    payload["name"] = meta["title"]

            imdb_id = None
            tmdb_id = None
            if isinstance(meta, dict):
                imdb_id = meta.get("imdb_id")
                tmdb_id = meta.get("tmdb_id")

            # OMDb
            omdb_data = None
            try:
                if imdb_id and hasattr(omdb, "get_by_imdb"):
                    omdb_data = omdb.get_by_imdb(imdb_id)
            except Exception:
                omdb_data = None
            if omdb_data:
                _merge_payload(payload, _payload_from_omdb(omdb_data))

            # TMDb (tamamlama)
            need_keys = ("year", "director", "writer", "cinematography", "runtime", "poster", "backdrop")
            if not payload or any(k not in payload for k in need_keys):
                tmdb_data = None
                try:
                    if tmdb_id and hasattr(tmdb, "get_by_id"):
                        tmdb_data = tmdb.get_by_id(tmdb_id)
                except Exception:
                    tmdb_data = None
                if tmdb_data:
                    _merge_payload(payload, _payload_from_tmdb(tmdb_data))

            if not payload:
                continue

            if args.dry_run:
                print(f"[dry] Would update {payload.get('name') or title_now}: {payload}")
            else:
                nz.update_page(pid, payload, existing_props=props)
                updated += 1
                time.sleep(0.2)

        print(f"Done. Updated {updated} pages.")
        return  # <--- ÖNEMLİ: bu dal biter ve fonksiyondan çıkar

    # --- Normal eksik alanları doldurma ---
    rows = nz.iter_pages_needing_fill(limit=args.limit)
    print(f"[debug] fetched {len(rows)} rows" if isinstance(rows, list) else "[debug] fetched rows")

    updated = 0
    for idx, page in enumerate(rows, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        title_guess = nz.get_page_title(props) or None
        year_guess = None
        imdb_id = None
        tmdb_id = None

        meta = None
        try:
            meta = lb.parse(lb_url)
        except Exception:
            meta = None

        if isinstance(meta, dict):
            title_guess = meta.get("title") or title_guess
            year_guess = meta.get("year")
            imdb_id = meta.get("imdb_id")
            tmdb_id = meta.get("tmdb_id")

        print(f"[debug] row {idx}: name='{title_guess}' url='{lb_url}'")

        payload: Dict[str, Any] = {}

        # OMDb
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

        # TMDb
        if not payload or any(k not in payload for k in ("year","director","writer","cinematography","runtime","poster","backdrop")):
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
            time.sleep(0.2)

    print(f"Done. Updated {updated} pages.")

if __name__ == "__main__":
    main()
