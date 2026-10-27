"""Startup configuration tests; database initialization is stubbed out."""

import os
import unittest
from unittest.mock import patch

from app import create_app


class ApplicationConfigurationTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        database_init = patch("app.init_db")
        self.init_db = database_init.start()
        self.addCleanup(database_init.stop)
        self.config = {"TESTING": True, "DATABASE_URL": "postgresql://localhost/shortly_test"}

    def test_missing_database_url_explains_how_to_configure_postgresql(self):
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
            create_app({"TESTING": True})
        self.init_db.assert_not_called()

    def test_non_postgresql_database_settings_are_rejected(self):
        for database_url in (
            "database.db",
            "sqlite:///database.db",
            "mysql://localhost/shortly",
        ):
            with self.subTest(database_url=database_url):
                with self.assertRaisesRegex(RuntimeError, "PostgreSQL connection URL"):
                    create_app({**self.config, "DATABASE_URL": database_url})
        self.init_db.assert_not_called()

    def test_rate_limit_settings_require_positive_integers_before_database_access(self):
        for name in ("RATE_LIMIT_MAX_REQUESTS", "RATE_LIMIT_WINDOW_SECONDS"):
            for value in (
                0,
                -1,
                True,
                1.5,
                None,
                "",
                "0",
                "-1",
                "bad",
                "1.5",
                "1e999",
            ):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(RuntimeError, name):
                        create_app({**self.config, name: value})
        self.init_db.assert_not_called()

    def test_invalid_environment_settings_report_the_setting_name(self):
        for name in (
            "RATE_LIMIT_MAX_REQUESTS",
            "RATE_LIMIT_WINDOW_SECONDS",
            "PROXY_HOPS",
        ):
            for value in ("invalid", "-1"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}),
                ):
                    with self.assertRaisesRegex(RuntimeError, name):
                        create_app(self.config)
        self.init_db.assert_not_called()

    def test_integer_environment_settings_are_parsed_and_defaults_are_direct(self):
        app = create_app(self.config)
        self.assertEqual(app.config["PROXY_HOPS"], 0)
        with patch.dict(
            os.environ,
            {
                "RATE_LIMIT_MAX_REQUESTS": "2",
                "RATE_LIMIT_WINDOW_SECONDS": "300",
                "PROXY_HOPS": "1",
            },
        ):
            app = create_app(self.config)
        self.assertEqual(app.config["RATE_LIMIT_MAX_REQUESTS"], 2)
        self.assertEqual(app.config["RATE_LIMIT_WINDOW_SECONDS"], 300)
        self.assertEqual(app.config["PROXY_HOPS"], 1)

    def test_proxy_hops_require_a_nonnegative_integer(self):
        for value in (-1, "-1", True, 1.5, "1.5", "", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "PROXY_HOPS"):
                    create_app({**self.config, "PROXY_HOPS": value})
        self.init_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
