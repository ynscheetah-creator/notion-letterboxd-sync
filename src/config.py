from __future__ import annotations
import os

# --- Secrets
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

# --- Notion column mapping (property names)
# ÖNEMLİ: Sağ taraftaki değerler Notion'daki kolon isimleriyle TAM OLARAK eşleşmeli!
# Büyük/küçük harf, boşluk, parantez - hepsi önemli.

NOTION_COLS = {
    "name": "Name",                    # Title property
    "letterboxd": "Letterboxd",        # URL
    "year": "Year",                    # Number
    "runtime": "Runtime (min)",        # Number
    "poster": "Poster",                # URL
    "backdrop": "Backdrop",            # URL
    "trailer_url": "Trailer URL",      # URL - DİKKAT: "Trailer URL" (boşluk var!)
    "original_title": "Original Title", # Text
    "synopsis": "Synopsis",            # Text
    
    # Multi-select properties
    "director": "Director",
    "writer": "Writer",
    "cinematography": "Cinematography",
    "cast_top": "Cast (Top 3)",
    "countries": "Countries",
    "languages": "Languages",
    "mubi": "MUBI",
}
