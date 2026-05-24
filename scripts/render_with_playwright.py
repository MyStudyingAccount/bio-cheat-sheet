#!/usr/bin/env python3
"""Render Common Planner pages with Playwright and save the fully rendered HTML.

Usage example (run locally on your Mac where browsers are installed):

  python scripts/render_with_playwright.py \
    --site-path yang2526 \
    --date 2026-05-18 \
    --perspective week \
    --output-dir ./scraped_commonplanner

This script requires Playwright to be installed locally:

  python -m pip install playwright
  python -m playwright install firefox chrome

The script will open a headless browser, navigate to the page URL,
wait for network activity to finish, then write the page's HTML to
`{output_dir}/calendar_pages/{date}.rendered.html`.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.commonplanner.com"


def build_url(site_path: str, target_date: str, perspective: str) -> str:
    return f"{BASE_URL}/sites/{site_path}?date={target_date}&perspective={perspective}"


def render_page(site_path: str, target_date: str, perspective: str, output_dir: str, browser_name: str = "firefox") -> Path:
    url = build_url(site_path, target_date, perspective)
    out_dir = Path(output_dir) / "calendar_pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{target_date}.rendered.html"

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch(headless=True)
        context = browser.new_context(user_agent="bio-cheat-sheet-renderer/1.0")
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        # allow some time for any late-rendering scripts
        time.sleep(0.5)
        content = page.content()
        out_file.write_text(content, encoding="utf-8")
        browser.close()

    return out_file


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render Common Planner pages with Playwright and save HTML")
    p.add_argument("--site-path", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--perspective", default="week")
    p.add_argument("--output-dir", default="./scraped_commonplanner")
    p.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="firefox")
    return p


def main() -> int:
    args = build_parser().parse_args()
    out = render_page(args.site_path, args.date, args.perspective, args.output_dir, browser_name=args.browser)
    print(f"Saved rendered HTML: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
