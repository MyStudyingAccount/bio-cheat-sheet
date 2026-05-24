# bio-cheat-sheet

## Common Planner scraper

Use `scrape_commonplanner.py` to download weekly calendar pages and collect links (including PDFs and YouTube links) from:

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

- `scraped_commonplanner/calendar_pages/*.html`: saved weekly pages
- `scraped_commonplanner/links.csv`: flattened links with type (`pdf`, `youtube`, `commonplanner`, `external`)
- `scraped_commonplanner/scrape_summary.json`: full scrape summary
- `scraped_commonplanner/pdfs/*.pdf`: downloaded PDFs (unless `--skip-download-pdfs`)
