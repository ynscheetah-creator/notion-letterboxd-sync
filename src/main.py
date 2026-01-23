from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional

from .config import NOTION_COLS
from . import notion as nz
from . import letterboxd as lb
from . import tmdb
from . import omdb


def _norm_people(v) -> List[str]:
    """İsimleri normalize et (virgülle ayrılmış string veya liste)"""
    if not v:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    return []


def _norm_tags(v) -> List[str]:
    """Tag'leri normalize et (virgülle ayrılmış string veya liste)"""
    if not v:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    if isinstance(v, list):
        return [str(s).strip() for s in v if str(s).strip()]
    return []


def _need(props: Dict[str, Any], key: str) -> bool:
    """Notion'da property boş mu kontrol et"""
    col_name = NOTION_COLS.get(key)
    if not col_name:
        return False
    return not nz.read_prop(props, col_name)


def _extract_title_from_letterboxd_url(lb_url: str) -> Optional[str]:
    """
    Letterboxd URL'inden film adını çıkarmaya çalış.
    Örnek: https://letterboxd.com/film/little-forest/ -> "little forest"
    """
    if not lb_url:
        return None
    
    # URL'den slug'ı çıkar
    import re
    match = re.search(r'letterboxd\.com/film/([^/]+)', lb_url)
    if match:
        slug = match.group(1)
        # Slug'ı başlığa çevir: "little-forest" -> "Little Forest"
        title = slug.replace('-', ' ').title()
        # Yıl varsa kaldır (örn: "drifting-2021" -> "Drifting")
        title = re.sub(r'\s+\d{4}$', '', title)
        return title
    
    return None


