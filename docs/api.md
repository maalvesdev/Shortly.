# API reference

[Back to Shortly](../README.md) · [Development guide](development.md)

The interface creates links through `POST /api/shorten`. Visitors follow them through `GET /<short_code>`.

## Create a link

Send a JSON object with a destination URL and optional alias and expiration:

```http
POST /api/shorten
Content-Type: application/json
```

```json
{
  "original_url": "https://example.com/articles/url-shortening?ref=reading-list",
  "custom_url": "reading-list",
  "expires_in_hours": "24"
}
```

A successful request returns `201 Created`. When running locally at `127.0.0.1:5000`, the example response is:

```json
{
  "short_code": "reading-list",
  "short_url": "http://127.0.0.1:5000/reading-list"
}
```

The short URL uses the request's host and scheme. Trusted reverse-proxy settings can affect that scheme; see [forwarded headers](development.md#forwarded-headers).

## Input rules

### Destination URL

`original_url` must be text containing a syntactically valid HTTP or HTTPS URL. When the scheme is omitted, Shortly adds `https://`.

- Hostnames, IPv4, bracketed IPv6, and explicit valid ports are supported.
- Internationalized hostnames are normalized to ASCII using IDNA.
- The scheme and hostname are normalized; the path, query, fragment, and valid percent-encoding are preserved.
- The normalized URL can contain at most 4,096 characters, including an added scheme and IDNA hostname expansion.
- Embedded usernames/passwords, malformed hosts or ports, invalid percent escapes, raw control characters, and backslashes are rejected.
- Destinations pointing back to the shortener's own hostname are rejected to prevent redirect chains through Shortly.

Validation checks syntax rather than reachability. Shortly does not make DNS or HTTP requests to check a destination, so a valid shortened link can still point to an unavailable website.

### Custom alias

`custom_url` is optional. Omit it, send `null`, or use an empty string to generate a seven-character code using Python's `secrets` module.

A supplied alias must contain 3–32 ASCII letters, numbers, hyphens, or underscores. Surrounding spaces are trimmed; aliases are case-sensitive. Used aliases return `409 Conflict`, including aliases belonging to expired links. This keeps an old link from being reassigned to a different destination.

### Expiration

For direct API requests, omit `expires_in_hours`, send `null`, or use an empty string for no expiration. Otherwise, send an integer or integer string from `1` to `8760` hours. Booleans, floats (including `1.0`), and other types return `400`.

The browser form selects **1 hour by default** and also offers 24 hours, 7 days, 30 days, and never. A link stops redirecting at its stored expiration timestamp; the record and alias remain reserved.

## Rate limiting

By default, the app permits **10 validated creation attempts per IP per fixed one-hour window**. These values are configurable through [environment variables](development.md#configuration).

URL, alias-format, and expiration validation happens first, so those validation failures do not consume quota. An attempt that passes validation but encounters an already-used alias does consume quota. Requests beyond the limit return `429` and a `Retry-After` header containing the configured window duration in seconds.

The limiter stores hashed client keys and request counts in PostgreSQL. It limits link creation, not visits to existing short links.

## Responses

Creation errors use JSON, for example:

```json
{
  "error": "This custom alias is already taken."
}
```

| Request | Status | Behavior |
| --- | --- | --- |
| `POST /api/shorten` | `201 Created` | Returns `short_code` and `short_url` as JSON |
| `POST /api/shorten` | `400 Bad Request` | Returns a JSON error for invalid JSON or field values |
| `POST /api/shorten` | `409 Conflict` | Returns a JSON error when the alias is already taken |
| `POST /api/shorten` | `429 Too Many Requests` | Returns a JSON error and `Retry-After` header |
| `GET /<short_code>` | `302 Found` | Redirects to the stored destination while the link is active |
| `GET /<short_code>` | `404 Not Found` | Displays the missing-link page |
| `GET /<short_code>` | `410 Gone` | Displays the expired-link page |

Redirects and missing/expired link pages include `Cache-Control: no-store`. The numerical paths `/404`, `/409`, and `/410` are ordinary alias lookups, not error-page preview routes.
