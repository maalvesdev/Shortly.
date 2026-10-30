# Development guide

[Back to Shortly](../README.md) · [API reference](api.md) · [Container maintenance and security review](security.md)

This guide contains the setup and configuration details behind the README's quick start. The [live demo](https://shortly-go.vercel.app/) runs on Vercel with PostgreSQL hosted on Neon. The app and database can also run locally without a hosting account.

## Project structure

```text
app.py              Flask application factory and HTTP routes
wsgi.py             Vercel entry point exporting the Flask application
url_service.py      URL and alias validation, expiration, persistence, and redirects
database.py         PostgreSQL connections, schema setup, and parameterized SQL
rate_limit.py       Database-backed fixed-window rate limiter
init_db.py          Schema initialization entry point, also used during deployment builds
templates/          Shared Jinja layout, form, and missing/expired pages
static/css/         Site styles
static/js/          Form submission and copying links
static/favicon/     Browser and web-app icon assets
static/demo.gif     Demonstration shown in the README
tests/              Database-free tests and PostgreSQL API integration tests
Dockerfile          Python 3.14 image running Gunicorn as a non-root user
.dockerignore       Files excluded from the image build
compose.yaml        Local application and PostgreSQL services
.env.example        Example local configuration
vercel.json         Flask deployment and build configuration
.python-version     Python version selected for Vercel
scripts/            Static asset preparation for Vercel
neon.ts             Neon service and branch configuration
package.json        Neon configuration dependencies and a Python build wrapper
package-lock.json   Locked Node tooling dependencies

docs/               Development, API, and security reference material
```

The application factory registers routes and initializes the schema. Link validation and creation rules live in `url_service.py`; database connections are opened as needed and closed when the application context ends.

## Run with Docker Compose