def build_payload_for_page(props: Dict[str, Any], lb_url: str) -> Dict[str, Any]:
    """
    Bir Notion sayfasındaki eksikleri tamamlamak için 
    Notion property formatında payload hazırlar.
    """
    payload: Dict[str, Any] = {}

    print(f"[info] Processing: {lb_url}")

    # 1. Letterboxd'dan meta getir
    meta = {}
    try:
        meta = lb.parse(lb_url) or {}
    except Exception as e:
        print(f"[warn] lb.parse failed: {e}")

    # 2. Letterboxd başarısız olduysa, alternatif kaynaklardan dene
    tmdb_id = meta.get("tmdb_id")
    imdb_id = meta.get("imdb_id")
    title_from_meta = meta.get("title")
    year_from_meta = meta.get("year")
    
    tmd = {}
    omd = {}
    
    if tmdb_id:
        # TMDb ID varsa direkt fetch
        try:
            tmd = tmdb.fetch_movie(tmdb_id) or {}
            print(f"[debug] TMDb data fetched via ID")
        except Exception as e:
            print(f"[warn] tmdb.fetch_movie failed: {e}")
    
    if not tmd:
        # TMDb ID yoksa, başka yollarla dene
        search_title = None
        search_year = year_from_meta
        
        # Öncelik 1: Letterboxd'dan gelen title
        if title_from_meta:
            search_title = title_from_meta
        
        # Öncelik 2: Notion'daki sayfa adı
        if not search_title:
            page_title = nz.get_page_title(props)
            if page_title and page_title.lower() not in ["new page", "untitled", ""]:
                search_title = page_title
        
        # Öncelik 3: Letterboxd URL'inden çıkar
        if not search_title:
            search_title = _extract_title_from_letterboxd_url(lb_url)
        
        if search_title:
            print(f"[info] Searching TMDb for: {search_title}")
            try:
                tmd = tmdb.fetch_by_title(search_title, year=search_year) or {}
                if tmd:
                    print(f"[debug] TMDb data fetched via title search")
            except Exception as e:
                print(f"[warn] tmdb.fetch_by_title failed: {e}")
    
    # OMDb verileri (IMDb ID varsa)
    final_imdb_id = imdb_id or tmd.get("imdb_id")
    if final_imdb_id:
        try:
            omd = omdb.fetch_by_imdb(final_imdb_id) or {}
            print(f"[debug] OMDb data fetched")
        except Exception as e:
            print(f"[warn] omdb.fetch_by_imdb failed: {e}")
    
    # Hiç veri bulunamadıysa çık
    if not tmd and not omd:
        print(f"[warn] No movie data found, skipping")
        return payload

    # Title (sayfa adı)
    if _need(props, "name"):
        current_title = nz.get_page_title(props) or ""
        if (not current_title) or current_title.lower() == "new page":
            title = title_from_meta or tmd.get("title") or omd.get("Title")
            if title:
                payload[NOTION_COLS["name"]] = nz._title(title)
                print(f"[debug] Setting title: {title}")

    # Year
    if _need(props, "year"):
        y = year_from_meta or tmd.get("year") or omd.get("Year")
        if y:
            try:
                year_int = int(str(y)[:4])
                payload[NOTION_COLS["year"]] = nz._num(year_int)
                print(f"[debug] Setting year: {year_int}")
            except Exception:
                pass

    # Director
    if _need(props, "director"):
        vals = _norm_people(tmd.get("directors") or omd.get("Director"))
        if vals:
            payload[NOTION_COLS["director"]] = nz._multi(vals)
            print(f"[debug] Setting director: {vals}")

    # Writer
    if _need(props, "writer"):
        vals = _norm_people(tmd.get("writers") or omd.get("Writer"))
        if vals:
            payload[NOTION_COLS["writer"]] = nz._multi(vals)
            print(f"[debug] Setting writer: {vals}")

    # Cinematography
    if _need(props, "cinematography"):
        vals = _norm_people(tmd.get("cinematography") or omd.get("Cinematography"))
        if vals:
            payload[NOTION_COLS["cinematography"]] = nz._multi(vals)
            print(f"[debug] Setting cinematography: {vals}")

    # Runtime
    if _need(props, "runtime"):
        rt = tmd.get("runtime") or omd.get("Runtime")
        if isinstance(rt, str) and "min" in rt:
            try:
                rt = int(rt.split()[0])
            except Exception:
                rt = None
        if rt:
            try:
                payload[NOTION_COLS["runtime"]] = nz._num(int(rt))
                print(f"[debug] Setting runtime: {rt}")
            except Exception:
                pass

    # Languages
    if _need(props, "languages"):
        vals = _norm_tags(tmd.get("languages") or omd.get("Language"))
        if vals:
            payload[NOTION_COLS["languages"]] = nz._multi(vals)

    # Countries
    if _need(props, "countries"):
        vals = _norm_tags(tmd.get("production_countries") or omd.get("Country"))
        if vals:
            payload[NOTION_COLS["countries"]] = nz._multi(vals)

    # Cast (Top 3)
    if _need(props, "cast_top"):
        vals = _norm_people(tmd.get("cast_top") or omd.get("Actors"))
        if vals:
            payload[NOTION_COLS["cast_top"]] = nz._multi(vals[:3])

    # Poster
    if _need(props, "poster"):
        poster = tmd.get("poster_url") or omd.get("Poster")
        if poster and poster != "N/A":
            payload[NOTION_COLS["poster"]] = nz._url(poster)
            print(f"[debug] Setting poster")

    # Backdrop
    if _need(props, "backdrop"):
        backdrop = tmd.get("backdrop_url")
        if backdrop:
            payload[NOTION_COLS["backdrop"]] = nz._url(backdrop)
            print(f"[debug] Setting backdrop")

    # Trailer
    if _need(props, "trailer_url"):
        tmdb_id_for_trailer = meta.get("tmdb_id") or tmd.get("id")
        if tmdb_id_for_trailer:
            try:
                videos = tmdb._get(f"{tmdb.BASE}/movie/{tmdb_id_for_trailer}/videos")
                if videos and videos.get("results"):
                    for vid in videos["results"]:
                        if vid.get("type") == "Trailer" and vid.get("site") == "YouTube":
                            yt_key = vid.get("key")
                            if yt_key:
                                payload[NOTION_COLS["trailer_url"]] = nz._url(f"https://www.youtube.com/watch?v={yt_key}")
                                print(f"[debug] Setting trailer")
                                break
            except Exception as e:
                print(f"[warn] Failed to fetch trailer: {e}")

    # Original Title
    if _need(props, "original_title"):
        orig = tmd.get("original_title") or omd.get("Title")
        if orig:
            payload[NOTION_COLS["original_title"]] = nz._rich(orig)

    # Synopsis
    if _need(props, "synopsis"):
        synopsis = tmd.get("synopsis") or omd.get("Plot")
        if synopsis and synopsis != "N/A":
            payload[NOTION_COLS["synopsis"]] = nz._rich(synopsis)
    
    # Streaming (TR platformları + MUBI global)
    if _need(props, "streaming"):
        tmdb_id_for_streaming = meta.get("tmdb_id") or tmd.get("id")
        if tmdb_id_for_streaming:
            try:
                streaming_data = tmdb.get_streaming_availability(tmdb_id_for_streaming)
                if streaming_data:
                    payload[NOTION_COLS["streaming"]] = nz._multi(streaming_data)
                    print(f"[debug] Setting streaming: {streaming_data}")
            except Exception as e:
                print(f"[warn] Failed to fetch streaming data: {e}")

    return payload


