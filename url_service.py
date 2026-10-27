"""Business rules and persistence operations for shortened links."""

import re
import secrets
import string
import time
from ipaddress import ip_address
from urllib.parse import urlsplit

import idna
from psycopg.errors import UniqueViolation

from database import get_db

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
SHORT_CODE_ALPHABET = string.ascii_letters + string.digits
MAX_URL_LENGTH = 4_096
AUTHORITY_PATTERN = re.compile(r"(?:\[[^\[\]]+\]|[^:\[\]@]+)(?::[0-9]+)?")
HOST_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


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
    """Validate a web URL's syntax without fetching or resolving its destination."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidUrlError("Enter a URL to shorten.")
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value):
        raise InvalidUrlError("URLs must not contain control characters.")
    if "\\" in value:
        raise InvalidUrlError("URLs must not contain backslashes; encode them as %5C.")

    value = value.strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
        value = f"https://{value}"
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise InvalidUrlError("Use valid percent-encoding in the URL, such as %20 for a space.")

    try:
        value.encode("utf-8")
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise InvalidUrlError("Enter a valid http or https URL with a valid hostname and port.") from error

    if parsed.scheme not in {"http", "https"} or not hostname:
        raise InvalidUrlError("Enter a valid http or https URL.")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidUrlError("URLs containing a username or password are not supported.")
    if not AUTHORITY_PATTERN.fullmatch(parsed.netloc):
        raise InvalidUrlError("Enter a valid URL hostname and port.")
    if parsed.netloc.startswith("[") and ":" not in hostname:
        raise InvalidUrlError("Use a valid IPv6 address inside URL brackets.")

    hostname = _normalize_hostname(hostname)
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        authority = f"{authority}:{port}"

    # Preserve the path, query, and fragment, including empty ? and # markers.
    remainder = value.split("://", 1)[1]
    suffix = remainder[len(parsed.netloc):]
    normalized_url = f"{parsed.scheme}://{authority}{suffix}"
    if len(normalized_url) > MAX_URL_LENGTH:
        raise InvalidUrlError(f"URLs must be at most {MAX_URL_LENGTH} characters long.")
    return normalized_url


def _normalize_hostname(hostname):
    """Return a canonical IP address or validated ASCII/IDNA DNS hostname."""
    if "%" in hostname:
        raise InvalidUrlError("Enter a URL with a valid hostname or IP address.")
    try:
        return str(ip_address(hostname))
    except ValueError:
        pass

    try:
        mapped_hostname = idna.uts46_remap(hostname, std3_rules=True)
        labels = mapped_hostname.removesuffix(".").split(".")
        ascii_labels = []
        for label in labels:
            if label.isascii() and not label.startswith("xn--"):
                # Ordinary ASCII DNS labels need not follow IDNA's reserved-hyphen rule.
                if not HOST_LABEL_PATTERN.fullmatch(label):
                    raise InvalidUrlError("Enter a URL with a valid hostname or IP address.")
                ascii_labels.append(label)
            else:
                ascii_labels.append(idna.alabel(label).decode("ascii"))
    except idna.IDNAError as error:
        raise InvalidUrlError("Enter a URL with a valid hostname or IP address.") from error

    ascii_hostname = ".".join(ascii_labels)
    if len(ascii_hostname) > 253:
        raise InvalidUrlError("Enter a URL with a valid hostname or IP address.")
    if mapped_hostname.endswith("."):
        ascii_hostname += "."

    # Browsers interpret numeric final labels as IPv4, not ordinary DNS names.
    last_label = ascii_hostname.removesuffix(".").rsplit(".", 1)[-1]
    if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", last_label, re.IGNORECASE):
        try:
            return str(ip_address(ascii_hostname.removesuffix(".")))
        except ValueError as error:
            raise InvalidUrlError("Enter a URL with a valid IPv4 address.") from error
    return ascii_hostname


def reject_shortener_url(url, shortener_host):
    """Prevent links that redirect back into this shortener's own routes."""
    try:
        destination_host = urlsplit(url).hostname
        current_host = urlsplit(f"//{shortener_host}").hostname
    except ValueError as error:
        raise InvalidUrlError("Enter a valid http or https URL.") from error
    if (
        destination_host
        and current_host
        and _normalize_hostname(destination_host).rstrip(".")
        == _normalize_hostname(current_host).rstrip(".")
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
    connection = get_db()
    try:
        connection.execute(
            "INSERT INTO urls (short_code, original_url, expires_at) VALUES (%s, %s, %s)",
            (short_code, original_url, expires_at),
        )
        connection.commit()
    except UniqueViolation:
        connection.rollback()
        return False
    return True


def get_destination(short_code):
    row = get_db().execute(
        "SELECT original_url, expires_at FROM urls WHERE short_code = %s", (short_code,)
    ).fetchone()
    if row is None:
        return None
    if row["expires_at"] is not None and time.time() >= row["expires_at"]:
        return "expired"
    return row["original_url"]
