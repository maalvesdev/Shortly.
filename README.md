# Shortly.

A full-stack URL shortener built with Python, Flask, JavaScript, and PostgreSQL. It lets users create shareable short links, choose a custom alias, and optionally set an expiration time.

![URLshort demo](static/demo.gif)

## Why I built it

This project is a practical exercise in the backend and deployment fundamentals behind a small web application: validating untrusted input, persisting data, returning useful HTTP responses, handling conflicts, and testing important behavior.

## Features

- Shortens syntactically valid `http` and `https` URLs, adding HTTPS when the scheme is omitted
- Accepts DNS hostnames, IPv4, bracketed IPv6, and explicit ports; normalizes internationalized hostnames to ASCII using IDNA
- Enforces a 4,096-character limit after normalization and rejects malformed URLs or embedded credentials
- Supports optional custom aliases (3–32 letters, numbers, hyphens, or underscores)
- Offers link expiration: 1 hour, 24 hours, 7 days, or never
- Generates random short codes with Python's `secrets` module
- Handles alias conflicts with a clear `409 Conflict` response
- Prevents accidental redirect chains by rejecting links back to Shortly itself
- Displays dedicated pages for missing (`404`) and expired (`410`) links
- Uses a database-backed rate limit to reduce link-creation spam
- Runs the application and PostgreSQL locally through Docker Compose

TODO:
QR Code generator, link data

## Tech stack

| Area | Technology |
| --- | --- |
| Backend | Python, Flask |
| Database | PostgreSQL (local or hosted) |
| Local environment | Docker Compose (application and database) |
| PostgreSQL driver | psycopg |
| Front end | HTML, CSS, JavaScript |
| Production server | Gunicorn |
| Tests | Python `unittest` |
| Hosting | Optional; previously deployed on Render |

## Project structure

```text
app.py              Flask application factory and HTTP routes
database.py         PostgreSQL connections, schema setup, and parameterized SQL
url_service.py      URL validation, alias validation, persistence, and redirects
rate_limit.py       Database-backed fixed-window rate limiter
templates/          Jinja HTML templates
static/css/         Site styles
static/js/          Browser behavior for form submission and copying links
static/favicon/     Browser and web-app icon assets
tests/              Database-free rule/configuration tests and PostgreSQL API tests
Dockerfile          Python 3.14 application image running Gunicorn as a non-root user
.dockerignore       Files excluded from the application image build
compose.yaml        Local application and PostgreSQL services with health checks
.env.example        Example local configuration (copy to .env)
```

## Run locally

Requirements: Docker Desktop running with Linux containers and PowerShell (commands below are for Windows). Python runs inside the application container, so a separate Python installation is not needed for this workflow.

Run these commands from the project folder. The first command copies `.env.example` only if `.env` does not already exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build --wait
```

The command builds the application image, starts both services in the background, and waits for their health checks. Open `http://127.0.0.1:5000` in a browser. Flask runs behind Gunicorn in the `web` container, and PostgreSQL runs in the `db` container. Their published ports are bound to your computer's loopback interface: `127.0.0.1:5000` for the app and `127.0.0.1:5432` for PostgreSQL. The application creates its tables automatically.

The example credentials are for local development only. If you change `POSTGRES_PASSWORD`, update the password in both `DATABASE_URL` and `TEST_DATABASE_URL`. PostgreSQL applies its initialization credentials only when creating an empty data volume; editing `.env` later does not change an existing database password.

PostgreSQL stores its data in the named Docker volume `shortly_postgres_data`, so stopping or recreating the container preserves your links. The old SQLite `database.db` file is no longer used, and its contents are not imported into PostgreSQL automatically.

To inspect the database in DBeaver, use host `127.0.0.1`, port `5432`, database `shortly`, username `shortly`, and the password from your local `.env` file. SSL is not required for this local connection.

Useful commands:

```powershell
docker compose ps
docker compose logs -f web
docker compose stop
docker compose up --build --wait
```

