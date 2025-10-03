import os

# Map your Notion property names here (case-sensitive)
NOTION_COLS = {
    "title": "Name",
    "letterboxd": "Letterboxd",
    "year": "Year",
    "director": "Director",
    "writer": "Writer",
    "cinematography": "Cinematography",
    "runtime": "Runtime (min)",
    "poster": "Poster",
}

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

OMDB_API_KEY = os.getenv("OMDB_API_KEY")  # optional
TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # optional

DEFAULT_LIMIT = 100