Requirements: Docker Desktop running with Linux containers. Commands in this guide use PowerShell and run from the project folder.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build --wait
```

The copy command preserves an existing `.env` file. Compose builds the application image, starts both services in the background, and waits for their health checks. Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

Flask runs behind Gunicorn in `web`, and PostgreSQL runs in `db`. Published ports are bound to your computer's loopback interface:

| Service | Local address |
| --- | --- |
| Web application | `127.0.0.1:5000` |
| PostgreSQL | `127.0.0.1:5432` |

The app creates missing tables and indexes on startup. It does not use a database-migration framework.

Useful commands:

```powershell
docker compose ps
docker compose logs -f web
docker compose stop
docker compose up --build --wait
```

Use `Ctrl+C` to stop following logs; this does not stop the containers. `docker compose stop` stops both services. Application files are copied into the image, so rebuild after source or dependency changes; the container does not reload code automatically.

### Persistent data and credentials

PostgreSQL stores data in the named volume `shortly_postgres_data`. Stopping or recreating the container preserves your links. Avoid `docker compose down -v` unless you intend to permanently delete that data volume.

The example credentials are for local development. If you change `POSTGRES_PASSWORD`, update the passwords in both host connection strings, `DATABASE_URL` and `TEST_DATABASE_URL`, too. PostgreSQL applies initialization credentials only when creating an empty data volume: editing `.env` later does not change an existing database password.

The old SQLite `database.db` file is no longer used. Its contents are not imported into PostgreSQL automatically.

### Inspect the database with DBeaver

Create a PostgreSQL connection with these local settings:

| Setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `shortly` |
| Username | `shortly` |
| Password | Your local `POSTGRES_PASSWORD` value |
| SSL | Not required for this local connection |

Link destinations, aliases, and expiration timestamps are stored in `urls`. Fixed-window request counts are stored in `rate_limits`. During validated creation attempts, the limiter removes old request-count buckets. Expired URL rows remain, and their aliases stay reserved.

## Run Flask directly with Python

For editing and debugging outside the application container, install Python 3.10+. The commands below assume `.env` contains the local connection URLs from `.env.example`. Python uses whichever database `DATABASE_URL` points to, so a Neon URL connects to the hosted database instead. Stop `web` first because it uses the same port as the Python development server:

```powershell
docker compose stop web
docker compose up -d --wait db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open the same [http://127.0.0.1:5000](http://127.0.0.1:5000) address. Stop this development server with `Ctrl+C` before starting `web` again.

## Configuration

Docker Compose reads the host `.env` file and passes the configured settings to the containers. The file is excluded from the application image.

Inside `web`, Compose supplies `DATABASE_URL=postgresql://db:5432/shortly` and `TEST_DATABASE_URL=postgresql://db:5432/shortly_test`. The hostname `db` refers to the database service on Docker's network. The client receives its username through `PGUSER` and its password through `PGPASSWORD`, populated from `POSTGRES_PASSWORD`.

The `127.0.0.1` URLs in `.env.example` are for running Python directly on your computer or connecting database tools to local PostgreSQL. A host `.env` can instead contain a hosted connection URL; Compose still supplies its own internal database URLs to the containers. Normal Python startup reads `.env` from the project folder; variables already set in the terminal or hosting environment take precedence.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Required | PostgreSQL URL beginning with `postgresql://` or `postgres://` |
| `TEST_DATABASE_URL` | Required for integration tests | URL for the separate `shortly_test` PostgreSQL database |
| `POSTGRES_PASSWORD` | Required by Compose | Password used when initializing the local database |
| `RATE_LIMIT_SECRET` | Required by Compose; development fallback in Python | Secret used to hash IP addresses before storing rate-limit keys |
| `RATE_LIMIT_MAX_REQUESTS` | `10` | Maximum validated creation attempts per IP per fixed time window |
| `RATE_LIMIT_WINDOW_SECONDS` | `3600` | Window duration; use `300` for five minutes |
| `PROXY_HOPS` | `0` | Number of trusted proxy hops setting forwarding headers |

Rate-limit settings must be positive integers. `PROXY_HOPS` must be a nonnegative integer. Invalid values stop startup with an error naming the setting, before connecting to PostgreSQL.

Never commit real credentials. `.env` is ignored by Git; `.env.example` contains development-only examples. Use separate secrets for a public deployment.

### Forwarded headers

By default, Flask ignores `X-Forwarded-*` headers. For a deployment behind a trusted reverse proxy that sets both `X-Forwarded-For` and `X-Forwarded-Proto`, set `PROXY_HOPS` to the correct count, such as `1` for one proxy.

Enable this only when requests reach the app through that proxy chain and the proxies overwrite or append the appropriate headers. A hop count does not authenticate a proxy. See [Werkzeug's forwarding-header guidance](https://werkzeug.palletsprojects.com/en/stable/middleware/proxy_fix/).

## Testing

The suite uses Python `unittest`. URL, alias, expiration, and configuration checks can run without a database. API integration tests exercise PostgreSQL using a separate database. Time-sensitive cases use a controlled clock.

Coverage includes:

- Creation and redirects, including internationalized and percent-encoded destinations.
- Malformed JSON, incorrect field types, hosts, ports, and URL length boundaries.
- Alias conflicts and generated-code collisions without overwriting existing links.
- Exact expiration boundaries, missing/expired pages, and cache headers.
- Rate-limit rollover, client isolation, and validation failures that consume no quota.
- Invalid configuration and forwarded-header handling.

### Full suite with PostgreSQL

Create the test database once:

```powershell
docker compose up -d --wait db
docker compose exec db createdb -U shortly shortly_test
```

Skip `createdb` if the database already exists. Then run the suite in a temporary application container:

```powershell
docker compose run --build --rm web python -m unittest discover -s tests -v
```

The command uses the container's `TEST_DATABASE_URL`, removes the test container when it finishes, and does not publish its web port. The normal app can remain running.

Tests check that the connected database is named `shortly_test` before creating schema or clearing tables. They clear `urls` and `rate_limits` between tests, so use that database only for tests and run the suite serially. The development database `shortly` is not used by these tests.

With the host Python environment and dependencies installed, the same suite can also run directly:

```powershell
python -m unittest discover -s tests -v
```

Tests read `TEST_DATABASE_URL` from the terminal first, or from `.env` if it is not set. The example host URL points to `127.0.0.1:5432/shortly_test`. Reading test configuration does not load `.env` values into the process environment.

### Tests without PostgreSQL

With Python and the project dependencies installed, these commands run the database-free checks without PostgreSQL or Docker:

```powershell
python -m unittest discover -s tests -p test_url_validation.py -v
python -m unittest discover -s tests -p test_link_rules.py -v
python -m unittest discover -s tests -p test_configuration.py -v
```

## Deployment notes

### Current hosting

The public demo uses Vercel for the Flask application and Neon for PostgreSQL:

- [wsgi.py](../wsgi.py) exports the application created by `create_app()` for Vercel's Python runtime.
- [vercel.json](../vercel.json) selects Flask and defines the build. It initializes the database schema, then [prepares static assets](../scripts/prepare_vercel.py) in `public/static` so existing CSS, JavaScript, and favicon paths work through Vercel.
- Flask connects to Neon through the pooled `DATABASE_URL` with TLS using the existing `psycopg` driver. Database connections remain scoped to the application context.
- Database credentials, the rate-limit secret, and proxy settings are read from environment variables in Vercel. Local `.env` files are excluded from deployment and Git.

[neon.ts](../neon.ts) declares the Neon service and branch policy. The Node packages in [package.json](../package.json) support this configuration tooling; `npm run build` wraps the existing Python build commands. Node tooling is optional for the Docker quick start and is not part of Flask's request handling.

The local Docker database and hosted Neon database have separate data. Running the app locally with Compose does not copy links to or from the live demo. PostgreSQL integration tests use the separate `shortly_test` database described above.

### Other Python hosts

Hosting is optional. For another host, configure `DATABASE_URL` and a separate `RATE_LIMIT_SECRET`, following the provider's connection and SSL requirements. Schema creation happens automatically on startup.

For a Linux host, use:

```text
gunicorn 'app:create_app()'
```

Update any older `gunicorn app:app` start command to this factory form. Gunicorn is not the Windows development server; `python app.py` remains the local Python entry point.

See [container maintenance and the security review](security.md) for image refreshes and scans.

## Troubleshooting

- **Compose cannot start:** check that Docker Desktop is running with Linux containers. Use `docker compose ps` and `docker compose logs -f web` to inspect service state and application logs.
- **Port 5000 is already in use:** run either the `web` container or the host Python server on that port. Stop the other one before starting your chosen workflow.
- **A password change has no effect:** changing `.env` does not reset an existing PostgreSQL user's password. See [persistent data and credentials](#persistent-data-and-credentials).
- **The test database already exists:** skip the `createdb` command and run the tests against the existing `shortly_test` database.

## Scope and future improvements

Shortly is a personal portfolio/demo project. QR-code generation and link information are ideas for future iterations.

A public production service would also need authentication, link management, abuse reporting, observability, database migrations, stronger rate-limiting controls, and a cleanup strategy for expired links. The current app retains expired records and reserves their aliases.