Use `Ctrl+C` to stop following logs; this does not stop the containers. `docker compose stop` stops both services, and the final command starts them again. Application files are copied into the image, so run `docker compose up --build --wait` after source changes; the container does not reload code automatically.

Avoid `docker compose down -v` unless you intend to permanently delete the local PostgreSQL data volume.

### Optional: run Flask directly with Python

For editing and debugging outside the application container, install Python 3.10+ and use the local URLs from `.env`. Stop the `web` container first because it uses the same port as the Python development server:

```powershell
docker compose stop web
docker compose up -d --wait db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open the same `http://127.0.0.1:5000` address. Stop this development server with `Ctrl+C` before starting the `web` container again.

## Configuration

Docker Compose reads the host's `.env` file and passes the required settings to the containers. The file is excluded from the application image. Inside `web`, Compose sets `DATABASE_URL` to `postgresql://db:5432/shortly` and `TEST_DATABASE_URL` to `postgresql://db:5432/shortly_test`, using the `db` service name on Docker's network. The database client in `web` receives the username through `PGUSER` and the password through `PGPASSWORD`, populated from `POSTGRES_PASSWORD`.

The `127.0.0.1` URLs in `.env` remain available for running Python directly on your computer and for database tools. Normal Python application startup reads `.env` from the project folder; variables already set in your terminal or hosting environment take precedence. `DATABASE_URL` is required and must be a PostgreSQL connection URL (`postgresql://` or `postgres://`).

Tests read `TEST_DATABASE_URL` from the terminal environment first, or from `.env` if it is not set, and pass explicit configuration to the application. Reading the test configuration does not load `.env` values into the process environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | required | PostgreSQL connection string for local development or hosting |
| `TEST_DATABASE_URL` | required for integration tests | Connection string for the separate `shortly_test` PostgreSQL database |
| `POSTGRES_PASSWORD` | required by Compose | Password used when initializing the local PostgreSQL container |
| `RATE_LIMIT_SECRET` | required by Compose; development fallback in Python | Secret used to hash client IP addresses before storing rate-limit keys |
| `RATE_LIMIT_MAX_REQUESTS` | `10` | Maximum validated link-creation requests per IP per time window |
| `RATE_LIMIT_WINDOW_SECONDS` | `3600` | Rate-limit window in seconds; use `300` for five minutes |
| `PROXY_HOPS` | `0` | Number of trusted reverse-proxy hops setting forwarding headers; leave at zero for direct local access |

Both rate-limit settings must be positive integers. `PROXY_HOPS` must be a nonnegative integer. Invalid values stop application startup with an error naming the setting, before connecting to PostgreSQL.

