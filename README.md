# bio-cheat-sheet

## Common Planner scraper

Use `scrape_commonplanner.py` to pull weekly class-website data from the Common Planner JSON API and collect links (including PDFs and YouTube links) from:

- `https://www.commonplanner.com/sites/yang2526`
- Date range default: `2026-01-07` through `2026-05-29`
- Perspective default: `week`

### Run

```bash
python3 scrape_commonplanner.py
```

### Useful options

```bash
python3 scrape_commonplanner.py \
  --site-path yang2526 \
  --start-date 2026-01-07 \
  --end-date 2026-05-29 \
  --perspective week \
  --output-dir ./scraped_commonplanner \
  --skip-download-pdfs
```

Outputs:

- `scraped_commonplanner/calendar_pages/*.json`: saved weekly card-stack payloads
- `scraped_commonplanner/links.csv`: flattened links with type (`pdf`, `youtube`, `commonplanner`, `external`)
- `scraped_commonplanner/scrape_summary.json`: full scrape summary
- `scraped_commonplanner/pdfs/*.pdf`: downloaded PDFs (unless `--skip-download-pdfs`)

If you need the fully rendered HTML (the DOM after client-side JavaScript runs), run the local Playwright renderer (this must be run on your Mac where browsers are installed):

Install Playwright and browsers:

```bash
python -m pip install playwright
python -m playwright install firefox chrome
```

Render a specific date to HTML:

```bash
python scripts/render_with_playwright.py --site-path yang2526 --date 2026-05-18 --perspective week --output-dir ./scraped_commonplanner
```

This writes `scraped_commonplanner/calendar_pages/2026-05-18.rendered.html` containing the post-JS DOM you can feed to an LLM.
