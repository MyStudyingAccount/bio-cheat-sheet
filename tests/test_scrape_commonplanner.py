import unittest
from datetime import date
from unittest.mock import Mock, patch

from scrape_commonplanner import classify_link, extract_links, generate_week_dates, resolve_link_type


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
        # Simulate urlopen returning a context manager (real response object)
        mock_response = Mock()
        mock_response.headers.get_content_type.return_value = "application/pdf"
        mock_response.headers.get.return_value = ""
        mock_response.read.return_value = b""

        mock_ctx = Mock()
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


if __name__ == "__main__":
    unittest.main()
