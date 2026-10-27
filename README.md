# Shortly.

A full-stack URL shortener built with Python, Flask, JavaScript, and PostgreSQL. It lets users create shareable short links, choose a custom alias, and optionally set an expiration time.

![URLshort demo](static/demo.gif)

## Why I built it

This project is a practical exercise in the backend and deployment fundamentals behind a small web application: validating untrusted input, persisting data, returning useful HTTP responses, handling conflicts, and testing important behavior.

## Features

- Shortens valid `http` and `https` URLs
- Supports optional custom aliases (3–32 letters, numbers, hyphens, or underscores)
- Offers link expiration: 1 hour, 24 hours, 7 days, or never
- Generates random short codes with Python's `secrets` module
- Handles alias conflicts with a clear `409 Conflict` response
- Prevents accidental redirect chains by rejecting links back to Shortly itself
- Displays dedicated pages for missing (`404`) and expired (`410`) links
- Uses a database-backed rate limit to reduce link-creation spam
- Runs PostgreSQL locally through Docker Compose

TODO:
QR Code generator, link data

## Tech stack

| Area | Technology |
| --- | --- |
| Backend | Python, Flask |
| Database | PostgreSQL (local or hosted) |
| Local database environment | Docker Compose |
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
tests/              Automated application tests
compose.yaml        Local PostgreSQL service, persistent storage, and health check
.env.example        Example local configuration (copy to .env)
```

## Run locally

Requirements: Python 3.10+, Docker Desktop running with Linux containers, and PowerShell (commands below are for Windows).

Run these commands from the project folder. Copy `.env.example` only when you do not already have a `.env` file:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d --wait db
python app.py
```

Open `http://127.0.0.1:5000` in a browser. Flask runs on your computer; PostgreSQL runs in Docker and is reachable only through `127.0.0.1:5432`. The application creates its tables automatically.

The example credentials are for local development only. If you change `POSTGRES_PASSWORD`, update the password in both `DATABASE_URL` and `TEST_DATABASE_URL`. PostgreSQL applies its initialization credentials only when creating an empty data volume; editing `.env` later does not change an existing database password.

PostgreSQL stores its data in the named Docker volume `shortly_postgres_data`, so stopping or recreating the container preserves your links. The old SQLite `database.db` file is no longer used, and its contents are not imported into PostgreSQL automatically.

To inspect the database in DBeaver, use host `127.0.0.1`, port `5432`, database `shortly`, username `shortly`, and the password from your local `.env` file. SSL is not required for this local connection.

Useful database commands:

```powershell
docker compose ps
docker compose logs db
docker compose stop db
docker compose up -d --wait db
```

Stop Flask with `Ctrl+C`. Avoid `docker compose down -v` unless you intend to permanently delete the local PostgreSQL data volume.

## Configuration

Normal application startup reads `.env` from the project folder. Variables already set in your terminal or hosting environment take precedence. `DATABASE_URL` is required and must be a PostgreSQL connection URL (`postgresql://` or `postgres://`).

Tests read `TEST_DATABASE_URL` from the terminal environment first, or from `.env` if it is not set, and pass explicit configuration to the application. Reading the test configuration does not load `.env` values into the process environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | required | PostgreSQL connection string for local development or hosting |
| `TEST_DATABASE_URL` | required for tests | Connection string for the separate `shortly_test` PostgreSQL database |
| `POSTGRES_PASSWORD` | required by Compose | Password used when initializing the local PostgreSQL container |
| `RATE_LIMIT_SECRET` | development-only value | Secret used to hash client IP addresses before storing rate-limit keys |
| `RATE_LIMIT_MAX_REQUESTS` | `10` | Number of links an IP address may create per time window |
| `RATE_LIMIT_WINDOW_SECONDS` | `3600` | Rate-limit window in seconds; use `300` for five minutes |

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

`custom_url` is optional. Send an empty `expires_in_hours` value for a link that does not expire.

A successful request returns `201 Created`:

```json
{
  "short_code": "example-link",
  "short_url": "https://your-domain.example/example-link"
}
```

Validation errors return `400`, an already-used alias returns `409`, and rate-limited requests return `429` with a `Retry-After` header.

## Tests

The automated tests run against a dedicated PostgreSQL database. First, create it locally (run `createdb` only once):

```powershell
docker compose up -d --wait db
docker compose exec db createdb -U shortly shortly_test
```

The example `.env` configuration sets `TEST_DATABASE_URL` to this separate `shortly_test` database. Run the suite with:

```powershell
python -m unittest discover -s tests -v
```

You can override `TEST_DATABASE_URL` in your terminal environment when needed. The suite covers custom-link creation and redirects, invalid input, duplicate aliases, expired links, and rate limiting.

Tests verify the connected database is named `shortly_test` before creating tables or clearing data. They clear the `urls` and `rate_limits` tables in that database between tests. Keep it for tests only and run this suite serially, not with parallel test workers. The development database `shortly` is not used by these tests.

## Deployment notes

Hosting is optional. The local setup does not require Render or any other hosting account. To deploy, configure `DATABASE_URL` for your chosen PostgreSQL service and a separate `RATE_LIMIT_SECRET`, using the provider's required connection and SSL settings. Do not upload your local `.env` file. The schema is created automatically when the application starts.

For a Linux host, use the following production start command:

```text
gunicorn 'app:create_app()'
```

If an existing deployment uses `gunicorn app:app`, update it to the factory command above. Gunicorn is not the development server used on Windows; `python app.py` continues to work locally.

## Scope and future improvements

Shortly is a portfolio/demo project, not a production-grade public shortener. A production version would add authentication, link management, abuse reporting, observability, database migrations, stronger rate-limiting controls, and a dedicated cleanup strategy for expired links.
