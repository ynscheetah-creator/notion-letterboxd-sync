from __future__ import annotations
import os

# --- Secrets
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

# --- Notion column mapping (property names)
# Sağ taraftakileri birebir Notion veritabanındaki kolon adlarınla eşleştir.
NOTION_COLS = {
    "name": "Name",
    "letterboxd": "Letterboxd",
    "year": "Year",
    "runtime": "Runtime (min)",
    "poster": "Poster",
    "backdrop": "Backdrop",
    "trailer_url": "Trailer",
    "original_title": "Original Title",
    "synopsis": "Synopsis",

    # multi-select olarak kullanacağınlar:
    "director": "Director",
    "writer": "Writer",
    "cinematography": "Cinematography",
    "cast_top": "Cast (Top 3)",
    "countries": "Countries",
    "languages": "Languages",

    # MUBI bölgeleri (multi-select)
    "mubi": "MUBI",
}
