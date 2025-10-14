# src/main.py
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional

from src.config import NOTION_COLS
from src import notion as nz
from src import letterboxd as lb
from src import tmdb as tdb
from src import omdb as odb


# ---------- küçük yardımcılar ----------

def _safe_lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _add_if_empty(props: Dict[str, Any],
                  page_props: Dict[str, Any],
                  key: str,
                  value: Any) -> None:
    """
    Notion'da hedef property boşsa doldurmak için yardımcı.
    key: NOTION_COLS içindeki mantıksal anahtar (örn. "year", "director")
    value: yazılacak ham değer (string, sayı, multi-select list vs.)
    """
    col = NOTION_COLS.get(key)
    if not col:
        return
    existing = nz.read_prop(page_props, col)
    if existing in (None, "", [], {}):
        nz.write_prop(props, col, value)


def _set_title_if_new(page_id: str, page_props: Dict[str, Any], title: Optional[str]) -> bool:
    """
    Sayfa 'New page' ya da boş ise başlığı set eder.
    True dönerse başlık güncellendi demektir.
    """
    if not title:
        return False
    current_title = nz.get_page_title(page_props) or ""
    if current_title == "" or _safe_lower(current_title) == "new page":
        nz.set_page_title(page_id, title)
        return True
    return False


# ---------- çekirdek senkron ----------

def mode_force_recent(force_recent: int = 20, by: str = "created") -> int:
    """
    Son N sayfayı (default 20) getirir, Letterboxd linki olanlarda eksik alanları doldurur.
    Sıralama: created_time (by='created') ya da last_edited_time (by='edited')
    Dönüş: güncellenen sayfa adedi
    """
    print(f"Running recent sync (last {force_recent})")
    updated = 0

    # created_time / last_edited_time ile sayfaları getir
    pages = nz.iter_recent_pages(force_recent=force_recent, by=by)

    for idx, page in enumerate(pages, start=1):
        props = page["properties"]
        pid = page["id"]

        # Letterboxd linki gerekiyor
        lb_url = nz.read_prop(props, NOTION_COLS.get("letterboxd"))
        if not lb_url:
            # Hız için, LB linki yoksa pas
            continue

        row_title = nz.get_page_title(props) or ""
        print(f"[debug] row {idx}: title='{row_title}' url='{lb_url}'")

        # Letterboxd meta
        meta = {}
        try:
            meta = lb.parse(lb_url)  # {"title","year","imdb_id","tmdb_id"}
        except Exception:
            meta = {}

        title = meta.get("title")
        year = meta.get("year")
        imdb_id = meta.get("imdb_id")
        tmdb_id = meta.get("tmdb_id")

        # Başlık gerekiyorsa önce onu set et
        changed_title = _set_title_if_new(pid, props, title)

        # Boş alanları yazmak için properties payload
        payload: Dict[str, Any] = {}

        # --- Yıl ---
        if year:
            _add_if_empty(payload, props, "year", year)

        # --- Poster / Backdrop (TMDb öncelikli, sonra OMDb) ---
        poster_url = None
        backdrop_url = None
        languages = []
        countries = []
        director = []
        writer = []
        cinematography = []
        runtime = None
        original_title = None

        # TMDb/OMDb lookup: elinde ID varsa çok hızlı
        tmd: Dict[str, Any] = {}
        omd: Dict[str, Any] = {}

        try:
            if tmdb_id:
                tmd = tdb.fetch_tmdb_movie(tmdb_id)
            elif imdb_id:
                tmd = tdb.find_by_imdb(imdb_id)
            elif title and year:
                tmd = tdb.search_movie(title, year=year)
            elif title:
                tmd = tdb.search_movie(title)
        except Exception:
            tmd = {}

        try:
            if imdb_id:
                omd = odb.fetch_by_imdb(imdb_id)
            elif title and year:
                omd = odb.search_first(title, year=year)
            elif title:
                omd = odb.search_first(title)
        except Exception:
            omd = {}

        # görseller
        poster_url = tdb.best_poster(tmd) or odb.poster_url(omd)
        backdrop_url = tdb.best_backdrop(tmd)

        # metadatalar
        original_title = tdb.original_title(tmd)
        runtime = tdb.runtime_minutes(tmd) or odb.runtime_minutes(omd)
        languages = tdb.languages(tmd) or odb.languages(omd)
        countries = tdb.countries(tmd) or odb.countries(omd)
        director = tdb.directors(tmd) or odb.directors(omd)
        writer = tdb.writers(tmd) or odb.writers(omd)
        cinematography = tdb.cinematographers(tmd)  # OMDb’da çoğu zaman yok

        # --- yazmalar ---
        _add_if_empty(payload, props, "original_title", original_title)
        if runtime:
            _add_if_empty(payload, props, "runtime", runtime)
        if languages:
            _add_if_empty(payload, props, "languages", languages)
        if countries:
            _add_if_empty(payload, props, "countries", countries)
        if director:
            _add_if_empty(payload, props, "director", director)
        if writer:
            _add_if_empty(payload, props, "writer", writer)
        if cinematography:
            _add_if_empty(payload, props, "cinematography", cinematography)

        # Poster & Backdrop file’larını Notion’a indir (boşsa)
        if poster_url and not nz.read_prop(props, NOTION_COLS.get("poster")):
            try:
                file_obj = nz.download_image_to_files(poster_url, filename_hint="poster")
                nz.write_prop(payload, NOTION_COLS.get("poster"), file_obj)
            except Exception:
                pass

        if backdrop_url and not nz.read_prop(props, NOTION_COLS.get("backdrop")):
            try:
                file_obj = nz.download_image_to_files(backdrop_url, filename_hint="backdrop")
                nz.write_prop(payload, NOTION_COLS.get("backdrop"), file_obj)
            except Exception:
                pass

        # Payload’ı gönder
        if payload:
            try:
                nz.update_page(pid, payload, existing_props=props)
                updated += 1
            except Exception as e:
                print(f"[warn] failed to update page {pid}: {e}")

        # Sadece başlık güncellendiyse de updated say
        elif changed_title:
            updated += 1

    print(f"Done. Updated {updated} pages.")
    return updated


# ---------- CLI ----------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="Notion × Letterboxd sync",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--limit", type=int, default=0, help="(kullanılmıyor)")
    p.add_argument("--dry-run", action="store_true", help="Sadece log bas, yazma")
    p.add_argument("--set-covers", action="store_true", help="Kullanımdan kalktı")
    p.add_argument("--force-recent", type=int, default=20, help="Son N sayfayı tara")
    p.add_argument("--by", choices=["created", "edited"], default="created",
                   help="Sıralama: created_time ya da last_edited_time")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    # kuru çalışma istenirse Notion yazma fonksiyonlarını no-op yapabilirsiniz;
    # burada sadece log’layıp devam ediyoruz.
    try:
        mode_force_recent(force_recent=args.force_recent, by=args.by)
    except nz.notion_client.errors.APIResponseError as e:  # type: ignore[attr-defined]
        # Notion istemcisinin dışarı verdiği hatalar için görünür log
        print(f"[error] Notion API error: {getattr(e, 'message', e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
