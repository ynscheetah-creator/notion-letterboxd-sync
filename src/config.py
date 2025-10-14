from __future__ import annotations
import os

# ENV’den oku (GitHub Actions secrets ile gelir)
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip()
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()

if not NOTION_TOKEN or not NOTION_DATABASE_ID:
    raise RuntimeError("NOTION_TOKEN ve NOTION_DATABASE_ID zorunlu.")

# Notion veritabanı kolon adlarını burada eşleyin
NOTION_COLS = {
    "name": "Name",                 # title
    "letterboxd": "Letterboxd",     # url ya da text (siz URL kullandınız)
    "poster": "Poster",             # url
    "backdrop": "Backdrop",         # url
    "trailer_url": "Trailer URL",   # url

    "year": "Year",                 # number
    "runtime": "Runtime (min)",     # number

    "original_title": "Original Title",  # rich_text
    "synopsis": "Overview / Plot",       # rich_text

    "director": "Director",         # multi-select
    "writer": "Writer",             # multi-select
    "cinematography": "Cinematography",  # multi-select
    "cast_top": "Cast (Top 3)",     # multi-select
    "countries": "Countries",       # multi-select
    "languages": "Languages",       # multi-select

    "mubi": "MUBI",                 # multi-select (YENİ: ISO ülke kodları)
}
