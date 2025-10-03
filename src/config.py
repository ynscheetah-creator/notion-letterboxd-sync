# src/config.py
from __future__ import annotations
import os
from typing import Dict

# -----------------------------
# Secrets (ENV’den okunuyor)
# -----------------------------
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()
OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "").strip()
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()

# -----------------------------
# Notion Column Mapping
# -----------------------------
# Buradaki adlar birebir Notion’daki sütun adlarınla eşleşmeli
NOTION_COLS: Dict[str, str] = {
    "name": "Name",
    "letterboxd": "Letterboxd URI",

    "year": "Year",
    "runtime": "Runtime (min)",

    "poster": "Poster",
    "backdrop": "Backdrop",
    "trailer_url": "Trailer URL",

    "original_title": "Original Title",
    "synopsis": "Overview / Plot",

    "director": "Director",
    "writer": "Writer",
    "cinematography": "Cinematography",
    "cast_top": "Cast Top",
    "countries": "Countries",
    "languages": "Languages",
}
