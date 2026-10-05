"""Business rules and persistence operations for shortened links."""

import re
import secrets
import string
import time
from urllib.parse import urlparse

from database import execute, get_db, is_integrity_error

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
SHORT_CODE_ALPHABET = string.ascii_letters + string.digits


class InvalidUrlError(ValueError):
    pass


class InvalidAliasError(ValueError):
    pass


class AliasTakenError(ValueError):
    pass


def validate_short_url(
    original_url, custom_alias, expires_in_hours, max_expiry_hours, shortener_host
):
    normalized_url = normalize_url(original_url)
    reject_shortener_url(normalized_url, shortener_host)
    expires_at = calculate_expiry(expires_in_hours, max_expiry_hours)
    alias = normalize_alias(custom_alias)
    return normalized_url, alias, expires_at


def create_short_url(normalized_url, alias, expires_at):
    """Persist validated link data and return its unique short code."""
    if alias:
        if not insert_url(alias, normalized_url, expires_at):
            raise AliasTakenError()
        return alias
    for _ in range(5):
        code = generate_short_code()
        if insert_url(code, normalized_url, expires_at):
            return code
    raise RuntimeError("Unable to generate a unique short code. Please try again.")


def normalize_url(value):
    if not isinstance(value, str) or not value.strip():
        raise InvalidUrlError("Enter a URL to shorten.")
    value = value.strip()
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidUrlError("Enter a valid http or https URL.")
    return value


def reject_shortener_url(url, shortener_host):
    """Prevent links that redirect back into this shortener's own routes."""
    destination_host = urlparse(url).hostname
    current_host = urlparse(f"//{shortener_host}").hostname
    if (
        destination_host
        and current_host
        and destination_host.lower() == current_host.lower()
    ):
        raise InvalidUrlError("You cannot shorten a Shortly link.")


def normalize_alias(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise InvalidAliasError("Custom aliases must be text.")
    alias = value.strip()
    if not ALIAS_PATTERN.fullmatch(alias):
        raise InvalidAliasError(
            "Use 3–32 letters, numbers, hyphens, or underscores for the custom alias."
        )
    return alias


def calculate_expiry(value, max_expiry_hours):
    if value is None or value == "":
        return None
    try:
        hours = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidUrlError("Expiration must be a whole number of hours.") from error
    if not 1 <= hours <= max_expiry_hours:
        raise InvalidUrlError(f"Expiration must be between 1 and {max_expiry_hours} hours.")
    return int(time.time()) + hours * 3_600


def generate_short_code():
    return "".join(secrets.choice(SHORT_CODE_ALPHABET) for _ in range(7))


def insert_url(short_code, original_url, expires_at):
    try:
        execute(
            "INSERT INTO urls (short_code, original_url, expires_at) VALUES (?, ?, ?)",
            (short_code, original_url, expires_at),
        )
        get_db().commit()
    except Exception as error:
        if is_integrity_error(error):
            return False
        raise
    return True


def get_destination(short_code):
    row = execute(
        "SELECT original_url, expires_at FROM urls WHERE short_code = ?", (short_code,)
    ).fetchone()
    if row is None:
        return None
    if row["expires_at"] is not None and time.time() >= row["expires_at"]:
        return "expired"
    return row["original_url"]
