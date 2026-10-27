import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from dotenv import dotenv_values

from app import create_app
from database import get_db
from url_service import MAX_URL_LENGTH


class UrlShortenerTests(unittest.TestCase):
    def setUp(self):
        local_settings = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
        self.database_url = os.environ.get("TEST_DATABASE_URL", local_settings.get("TEST_DATABASE_URL"))
        if not self.database_url:
            raise ValueError(
                "TEST_DATABASE_URL is required. Set it in .env or your environment "
                "to a separate PostgreSQL database named shortly_test."
            )
        if not self.database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("TEST_DATABASE_URL must be a PostgreSQL connection URL.")

        # Verify the database before application initialization writes any schema.
        with psycopg.connect(self.database_url) as connection:
            database_name = connection.execute("SELECT current_database()").fetchone()[0]
            if database_name != "shortly_test":
                raise ValueError("PostgreSQL tests must use the separate shortly_test database.")

        self.test_config = {
            "TESTING": True,
            "DATABASE_URL": self.database_url,
            "RATE_LIMIT_SECRET": "shortly-test-only",
            "RATE_LIMIT_MAX_REQUESTS": 10,
            "RATE_LIMIT_WINDOW_SECONDS": 3600,
        }
        self.app = create_app(self.test_config)
        self.client = self.app.test_client()
        self.clear_postgres_tables()
        self.addCleanup(self.clear_postgres_tables)

    def clear_postgres_tables(self):
        with self.app.app_context():
            connection = get_db()
            database_name = connection.execute("SELECT current_database() AS name").fetchone()["name"]
            if database_name != "shortly_test":
                raise ValueError("Refusing to clear a database other than shortly_test.")
            connection.execute("TRUNCATE TABLE urls, rate_limits")
            connection.commit()

    def test_creates_and_redirects_a_custom_link(self):
        response = self.client.post("/api/shorten", json={"original_url": "example.com/docs", "custom_url": "portfolio-demo"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["short_code"], "portfolio-demo")
        redirect_response = self.client.get("/portfolio-demo", follow_redirects=False)
        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(redirect_response.headers["Location"], "https://example.com/docs")
        self.assertEqual(redirect_response.headers["Cache-Control"], "no-store")

    def test_rejects_invalid_requests_with_a_useful_400(self):
        cases = ({}, {"original_url": "ftp://example.com"}, {"original_url": "example.com", "expires_in_hours": "later"})
        for payload in cases:
            response = self.client.post("/api/shorten", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.json)

    def test_invalid_requests_do_not_consume_rate_limit_quota(self):
        limited_app = create_app(
            {
                **self.test_config,
                "RATE_LIMIT_MAX_REQUESTS": 1,
                "RATE_LIMIT_WINDOW_SECONDS": 300,
            }
        )
        limited_client = limited_app.test_client()
        invalid_response = limited_client.post("/api/shorten", json={})
        valid_response = limited_client.post(
            "/api/shorten", json={"original_url": "https://example.com"}
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(valid_response.status_code, 201)

    def test_malformed_urls_do_not_create_records_or_consume_rate_limit_quota(self):
        limited_app = create_app(
            {
                **self.test_config,
                "RATE_LIMIT_MAX_REQUESTS": 1,
                "RATE_LIMIT_WINDOW_SECONDS": 300,
            }
        )
        client = limited_app.test_client()
        invalid_urls = (
            "https://@",
            "https://example.com:badport",
            "https://example.com:65536",
            "https://foo bar.com",
            "http://[broken",
            "https://[::1]suffix/docs",
            "https://999.999.999.999",
            "https://example.com/\r\nInjected: yes",
            "https://example.com/a\x00b",
            "https://example.com/\ud800",
            r"https://example.com\other-host",
            "https://example.com/%ZZ",
            "https://user:password@example.com",
            "https://example.com/" + "a" * MAX_URL_LENGTH,
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                response = client.post("/api/shorten", json={"original_url": url})
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.is_json)
                self.assertIsInstance(response.json["error"], str)
                self.assertTrue(response.json["error"])

        with limited_app.app_context():
            connection = get_db()
            self.assertEqual(connection.execute("SELECT COUNT(*) AS count FROM urls").fetchone()["count"], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) AS count FROM rate_limits").fetchone()["count"], 0)

        valid_response = client.post("/api/shorten", json={"original_url": "https://example.com"})
        self.assertEqual(valid_response.status_code, 201)

    def test_supported_url_destinations_create_links_and_redirect_successfully(self):
        cases = (
            ("https://example.com/docs?x=1#part", "https://example.com/docs?x=1#part"),
            (
                "example.com/?next=https://other.example/path",
                "https://example.com/?next=https://other.example/path",
            ),
            (
                "HTTPS://EXAMPLE.COM:8443/path?value=%2F#part",
                "https://example.com:8443/path?value=%2F#part",
            ),
            (
                "https://m\u00fcnich.example/caf\u00e9?q=%2F#part",
                "https://xn--mnich-kva.example/caf%C3%A9?q=%2F#part",
            ),
            ("https://fa\u00df.de/docs", "https://xn--fa-hia.de/docs"),
            ("http://192.0.2.1:8080/docs", "http://192.0.2.1:8080/docs"),
            ("https://[2001:db8::1]:8443/docs", "https://[2001:db8::1]:8443/docs"),
            (
                "https://example.com/a%20b?q=%252F#part%201",
                "https://example.com/a%20b?q=%252F#part%201",
            ),
            (
                "https://example.com/search?q=hello world",
                "https://example.com/search?q=hello%20world",
            ),
        )
        for index, (original_url, destination) in enumerate(cases):
            with self.subTest(original_url=original_url):
                alias = f"destination-{index}"
                response = self.client.post(
                    "/api/shorten",
                    json={"original_url": original_url, "custom_url": alias},
                )
                self.assertEqual(response.status_code, 201)
                redirect_response = self.client.get(f"/{alias}", follow_redirects=False)
                self.assertEqual(redirect_response.status_code, 302)
                self.assertEqual(redirect_response.headers["Location"], destination)

    def test_normalized_shortener_hostnames_are_still_rejected(self):
        cases = (
            ("https://shortly.example", "HTTPS://SHORTLY.EXAMPLE./existing"),
            ("https://xn--fa-hia.de", "https://fa\u00df.de/existing"),
            ("https://[2001:db8::1]", "https://[2001:0db8:0:0:0:0:0:1]/existing"),
        )
        for base_url, original_url in cases:
            with self.subTest(original_url=original_url):
                response = self.client.post(
                    "/api/shorten",
                    base_url=base_url,
                    json={"original_url": original_url},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"], "You cannot shorten a Shortly link.")

    def test_rejects_a_link_to_the_shortener_itself(self):
        response = self.client.post(
            "/api/shorten",
            base_url="https://urlshort-fhgq.onrender.com",
            json={
                "original_url": "https://urlshort-fhgq.onrender.com/wikipedia",
                "custom_url": "loop",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "You cannot shorten a Shortly link.")

    def test_rejects_an_alias_that_is_already_taken(self):
        payload = {"original_url": "https://example.com", "custom_url": "taken-link"}
        self.client.post("/api/shorten", json=payload)
        response = self.client.post("/api/shorten", json=payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json["error"],
            "This custom alias is already taken.",
        )

    def test_random_code_collision_retries_without_replacing_the_existing_link(self):
        self.client.post(
            "/api/shorten",
            json={"original_url": "https://example.com/original", "custom_url": "taken-code"},
        )
        with patch("url_service.generate_short_code", side_effect=["taken-code", "new-code"]):
            response = self.client.post(
                "/api/shorten", json={"original_url": "https://example.com/new"}
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["short_code"], "new-code")
        self.assertEqual(self.client.get("/new-code").headers["Location"], "https://example.com/new")
        self.assertEqual(
            self.client.get("/taken-code").headers["Location"], "https://example.com/original"
        )

    def test_expired_link_returns_gone_page(self):
        with self.app.app_context():
            get_db().execute("INSERT INTO urls VALUES (%s, %s, %s)", ("old-link", "https://example.com", 1))
            get_db().commit()
        for _ in range(2):
            response = self.client.get("/old-link")
            self.assertEqual(response.status_code, 410)
            self.assertIn(b"This link has expired.", response.data)
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_missing_link_is_not_cached(self):
        response = self.client.get("/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_rate_limit_blocks_the_third_request_when_limit_is_two(self):
        limited_app = create_app(
            {
                **self.test_config,
                "RATE_LIMIT_MAX_REQUESTS": 2,
                "RATE_LIMIT_WINDOW_SECONDS": 300,
            }
        )
        limited_client = limited_app.test_client()
        payload = {"original_url": "https://example.com"}
        self.assertEqual(limited_client.post("/api/shorten", json=payload).status_code, 201)
        self.assertEqual(limited_client.post("/api/shorten", json=payload).status_code, 201)
        response = limited_client.post("/api/shorten", json=payload)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "300")


class ApplicationConfigurationTests(unittest.TestCase):
    def test_missing_database_url_explains_how_to_configure_postgresql(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                create_app({"TESTING": True})

    def test_non_postgresql_database_settings_are_rejected(self):
        for database_url in ("database.db", "sqlite:///database.db", "mysql://localhost/shortly"):
            with self.subTest(database_url=database_url):
                with self.assertRaisesRegex(RuntimeError, "PostgreSQL connection URL"):
                    create_app({"TESTING": True, "DATABASE_URL": database_url})


if __name__ == "__main__":
    unittest.main()
