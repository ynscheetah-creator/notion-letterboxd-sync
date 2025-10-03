import os

# --- Notion kimlikleri (GitHub Secrets'tan geliyor) ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

# --- Notion sütun eşlemesi (Notion’daki adlarla birebir aynı olmalı) ---
NOTION_COLS = {
    "title": "Name",
    "letterboxd": "Letterboxd",
    "year": "Year",
    "director": "Director",
    "writer": "Writer",
    "cinematography": "Cinematography",
    "runtime": "Runtime (min)",
    "poster": "Poster",

    # Ek alanlar
    "original_title": "Original Title",
    "synopsis": "Synopsis",
    "countries": "Countries",
    "languages": "Languages",
    "cast_top": "Cast (Top 3)",
    "backdrop": "Backdrop",
    "trailer_url": "Trailer URL",
}

# Varsayılan limit (main.py import ediyor)
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "200"))

# API anahtarları (GitHub Secrets)
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
