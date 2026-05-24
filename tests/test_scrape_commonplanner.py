import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from scrape_commonplanner import (
    build_card_stack_index,
    classify_link,
    extract_links,
    extract_links_from_card_stack,
    generate_week_dates,
    resolve_link_type,
    scrape,
)


class WeekDateTests(unittest.TestCase):
    def test_generate_week_dates_inclusive(self):
        generated = generate_week_dates(date(2026, 1, 7), date(2026, 1, 22))
        self.assertEqual(
            generated,
            [date(2026, 1, 7), date(2026, 1, 14), date(2026, 1, 21)],
        )

    def test_generate_week_dates_rejects_invalid_range(self):
        with self.assertRaises(ValueError):
            generate_week_dates(date(2026, 1, 8), date(2026, 1, 7))


class LinkExtractionTests(unittest.TestCase):
    def test_extract_and_classify_links(self):
        html = """
        <html><body>
          <a href=\"/notes/week1.pdf\">Week 1 notes</a>
          <a href=\"https://www.youtube.com/watch?v=abc123\">Lecture</a>
          <iframe src=\"https://youtu.be/xyz\"></iframe>
          <a href=\"https://example.com/homework\">Homework</a>
          https://cdn.example.edu/files/handout.pdf
        </body></html>
        """

        page_url = "https://www.commonplanner.com/sites/yang2526?date=2026-01-07&perspective=week"
        links = extract_links(html, page_url)

        self.assertIn("https://www.commonplanner.com/notes/week1.pdf", links)
        self.assertIn("https://www.youtube.com/watch?v=abc123", links)
        self.assertIn("https://youtu.be/xyz", links)
        self.assertIn("https://example.com/homework", links)
        self.assertIn("https://cdn.example.edu/files/handout.pdf", links)

        classified = {link: classify_link(link) for link in links}
        self.assertEqual(classified["https://www.commonplanner.com/notes/week1.pdf"], "pdf")
        self.assertEqual(classified["https://www.youtube.com/watch?v=abc123"], "youtube")
        self.assertEqual(classified["https://youtu.be/xyz"], "youtube")
        self.assertEqual(classified["https://example.com/homework"], "external")

    def test_extract_links_from_data_attributes(self):
        html = """
        <html><body>
          <div data-href=\"/files/handout.pdf\"></div>
          <div data-url=\"https://www.youtube.com/watch?v=data123\"></div>
        </body></html>
        """

        page_url = "https://www.commonplanner.com/sites/yang2526?date=2026-01-07&perspective=week"
        links = extract_links(html, page_url)

        self.assertIn("https://www.commonplanner.com/files/handout.pdf", links)
        self.assertIn("https://www.youtube.com/watch?v=data123", links)

        classified = {link: classify_link(link) for link in links}
        self.assertEqual(classified["https://www.commonplanner.com/files/handout.pdf"], "pdf")
        self.assertEqual(classified["https://www.youtube.com/watch?v=data123"], "youtube")

    def test_extract_links_from_card_stack(self):
        page_url = "https://www.commonplanner.com/sites/yang2526?date=2026-05-18&perspective=week"
        card_stack_document = {
            "data": {
                "attributes": {
                    "cards": [
                        {
                            "attributes": {
                                "value": '<p><a href="https://www.youtube.com/watch?v=abc123">Lecture</a></p>',
                                "attachments": [
                                    {
                                        "url": "https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw",
                                        "title": "Handout.pdf",
                                    }
                                ],
                            }
                        }
                    ]
                }
            }
        }

        links = extract_links_from_card_stack(card_stack_document, page_url)
        self.assertIn("https://www.youtube.com/watch?v=abc123", links)
        self.assertIn("https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw", links)

    def test_resolve_link_type_probes_non_suffix_pdf(self):
        response = Mock()
        response.headers.get_content_type.return_value = "application/pdf"
        response.headers.get.return_value = ""
        response.read.return_value = b""

        with patch("scrape_commonplanner.urlopen", return_value=response):
            self.assertEqual(
                resolve_link_type("https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw", 30, "test-agent"),
                "pdf",
            )

    def test_resolve_link_type_keeps_html_links_external(self):
        response = Mock()
        response.headers.get_content_type.return_value = "text/html"
        response.headers.get.return_value = ""
        response.read.return_value = b"<htm"

        with patch("scrape_commonplanner.urlopen", return_value=response):
            self.assertEqual(
                resolve_link_type("https://example.com/homework", 30, "test-agent"),
                "external",
            )

    def test_resolve_link_type_handles_context_manager_response(self):
        mock_response = Mock()
        mock_response.headers.get_content_type.return_value = "application/pdf"
        mock_response.headers.get.return_value = ""
        mock_response.read.return_value = b""

        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_response
        mock_ctx.__exit__.return_value = None

        with patch("scrape_commonplanner.urlopen", return_value=mock_ctx):
            self.assertEqual(
                resolve_link_type("https://cdn.filestackcontent.com/context-pdf", 30, "test-agent"),
                "pdf",
            )

    def test_classify_link_rejects_suffix_lookalikes(self):
        self.assertEqual(classify_link("https://notyoutube.com/watch?v=abc"), "external")
        self.assertEqual(classify_link("https://evilcommonplanner.com/page"), "external")