def mode_refresh_mubi(args) -> int:
    """Tüm sayfalarda streaming availability'yi yenile (TR + MUBI global)"""
    mode = args.refresh_mubi or "all"
    print(f"[info] Refreshing streaming availability (mode={mode})")
    
    updated = 0
    skipped = 0
    
    for idx, page in enumerate(nz.iter_all_pages(), start=1):
        props = page["properties"]
        pid = page["id"]
        
        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            skipped += 1
            continue
        
        try:
            # TMDb ID'yi bul
            meta = lb.parse(lb_url) or {}
            tmdb_id = meta.get("tmdb_id")
            
            # Letterboxd başarısızsa title ile ara
            if not tmdb_id:
                search_title = meta.get("title") or nz.get_page_title(props) or _extract_title_from_letterboxd_url(lb_url)
                if search_title:
                    tmd = tmdb.fetch_by_title(search_title) or {}
                    tmdb_id = tmd.get("id")
            
            if not tmdb_id:
                print(f"[{idx}] No TMDb ID for {lb_url}")
                skipped += 1
                continue
            
            streaming_data = tmdb.get_streaming_availability(tmdb_id)
            current_streaming = nz.read_prop(props, NOTION_COLS.get("streaming")) or []
            
            if set(streaming_data) != set(current_streaming):
                payload = {
                    NOTION_COLS["streaming"]: nz._multi(streaming_data)
                }
                nz.update_page(pid, payload, existing_props=props)
                updated += 1
                print(f"[{idx}] Updated streaming: {streaming_data}")
            else:
                print(f"[{idx}] Streaming unchanged: {streaming_data}")
                
        except Exception as e:
            print(f"[{idx}] Error: {e}")
            skipped += 1
    
    print(f"[done] Updated {updated} pages, skipped {skipped}")
    return updated


def mode_set_covers(args) -> int:
    """Backdrop URL'si olan tüm sayfalara cover ayarla"""
    print(f"[info] Setting covers from backdrop URLs")
    
    updated = 0
    
    for idx, page in enumerate(nz.iter_all_pages(), start=1):
        props = page["properties"]
        pid = page["id"]
        
        backdrop = nz.read_prop(props, NOTION_COLS.get("backdrop"))
        if not backdrop:
            continue
        
        try:
            nz.update_cover(pid, backdrop)
            updated += 1
            print(f"[{idx}] Set cover for page {pid}")
        except Exception as e:
            print(f"[{idx}] Error setting cover: {e}")
    
    print(f"[done] Set {updated} covers")
    return updated


def mode_force_recent(args) -> int:
    """Son eklenen/düzenlenen N sayfayı doldur"""
    force_recent = args.force_recent or 20
    by = "created"

    print(f"[info] Running recent sync (last {force_recent})")
    pages = nz.iter_recent_pages(force_recent=force_recent, by=by)

    updated = 0
    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        print(f"[{idx}/{force_recent}] Processing page {pid}")
        payload = build_payload_for_page(props, lb_url)
        if payload:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            print(f"[success] Updated page {pid}")
        else:
            print(f"[skip] No updates needed for {pid}")

    print(f"[done] Updated {updated} pages.")
    return updated


def mode_normal(args) -> int:
    """Normal mod: Letterboxd URL'i olan ve boş alanları olan sayfaları doldur"""
    limit = args.limit or 0
    print(f"[info] Starting normal sync (limit={limit if limit > 0 else 'unlimited'})")

    pages = nz.iter_pages_needing_fill(limit=limit)
    updated = 0

    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            continue

        print(f"[{idx}] Processing page {pid}")
        payload = build_payload_for_page(props, lb_url)
        if payload:
            nz.update_page(pid, payload, existing_props=props)
            updated += 1
            print(f"[success] Updated page {pid}")
        else:
            print(f"[skip] No updates needed for {pid}")

    print(f"[done] Updated {updated} pages.")
    return updated


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="Notion × Letterboxd sync",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--limit", type=int, default=0, 
                   help="Normal modda güncellenecek sayfa sınırı (0=sınırsız)")
    p.add_argument("--force-recent", type=int, default=0, 
                   help="Son N sayfayı (created/edited) modunda doldur")
    p.add_argument("--set-covers", action="store_true", 
                   help="Backdrop URL'lerini cover olarak ayarla (tek seferlik)")
    p.add_argument("--refresh-mubi", type=str, default="", 
                   help="Streaming availability'yi yenile - TR platformları + MUBI global (all/recent)")
    p.add_argument("--dry-run", action="store_true", 
                   help="Sadece ne yapacağını göster, Notion'a yazma")
    return p


def main():
    args = build_arg_parser().parse_args()

    if args.dry_run:
        print("[DRY RUN] Simülasyon modu - hiçbir şey değiştirilmeyecek")
    
    try:
        if args.refresh_mubi:
            updated = mode_refresh_mubi(args)
        elif args.set_covers:
            updated = mode_set_covers(args)
        elif args.force_recent and args.force_recent > 0:
            updated = mode_force_recent(args)
        else:
            updated = mode_normal(args)

        print(f"\n[SUCCESS] Total updated: {updated} pages.")
        return 0
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
