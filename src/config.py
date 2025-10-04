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
# Buradaki değerler Notion’daki sütun adlarının KESİN yazımı olmalı
NOTION_COLS = {
    "name":            "Name",              # title
    "letterboxd":      "Letterboxd",        # url veya text

    "year":            "Year",              # number
    "runtime":         "Runtime (min)",     # number

    "director":        "Director",          # multi-select
    "writer":          "Writer",            # multi-select
    "cinematography":  "Cinematography",    # multi-select
    "cast_top":        "Cast (Top 3)",      # multi-select

    "poster":          "Poster",            # url
    "backdrop":        "Backdrop",          # url
    "trailer_url":     "Trailer URL",       # url

    "original_title":  "Original Title",    # rich_text
    "synopsis":        "Synopsis",          # rich_text

    "countries":       "Countries",         # multi-select
    "languages":       "Languages",         # multi-select
}
