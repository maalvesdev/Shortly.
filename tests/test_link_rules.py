"""Alias and expiration rules tested without a database or network connection."""

import unittest
from unittest.mock import patch

from url_service import (
    InvalidAliasError,
    InvalidUrlError,
    calculate_expiry,
    normalize_alias,
)


class AliasRulesTests(unittest.TestCase):
    def test_omitted_or_empty_alias_means_generate_a_code(self):
        for value in (None, ""):
            with self.subTest(value=value):
                self.assertIsNone(normalize_alias(value))

    def test_accepts_valid_alias_boundaries_and_trims_surrounding_spaces(self):
        for value, expected in (
            ("abc", "abc"),
            ("a" * 32, "a" * 32),
            ("  my-Link_1  ", "my-Link_1"),
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_alias(value), expected)

    def test_rejects_invalid_alias_lengths_characters_and_types(self):
        for value in (
            "ab",
            "a" * 33,
            "   ",
            "my link",
            "my.link",
            "my/link",
            "café",
            True,
            False,
            123,
            1.0,
            [],
            {},
        ):
            with self.subTest(value=value):
                with self.assertRaises(InvalidAliasError):
                    normalize_alias(value)


class ExpirationRulesTests(unittest.TestCase):
    def test_omitted_or_empty_expiration_means_never(self):
        for value in (None, ""):
            with self.subTest(value=value):
                self.assertIsNone(calculate_expiry(value, max_expiry_hours=8760))

    def test_accepts_integer_hours_and_strings_at_the_allowed_boundaries(self):
        now = 1_700_000_000.75
        with patch("url_service.time.time", return_value=now):
            for value, hours in (
                (1, 1),
                ("1", 1),
                (8760, 8760),
                ("8760", 8760),
                (" 24 ", 24),
            ):
                with self.subTest(value=value):
                    self.assertEqual(
                        calculate_expiry(value, max_expiry_hours=8760),
                        int(now) + hours * 3600,
                    )

    def test_rejects_hours_outside_the_allowed_range(self):
        for value in (0, -1, 8761, "0", "-1", "8761"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(InvalidUrlError, "between 1 and 8760"):
                    calculate_expiry(value, max_expiry_hours=8760)

    def test_rejects_floats_booleans_objects_and_non_integer_strings(self):
        for value in (
            1.0,
            1.5,
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            False,
            [],
            {},
            "later",
            "1.5",
            "NaN",
            "inf",
            "1e2",
            "   ",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(InvalidUrlError, "whole number of hours"):
                    calculate_expiry(value, max_expiry_hours=8760)


if __name__ == "__main__":
    unittest.main()