By default, Flask ignores `X-Forwarded-*` headers. For a deployment behind a trusted reverse proxy that sets both `X-Forwarded-For` and `X-Forwarded-Proto`, set `PROXY_HOPS` to the correct number of hops (for example, `1` for one proxy). Enable this only when requests reach the app through that proxy chain and the proxies overwrite or append the appropriate headers. A hop count does not authenticate a proxy. This follows [Werkzeug's forwarding-header guidance](https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/).

Never commit real credentials. `.env` is ignored by Git; `.env.example` contains development-only examples. Use separate secrets in your host's environment-variable settings for any public deployment.

## API

### Create a link

`POST /api/shorten`

```json
{
  "original_url": "https://example.com/a-long-page",
  "custom_url": "example-link",
  "expires_in_hours": "24"
}
```

`custom_url` is optional. Omit `expires_in_hours`, or send `null` or an empty string, for a link that does not expire. Otherwise, send an integer or integer string from `1` to `8760` hours. Booleans, floats (including `1.0`), and other types return a JSON `400` error. Links expire at their stored expiration timestamp and their aliases remain reserved.

`original_url` accepts HTTP or HTTPS URLs and adds `https://` when the scheme is omitted. Validation requires a valid hostname or IP address and a valid port when supplied. The scheme and hostname are normalized, including IDNA conversion of internationalized hostnames to ASCII; the path, query, and fragment are preserved, including correctly percent-encoded data.

The normalized URL must not exceed 4,096 characters, including its scheme and any IDNA hostname expansion. Embedded username/password credentials are not accepted. Malformed hosts, ports, percent escapes, raw control characters, or backslashes return a JSON `400` validation error before a link is stored or rate-limit quota is consumed.

Validation checks URL syntax, not whether the destination exists or is reachable; it does not make DNS or HTTP requests.

A successful request returns `201 Created`:

```json
{
  "short_code": "example-link",
  "short_url": "https://your-domain.example/example-link"
}
```

Validation errors return `400`, an already-used alias returns `409`, and rate-limited requests return `429` with a `Retry-After` header.

## Tests

The suite contains database-free tests for URL/alias validation, expiration calculations, and startup configuration, plus API integration tests using PostgreSQL. Time-sensitive tests use a controlled clock instead of waiting for real time to pass.

To run the full suite, first create the dedicated PostgreSQL test database locally (run `createdb` only once):

```powershell
docker compose up -d --wait db
docker compose exec db createdb -U shortly shortly_test
```

Run the suite in a separate, temporary application container:

```powershell
docker compose run --build --rm web python -m unittest discover -s tests -v
```

This command uses the container's `TEST_DATABASE_URL`, removes the test container when it finishes, and does not publish its web port. The normal application can remain running. Coverage includes malformed JSON and field types, URL length boundaries, internationalized redirects, alias conflicts, random-code collisions, exact expiration boundaries, rate-limit window rollover and client isolation, invalid configuration, and forwarded-header handling. API tests verify validation failures create no records and consume no rate-limit quota; validated attempts that hit an alias conflict do count toward the quota.

Tests verify the connected database is named `shortly_test` before creating tables or clearing data. They clear the `urls` and `rate_limits` tables in that database between tests. Keep it for tests only and run this suite serially, not with parallel test workers. The development database `shortly` is not used by these tests.

If you installed the Python dependencies using the optional workflow above, you can also run the same suite directly on your computer:

```powershell
python -m unittest discover -s tests -v
```

This alternative reads the host's `TEST_DATABASE_URL` from your terminal environment or `.env`, where the example points to `127.0.0.1:5432/shortly_test`.

With the Python dependencies installed, these commands run all database-free tests without PostgreSQL or Docker:

```powershell
python -m unittest discover -s tests -p test_url_validation.py -v
python -m unittest discover -s tests -p test_link_rules.py -v
python -m unittest discover -s tests -p test_configuration.py -v
```

## Deployment notes

Hosting is optional. The local setup does not require Render or any other hosting account. To deploy, configure `DATABASE_URL` for your chosen PostgreSQL service and a separate `RATE_LIMIT_SECRET`, using the provider's required connection and SSL settings. Do not upload your local `.env` file. The schema is created automatically when the application starts.

For a Linux host, use the following production start command:

```text
gunicorn 'app:create_app()'
```

If an existing deployment uses `gunicorn app:app`, update it to the factory command above. Gunicorn is not the development server used on Windows; `python app.py` continues to work locally.

### Container maintenance

The Docker image uses Python 3.14 on Debian Trixie. During the build, it installs the application dependencies and runs `pip check`, then removes `pip` and its optional bootstrap module, `ensurepip`. These installers contain bundled libraries that Shortly does not need at runtime. To add a dependency, edit `requirements.txt` and rebuild the image. The optional Python environment on your computer keeps its own pip installation.

To refresh the base image and dependencies, test the result, restart the local app, and inspect the image with Docker Scout:

```powershell
docker compose build --pull --no-cache web
docker compose run --rm web python -m unittest discover -s tests -v
docker compose up --wait
docker scout cves local://shortly-web:latest --locations
```

Docker Scout requires Docker sign-in. Its report can also be viewed through Docker Desktop's image analysis. Inspect package locations to distinguish application dependencies from installer or operating-system components.

Remaining system-package findings reviewed on October 27, 2026:

- **zlib / CVE-2026-85091:** the installed version is still marked vulnerable by [Debian's security tracker](https://security-tracker.debian.org/tracker/CVE-2026-85091), and the configured stable repositories currently offer no newer package. Keep this finding open and recheck when the base image or stable package is updated. The affected-version range is under discussion; a smaller version number alone does not establish safety.
- **tar / CVE-2025-45582:** [Debian describes this issue as disputed](https://security-tracker.debian.org/tracker/CVE-2025-45582). Shortly does not accept or extract archives, so the described archive-extraction scenario is not exposed by its current application features.

These findings remain visible in the scan. Reassess them if the application gains new features or is publicly deployed; scan results change as advisories and images are updated.

The PostgreSQL image was also checked on October 27, 2026. The local `postgres:18` image was already the current official image, running PostgreSQL 18.6. Its four critical findings all point to Go 1.24.6 in `/usr/local/bin/gosu`, the helper that switches to the database user during startup:

| Finding | Applicability assessment |
| --- | --- |
| [CVE-2025-68121](https://pkg.go.dev/vuln/GO-2026-4337) | Requires Go TLS session resumption; no TLS calls appear in the reviewed gosu startup code. |
| [CVE-2026-56857](https://pkg.go.dev/vuln/GO-2026-6604) | Concerns Windows junction handling; this image runs Linux. |
| [CVE-2026-39821](https://pkg.go.dev/vuln/GO-2026-5026) | Concerns HTTP/IDNA hostname conversion; no corresponding calls appear in the reviewed gosu code. |
| [CVE-2026-78663](https://pkg.go.dev/vuln/GO-2026-6612) | Requires a Go HTTP/2 server; gosu does not run one. |

The follow-up scan reported 33 high findings: 30 in gosu's Go standard library, two in libxml2, and one in zlib. A binary scan of the actual gosu executable using `govulncheck` v1.9.0 found no affected standard-library symbols for those 30 high and four critical advisories; all 34 CVEs were covered by the checker's advisory data. This supports the source review and [gosu's security policy](https://github.com/tianon/gosu/security). Binary symbol analysis has limitations and does not establish that the image has no security issues. Docker Scout's alerts remain visible.

The binary check did identify one separate medium-severity advisory, [CVE-2026-61801](https://github.com/moby/sys/security/advisories/GHSA-mjcv-p78q-w5fw), in gosu's user/group parser. It requires attacker-controlled account files such as `/etc/passwd` or `/etc/group`; Shortly's current inputs and volume mounts do not provide that capability. The dependency is fixed in [gosu 1.20](https://github.com/tianon/gosu/pull/181), so recheck when the official PostgreSQL image adopts it.

The three high-severity Debian findings remain open: [libxml2 CVE-2026-74860](https://security-tracker.debian.org/tracker/CVE-2026-74860), [libxml2 CVE-2026-86140](https://security-tracker.debian.org/tracker/CVE-2026-86140), and zlib CVE-2026-85091. The configured stable repositories currently offer no newer versions of those packages. Comparing the official `postgres:18-alpine` image did not offer a clear improvement: it retained the same Go findings and had additional findings, so the database image was not changed.

To check for PostgreSQL 18 image updates and scan the downloaded image:

```powershell
docker compose pull db
docker scout cves local://postgres:18 --locations
```

Pulling an image does not replace the running database container. Before applying a future update, save a database backup outside the container and keep the existing named volume. Stay within PostgreSQL 18 for routine updates; a major-version change needs a separate migration procedure.

## Scope and future improvements

Shortly is a portfolio/demo project, not a production-grade public shortener. A production version would add authentication, link management, abuse reporting, observability, database migrations, stronger rate-limiting controls, and a dedicated cleanup strategy for expired links.
