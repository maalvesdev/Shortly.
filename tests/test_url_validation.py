"""URL validation tests that do not require a database or network connection."""

import unittest

from url_service import MAX_URL_LENGTH, InvalidUrlError, normalize_url


class UrlValidationTests(unittest.TestCase):
    def test_adds_https_when_the_scheme_is_omitted(self):
        self.assertEqual(
            normalize_url("example.com/docs?topic=links#examples"),
            "https://example.com/docs?topic=links#examples",
        )

    def test_preserves_explicit_http_and_https_urls(self):
        for url in (
            "http://example.com/docs",
            "https://example.com/docs?topic=links#examples",
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_url(url), url)

    def test_normalizes_scheme_and_host_without_rewriting_path_or_query(self):
        self.assertEqual(
            normalize_url("HTTPS://EXAMPLE.COM/CaseSensitive?token=AbC#Section"),
            "https://example.com/CaseSensitive?token=AbC#Section",
        )

    def test_trims_surrounding_ordinary_spaces(self):
        self.assertEqual(
            normalize_url("  https://example.com/docs  "),
            "https://example.com/docs",
        )

    def test_accepts_ip_addresses_and_valid_explicit_ports(self):
        for url in (
            "https://127.0.0.1/docs",
            "http://192.0.2.1:8080/docs",
            "https://[2001:db8::1]/docs",
            "http://[::1]:5000/docs",
            "https://example.com:443/docs",
            "https://example.com:65535/docs",
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_url(url), url)

    def test_accepts_internationalized_domain_names(self):
        for url, expected in (
            ("https://münich.example/docs", "https://xn--mnich-kva.example/docs"),
            ("https://例え.テスト/docs", "https://xn--r8jz45g.xn--zckzah/docs"),
            ("https://faß.de/docs", "https://xn--fa-hia.de/docs"),
            ("https://xn--mnich-kva.example/docs", "https://xn--mnich-kva.example/docs"),
            (
                "https://münich.example/über?name=café#übersicht",
                "https://xn--mnich-kva.example/über?name=café#übersicht",
            ),
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_url(url), expected)

    def test_accepts_ascii_double_hyphen_labels_in_ascii_and_idn_hosts(self):
        for url, expected in (
            ("https://ab--cd.example/docs", "https://ab--cd.example/docs"),
            (
                "https://ab--cd.münich.example/docs",
                "https://ab--cd.xn--mnich-kva.example/docs",
            ),
            (
                "https://münich.ab--cd.example/docs",
                "https://xn--mnich-kva.ab--cd.example/docs",
            ),
        ):
            with self.subTest(url=url):
                self.assertEqual(normalize_url(url), expected)

    def test_preserves_percent_encoded_path_query_and_fragment_data(self):
        url = (
            "https://example.com/a%20b/%2F"
            "?next=https%3A%2F%2Fother.example%2F&value=%00%0A"
            "#part%201"
        )
        self.assertEqual(normalize_url(url), url)

    def test_rejects_missing_or_non_text_values(self):
        for value in (None, "", "   ", 123, {}, []):
            with self.subTest(value=value):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(value)

    def test_rejects_non_http_schemes(self):
        for url in (
            "ftp://example.com/file",
            "file:///tmp/file",
            "ws://example.com/socket",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_rejects_missing_hosts_and_malformed_authorities(self):
        for url in (
            "https://",
            "https:///example.com",
            "https://@",
            "https://user@",
            "https://:443/docs",
            "http://[broken",
            "https://[]/docs",
            "https://[::1]suffix/docs",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_rejects_unsupported_bracketed_ipvfuture_hosts(self):
        for url in (
            "https://[v1.example]/docs",
            "https://[vF.example]/docs",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_rejects_embedded_credentials(self):
        for url in (
            "https://user:password@example.com/docs",
            "https://user@example.com/docs",
            "https://:password@example.com/docs",
            "https://@example.com/docs",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_rejects_invalid_hostnames(self):
        for url in (
            "https://foo space.com",
            "https://-example.com",
            "https://example-.com",
            "https://example..com",
            "https://.example.com",
            "https://_example.com",
            "https://exa%mple.com",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_enforces_dns_label_length(self):
        valid_url = "https://" + "a" * 63 + ".example/docs"
        self.assertEqual(normalize_url(valid_url), valid_url)
        with self.assertRaises(InvalidUrlError):
            normalize_url("https://" + "a" * 64 + ".example/docs")

    def test_rejects_invalid_ports_as_validation_errors(self):
        for port in ("", "badport", "-1", "65536", "1.5"):
            with self.subTest(port=port):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(f"https://example.com:{port}/docs")

    def test_rejects_raw_control_characters_before_parsing(self):
        for url in (
            "https://example.com/\r\nInjected: yes",
            "https://exa\tmple.com/docs",
            "https://example.com/a\x00b",
            "https://example.com/a\x7fb",
            "\nhttps://example.com/docs",
            "https://example.com/docs\n",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_rejects_malformed_percent_escapes(self):
        for url in (
            "https://example.com/path%",
            "https://example.com/path%2",
            "https://example.com/path%ZZ",
            "https://example.com/?value=%2G",
            "https://example.com/#part%zz",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_rejects_raw_backslashes(self):
        for url in (
            r"https:\\example.com\docs",
            r"https://example.com\other-host",
            r"https://example.com/docs?next=\other-host",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InvalidUrlError):
                    normalize_url(url)

    def test_accepts_the_exact_normalized_length_limit(self):
        prefix = "https://example.com/"
        url = prefix + "a" * (MAX_URL_LENGTH - len(prefix))
        self.assertEqual(normalize_url(url), url)
        self.assertEqual(normalize_url(f"  {url}  "), url)

    def test_rejects_urls_above_the_normalized_length_limit(self):
        prefix = "https://example.com/"
        url = prefix + "a" * (MAX_URL_LENGTH - len(prefix) + 1)
        with self.assertRaises(InvalidUrlError):
            normalize_url(url)

    def test_length_limit_includes_an_automatically_added_scheme(self):
        prefix = "example.com/"
        value = prefix + "a" * (MAX_URL_LENGTH - len("https://") - len(prefix))
        self.assertEqual(normalize_url(value), f"https://{value}")
        with self.assertRaises(InvalidUrlError):
            normalize_url(value + "a")

    def test_length_limit_includes_idna_hostname_expansion(self):
        raw_prefix = "https://münich.example/"
        normalized_prefix = "https://xn--mnich-kva.example/"
        path = "a" * (MAX_URL_LENGTH - len(normalized_prefix))
        self.assertEqual(
            normalize_url(raw_prefix + path), normalized_prefix + path
        )
        with self.assertRaises(InvalidUrlError):
            normalize_url(raw_prefix + path + "a")

    def test_length_limit_applies_after_ipv6_compression(self):
        raw_prefix = "https://[2001:0db8:0000:0000:0000:0000:0000:0001]/"
        normalized_prefix = "https://[2001:db8::1]/"
        path = "a" * (MAX_URL_LENGTH - len(normalized_prefix))
        self.assertGreater(len(raw_prefix + path), MAX_URL_LENGTH)
        self.assertEqual(
            normalize_url(raw_prefix + path), normalized_prefix + path
        )
        with self.assertRaises(InvalidUrlError):
            normalize_url(raw_prefix + path + "a")


if __name__ == "__main__":
    unittest.main()
