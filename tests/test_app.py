import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from dotenv import dotenv_values

from app import create_app
from database import get_db


class UrlShortenerTests(unittest.TestCase):
    def setUp(self):
        local_settings = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
        self.database_url = os.environ.get(
            "TEST_DATABASE_URL", local_settings.get("TEST_DATABASE_URL")
        )
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
            "PROXY_HOPS": 0,
        }
        self.app = create_app(self.test_config)
        self.client = self.app.test_client()
        self.clear_postgres_tables()
        self.addCleanup(self.clear_postgres_tables)
        # All requests share a controlled clock; no test can straddle a real window.
        clock_patch = patch("time.time", return_value=1_800_000_000.0)
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def clear_postgres_tables(self):
        with self.app.app_context():
            connection = get_db()
            database_name = connection.execute(
                "SELECT current_database() AS name"
            ).fetchone()["name"]
            if database_name != "shortly_test":
                raise ValueError("Refusing to clear a database other than shortly_test.")
            connection.execute("TRUNCATE TABLE urls, rate_limits")
            connection.commit()

    def test_creates_and_redirects_a_custom_link(self):
        response = self.client.post(
            "/api/shorten",
            json={"original_url": "example.com/docs", "custom_url": "portfolio-demo"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["short_code"], "portfolio-demo")
        redirect_response = self.client.get("/portfolio-demo", follow_redirects=False)
        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(redirect_response.headers["Location"], "https://example.com/docs")
        self.assertEqual(redirect_response.headers["Cache-Control"], "no-store")

    def test_invalid_requests_return_json_without_records_or_quota_use(self):
        limited_app = create_app(
            {
                **self.test_config,
                "RATE_LIMIT_MAX_REQUESTS": 1,
                "RATE_LIMIT_WINDOW_SECONDS": 300,
            }
        )
        client = limited_app.test_client()
        # Detailed URL, alias, and expiry rules live in the database-free tests.
        invalid_payloads = (
            None,
            [],
            "text",
            True,
            123,
            {},
            {"original_url": None},
            {"original_url": []},
            {"original_url": {}},
            {"original_url": True},
            {"original_url": 123},
            {"original_url": "http://[broken"},
            {"original_url": "https://example.com:badport"},
            {"original_url": "https://example.com/\ud800"},
            {"original_url": "example.com", "custom_url": []},
            {"original_url": "example.com", "custom_url": {}},
            {"original_url": "example.com", "custom_url": True},
            {"original_url": "example.com", "custom_url": 123},
            {"original_url": "example.com", "custom_url": "x"},
            {"original_url": "example.com", "expires_in_hours": []},
            {"original_url": "example.com", "expires_in_hours": {}},
            {"original_url": "example.com", "expires_in_hours": True},
            {"original_url": "example.com", "expires_in_hours": 1.5},
            {"original_url": "example.com", "expires_in_hours": "later"},
        )
        request_bodies = [json.dumps(payload) for payload in invalid_payloads]
        request_bodies.extend(
            ("{", '{"original_url":"example.com","expires_in_hours":1e999}')
        )
        for body in request_bodies:
            with self.subTest(body=body):
                response = client.post(
                    "/api/shorten", data=body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.is_json)
                self.assertIsInstance(response.json["error"], str)
                self.assertTrue(response.json["error"])

        response = client.post("/api/shorten", data="original_url=example.com")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)

        with limited_app.app_context():
            connection = get_db()
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM urls"
                ).fetchone()["count"],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM rate_limits"
                ).fetchone()["count"],
                0,
            )

        valid_response = client.post("/api/shorten", json={"original_url": "https://example.com"})
        self.assertEqual(valid_response.status_code, 201)

    def test_supported_url_destinations_create_links_and_redirect_successfully(self):
        cases = (
            (
                "example.com/?next=https://other.example/path",
                "https://example.com/?next=https://other.example/path",
            ),
            (
                "https://m\u00fcnich.example/caf\u00e9?q=%2F#part",
                "https://xn--mnich-kva.example/caf%C3%A9?q=%2F#part",
            ),
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
            ("https://shortly.example", "https://shortly.example/existing"),
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
        self.assertEqual(
            self.client.get("/new-code").headers["Location"], "https://example.com/new"
        )
        self.assertEqual(
            self.client.get("/taken-code").headers["Location"], "https://example.com/original"
        )

    def test_link_expires_at_the_boundary_and_its_alias_stays_reserved(self):
        created_at = self.clock.return_value
        response = self.client.post(
            "/api/shorten",
            json={
                "original_url": "https://example.com",
                "custom_url": "old-link",
                "expires_in_hours": "1",
            },
        )
        self.assertEqual(response.status_code, 201)
        expires_at = created_at + 3600
        self.clock.return_value = expires_at - 0.001
        self.assertEqual(self.client.get("/old-link").status_code, 302)

        for now in (expires_at, expires_at + 0.001):
            self.clock.return_value = now
            response = self.client.get("/old-link")
            self.assertEqual(response.status_code, 410)
            self.assertIn(b"This link has expired.", response.data)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        response = self.client.post(
            "/api/shorten",
            json={"original_url": "https://example.com/new", "custom_url": "old-link"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"], "This custom alias is already taken.")

    def test_missing_link_is_not_cached(self):
        response = self.client.get("/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_rate_limit_is_per_client_and_resets_at_the_window_boundary(self):
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
        other_client = limited_client.post(
            "/api/shorten", json=payload, environ_overrides={"REMOTE_ADDR": "192.0.2.2"}
        )
        self.assertEqual(other_client.status_code, 201)
        window_start = self.clock.return_value
        self.clock.return_value = window_start + 299.999
        self.assertEqual(limited_client.post("/api/shorten", json=payload).status_code, 429)
        self.clock.return_value = window_start + 300
        self.assertEqual(limited_client.post("/api/shorten", json=payload).status_code, 201)
        self.assertEqual(limited_client.post("/api/shorten", json=payload).status_code, 201)
        self.assertEqual(limited_client.post("/api/shorten", json=payload).status_code, 429)

    def test_direct_requests_cannot_spoof_forwarding_headers_to_bypass_quota(self):
        app = create_app({**self.test_config, "RATE_LIMIT_MAX_REQUESTS": 1})
        client = app.test_client()
        payload = {"original_url": "https://example.com"}
        response = client.post(
            "/api/shorten",
            json=payload,
            headers={
                "X-Forwarded-For": "192.0.2.1",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "spoofed.example",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json["short_url"], f"http://localhost/{response.json['short_code']}"
        )
        response = client.post(
            "/api/shorten", json=payload, headers={"X-Forwarded-For": "192.0.2.2"}
        )
        self.assertEqual(response.status_code, 429)

    def test_configured_proxy_uses_the_rightmost_forwarded_client_and_scheme(self):
        app = create_app({**self.test_config, "RATE_LIMIT_MAX_REQUESTS": 1, "PROXY_HOPS": 1})
        client = app.test_client()
        payload = {"original_url": "https://example.com"}
        response = client.post(
            "/api/shorten",
            json=payload,
            headers={
                "X-Forwarded-For": "198.51.100.1, 192.0.2.1",
                "X-Forwarded-Proto": "http, https",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json["short_url"], f"https://localhost/{response.json['short_code']}"
        )
        response = client.post(
            "/api/shorten",
            json=payload,
            headers={"X-Forwarded-For": "198.51.100.2, 192.0.2.1"},
        )
        self.assertEqual(response.status_code, 429)
        response = client.post(
            "/api/shorten", json=payload, headers={"X-Forwarded-For": "192.0.2.2"}
        )
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
