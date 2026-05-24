#!/usr/bin/env python3
"""Scrape weekly Common Planner pages and collect resource links."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

BASE_URL = "https://www.commonplanner.com"
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "a" and attr_map.get("href"):
            self.links.append(attr_map["href"])
        if tag in {"iframe", "video", "source", "embed"} and attr_map.get("src"):
            self.links.append(attr_map["src"])


def parse_date(raw_date: str) -> date:
    return datetime.strptime(raw_date, "%Y-%m-%d").date()


def generate_week_dates(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    output: list[date] = []
    current = start_date
    while current <= end_date:
        output.append(current)
        current += timedelta(days=7)
    return output


def _url_has_pdf_query(url: str) -> bool:
    parsed = urlparse(url)
    for values in parse_qs(parsed.query).values():
        for value in values:
            if ".pdf" in value.lower():
                return True
    return False


def classify_link(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if path.endswith(".pdf") or _url_has_pdf_query(url):
        return "pdf"
    if _host_matches_domain(host, "youtube.com") or _host_matches_domain(host, "youtu.be"):
        return "youtube"
    if _host_matches_domain(host, "commonplanner.com"):
        return "commonplanner"
    return "external"


def _response_looks_like_pdf(response) -> bool:
    content_type = response.headers.get_content_type().lower()
    if content_type == "application/pdf":
        return True

    content_disposition = response.headers.get("Content-Disposition", "").lower()
    if ".pdf" in content_disposition:
        return True

    return False


def _probe_pdf_url(url: str, timeout: int, user_agent: str) -> bool:
    req = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Range": "bytes=0-15",
        },
    )
    try:
        res = urlopen(req, timeout=timeout)
        # Support both real responses (context managers) and mocked responses
        entered = None
        try:
            if hasattr(res, "__enter__"):
                entered = res.__enter__()
                response = entered
            else:
                response = res

            if _response_looks_like_pdf(response):
                return True
            return response.read(4) == b"%PDF"
        finally:
            if entered is not None:
                try:
                    res.__exit__(None, None, None)
                except Exception:
                    pass
    except Exception:  # noqa: BLE001
        return False


def resolve_link_type(url: str, timeout: int, user_agent: str) -> str:
    link_type = classify_link(url)
    if link_type == "youtube" or link_type == "pdf":
        return link_type

    if _probe_pdf_url(url, timeout=timeout, user_agent=user_agent):
        return "pdf"

    return link_type


def _host_matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _normalize_link(link: str, page_url: str) -> str | None:
    link = link.strip()
    if not link or link.startswith("#") or link.startswith("javascript:"):
        return None
    return urljoin(page_url, link)


def extract_links(html: str, page_url: str) -> list[str]:
    extractor = LinkExtractor()
    extractor.feed(html)

    links = list(extractor.links)
    links.extend(URL_PATTERN.findall(html))

    normalized: set[str] = set()
    for link in links:
        normalized_link = _normalize_link(link, page_url)
        if normalized_link:
            normalized.add(normalized_link)

    return sorted(normalized)


def safe_name_from_url(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or fallback
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def fetch_url(url: str, timeout: int, user_agent: str) -> bytes:
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    rows = list(rows)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["date", "page_url", "type", "link"])
        writer.writeheader()
        writer.writerows(rows)


def scrape(
    *,
    site_path: str,
    start_date: date,
    end_date: date,
    perspective: str,
    output_dir: Path,
    timeout: int,
    delay_seconds: float,
    skip_download_pdfs: bool,
    user_agent: str,
) -> dict:
    page_dir = output_dir / "calendar_pages"
    pdf_dir = output_dir / "pdfs"
    output_dir.mkdir(parents=True, exist_ok=True)
    page_dir.mkdir(parents=True, exist_ok=True)
    if not skip_download_pdfs:
        pdf_dir.mkdir(parents=True, exist_ok=True)

    week_dates = generate_week_dates(start_date, end_date)

    summary = {
        "site_path": site_path,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "perspective": perspective,
        "week_dates": [d.isoformat() for d in week_dates],
        "pages": [],
        "pdf_downloads": [],
    }

    pdf_links: set[str] = set()
    csv_rows: list[dict[str, str]] = []

    for target_date in week_dates:
        page_url = f"{BASE_URL}/sites/{site_path}?date={target_date.isoformat()}&perspective={perspective}"
        local_html = page_dir / f"{target_date.isoformat()}.html"

        try:
            html = fetch_url(page_url, timeout=timeout, user_agent=user_agent).decode("utf-8", errors="replace")
            local_html.write_text(html, encoding="utf-8")
            page_links = extract_links(html, page_url)
            classified_links = [
                {"url": link, "type": resolve_link_type(link, timeout=timeout, user_agent=user_agent)}
                for link in page_links
            ]
            page_error = ""
        except Exception as exc:  # noqa: BLE001
            classified_links = []
            page_error = str(exc)

        for entry in classified_links:
            csv_rows.append(
                {
                    "date": target_date.isoformat(),
                    "page_url": page_url,
                    "type": entry["type"],
                    "link": entry["url"],
                }
            )
            if entry["type"] == "pdf":
                pdf_links.add(entry["url"])

        summary["pages"].append(
            {
                "date": target_date.isoformat(),
                "page_url": page_url,
                "saved_html": str(local_html),
                "link_count": len(classified_links),
                "error": page_error,
                "links": classified_links,
            }
        )

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    if not skip_download_pdfs:
        for index, pdf_url in enumerate(sorted(pdf_links), start=1):
            filename = f"{index:03d}_{safe_name_from_url(pdf_url, fallback=f'file_{index}')}"
            target_file = pdf_dir / filename
            status = "ok"
            error_message = ""
            try:
                target_file.write_bytes(fetch_url(pdf_url, timeout=timeout, user_agent=user_agent))
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error_message = str(exc)
            summary["pdf_downloads"].append(
                {
                    "url": pdf_url,
                    "saved_file": str(target_file),
                    "status": status,
                    "error": error_message,
                }
            )
            if delay_seconds > 0:
                time.sleep(delay_seconds)

    write_json(output_dir / "scrape_summary.json", summary)
    write_csv(output_dir / "links.csv", csv_rows)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Common Planner weekly pages and save links/PDFs"
    )
    parser.add_argument("--site-path", default="yang2526", help="Path after /sites/")
    parser.add_argument("--start-date", default="2026-01-07", help="YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-05-29", help="YYYY-MM-DD")
    parser.add_argument("--perspective", default="week", help="Planner perspective")
    parser.add_argument(
        "--output-dir",
        default="./scraped_commonplanner",
        help="Directory where files are written",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.5,
        help="Delay between requests",
    )
    parser.add_argument(
        "--skip-download-pdfs",
        action="store_true",
        help="Only save pages and links, do not download PDF files",
    )
    parser.add_argument(
        "--user-agent",
        default="bio-cheat-sheet-scraper/1.0",
        help="User-Agent header for requests",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)

    summary = scrape(
        site_path=args.site_path,
        start_date=start_date,
        end_date=end_date,
        perspective=args.perspective,
        output_dir=Path(args.output_dir),
        timeout=args.timeout,
        delay_seconds=args.delay_seconds,
        skip_download_pdfs=args.skip_download_pdfs,
        user_agent=args.user_agent,
    )

    print(
        f"Saved {len(summary['pages'])} weekly pages, "
        f"{sum(1 for page in summary['pages'] for link in page['links'] if link['type'] == 'pdf')} PDF links found, "
        f"{sum(1 for page in summary['pages'] for link in page['links'] if link['type'] == 'youtube')} YouTube links found."
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
