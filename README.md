# Notion × Letterboxd Sync (via OMDb/TMDb)

A small Python tool that fills your Notion movie database using your **Letterboxd** links.

- Extracts **IMDb ID** from the Letterboxd page (via JSON‑LD).
- Pulls details from **OMDb** (director, writer, runtime, year, poster, etc.).
- Optionally falls back to **TMDb** if OMDb is not configured.
- Updates your Notion database columns.

## Notion Database Assumptions

Your database should have (case‑insensitive suggestions in parentheses):

- **Name** (title property) – movie name.
- **Letterboxd** (url) – the Letterboxd link like `https://boxd.it/ICXQ` or full `https://letterboxd.com/film/.../`.
- **Year** (number).
- **Director** (rich text).
- **Writer** (rich text).
- **Cinematography** (rich text) — optional, if available in OMDb (`Director of Photography` not separate; we try `cinematography` field if present in TMDb or parse Writers/Technical if present).
- **Runtime (min)** (number).
- **Poster** (url).

> You can rename columns, but then update the names in `src/config.py`.

## Quick Start

1. Create a virtualenv and install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill values:
   - `NOTION_TOKEN` – from https://www.notion.so/my-integrations
   - `NOTION_DATABASE_ID` – your database ID
   - `OMDB_API_KEY` – optional but recommended (get one from http://www.omdbapi.com/apikey.aspx)
   - `TMDB_API_KEY` – optional fallback (https://www.themoviedb.org/settings/api)

3. Share your Notion database with your integration (top right **Share** → **Connect**).

4. Run locally:
   ```bash
   python -m src.main --dry-run        # show what would update
   python -m src.main                  # actually update
   python -m src.main --limit 20       # process first 20 rows needing fill
   ```

## GitHub Actions (optional)

1. Push this repo to GitHub.
2. In the repo, add the following **Actions secrets**:
   - `NOTION_TOKEN`
   - `NOTION_DATABASE_ID`
   - `OMDB_API_KEY` (optional)
   - `TMDB_API_KEY` (optional)
3. Enable Actions. It runs:
   - on manual dispatch
   - every day at 03:00 UTC

You can change the schedule in `.github/workflows/sync.yml`.

## How It Works

1. Read Notion rows where `Letterboxd` has a URL and one or more target fields are empty.
2. Fetch the Letterboxd page and parse its `application/ld+json` for `sameAs` → IMDb URL to get the `tt` ID.
3. Query OMDb by IMDb ID (accurate and simple).
4. If OMDb fails and TMDb is configured, use TMDb (by IMDb ID or by movie title + year).
5. Map fields and update the Notion page.

## Notes

- Letterboxd has no official API; we use only public page metadata.
- If a field is already filled in Notion, we don't overwrite it unless you pass `--overwrite`.
- Cinematographer isn't always exposed by OMDb; TMDb sometimes provides it via crew list.

## Troubleshooting

- If nothing updates, ensure:
  - The database is shared with your integration.
  - Column names in Notion match those in `src/config.py`.
  - Your OMDb key is active and not throttled.
  - Letterboxd page is a film page (not a list, diary, or review URL).