class ApiScrapeTests(unittest.TestCase):
    def test_build_card_stack_index(self):
        document = {
            "included": [
                {
                    "type": "course",
                    "attributes": {
                        "calendar": {
                            "dates": [
                                {
                                    "id": "2026-05-18",
                                    "attributes": {"cardStackId": "stack-1"},
                                },
                                {
                                    "id": "2026-05-19",
                                    "attributes": {"cardStackId": "stack-2"},
                                },
                            ]
                        }
                    },
                }
            ]
        }

        self.assertEqual(
            build_card_stack_index(document),
            {"2026-05-18": "stack-1", "2026-05-19": "stack-2"},
        )

    def test_scrape_uses_api_card_stacks(self):
        class_website_document = {
            "included": [
                {"type": "planbook", "id": "planbook-1", "attributes": {}, "relationships": {}},
                {
                    "type": "course",
                    "id": "course-1",
                    "attributes": {
                        "calendar": {
                            "dates": [
                                {
                                    "id": "2026-05-18",
                                    "attributes": {"cardStackId": "stack-1"},
                                }
                            ]
                        }
                    },
                    "relationships": {},
                },
                {
                    "type": "class-website",
                    "id": "class-website-1",
                    "attributes": {"slug": "yang2526"},
                    "relationships": {},
                },
            ]
        }
        card_stack_document = {
            "data": {
                "attributes": {
                    "cards": [
                        {
                            "attributes": {
                                "value": '<p><a href="https://www.youtube.com/watch?v=abc123">Lecture</a></p>',
                                "attachments": [
                                    {
                                        "url": "https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw",
                                        "title": "Handout.pdf",
                                    }
                                ],
                            }
                        }
                    ]
                }
            }
        }

        def fake_fetch_url(url, timeout, user_agent):
            if url == "https://www.commonplanner.com/api/v4/class_websites_by_slug/yang2526":
                return json.dumps(class_website_document).encode("utf-8")
            if url == "https://www.commonplanner.com/api/v4/card_stacks/stack-1":
                return json.dumps(card_stack_document).encode("utf-8")
            raise AssertionError(f"Unexpected URL: {url}")

        pdf_response = Mock()
        pdf_response.headers.get_content_type.return_value = "application/pdf"
        pdf_response.headers.get.return_value = ""
        pdf_response.read.return_value = b""

        def fake_urlopen(req, timeout):
            url = getattr(req, "full_url", str(req))
            if url == "https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw":
                return pdf_response
            raise AssertionError(f"Unexpected probe URL: {url}")

        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            with patch("scrape_commonplanner.fetch_url", side_effect=fake_fetch_url), patch(
                "scrape_commonplanner.urlopen", side_effect=fake_urlopen
            ):
                summary = scrape(
                    site_path="yang2526",
                    start_date=date(2026, 5, 18),
                    end_date=date(2026, 5, 18),
                    perspective="week",
                    output_dir=output_dir,
                    timeout=30,
                    delay_seconds=0,
                    skip_download_pdfs=True,
                    user_agent="test-agent",
                )

            self.assertEqual(summary["pages"][0]["error"], "")
            link_types = {entry["url"]: entry["type"] for entry in summary["pages"][0]["links"]}
            self.assertEqual(link_types["https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw"], "pdf")
            self.assertEqual(link_types["https://www.youtube.com/watch?v=abc123"], "youtube")
            self.assertTrue((output_dir / "calendar_pages" / "2026-05-18.json").exists())

        def test_scrape_writes_reconstructed_html(self):
            class_website_document = {
                "included": [
                    {"type": "course", "attributes": {"calendar": {"dates": [{"id": "2026-05-18", "attributes": {"cardStackId": "stack-1"}}]}}}
                ]
            }
            card_stack_document = {
                "data": {
                    "attributes": {
                        "cards": [
                            {
                                "attributes": {
                                            "value": '<p><a href="https://www.youtube.com/watch?v=abc123">Lecture</a></p>',
                                            "summary": "This is a brief summary line.",
                                    "attachments": [
                                        {"url": "https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw", "title": "Handout.pdf"}
                                    ],
                                }
                            }
                        ]
                    }
                }
            }

            def fake_fetch_url(url, timeout, user_agent):
                if url == "https://www.commonplanner.com/api/v4/class_websites_by_slug/yang2526":
                    return json.dumps(class_website_document).encode("utf-8")
                if url == "https://www.commonplanner.com/api/v4/card_stacks/stack-1":
                    return json.dumps(card_stack_document).encode("utf-8")
                raise AssertionError(f"Unexpected URL: {url}")

            pdf_response = Mock()
            pdf_response.headers.get_content_type.return_value = "application/pdf"
            pdf_response.headers.get.return_value = ""
            pdf_response.read.return_value = b""

            def fake_urlopen(req, timeout):
                url = getattr(req, "full_url", str(req))
                if url == "https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw":
                    return pdf_response
                raise AssertionError(f"Unexpected probe URL: {url}")

            with TemporaryDirectory() as tmp_dir:
                output_dir = Path(tmp_dir)
                with patch("scrape_commonplanner.fetch_url", side_effect=fake_fetch_url), patch(
                    "scrape_commonplanner.urlopen", side_effect=fake_urlopen
                ):
                    summary = scrape(
                        site_path="yang2526",
                        start_date=date(2026, 5, 18),
                        end_date=date(2026, 5, 18),
                        perspective="week",
                        output_dir=output_dir,
                        timeout=30,
                        delay_seconds=0,
                        skip_download_pdfs=True,
                        user_agent="test-agent",
                    )

                html_file = output_dir / "calendar_pages" / "2026-05-18.html"
                self.assertTrue(html_file.exists())
                content = html_file.read_text(encoding="utf-8")
                self.assertIn("https://cdn.filestackcontent.com/l0MyQIWSZ22902qfk8Tw", content)
                self.assertIn("https://www.youtube.com/watch?v=abc123", content)


if __name__ == "__main__":
    unittest.main()
