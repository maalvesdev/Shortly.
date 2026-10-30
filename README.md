# Shortly.

Turn a long URL into a link that's easier to share. Choose a memorable alias, set an expiration time for a temporary link, or let Shortly generate a short code for you.

**[Try it yourself](https://shortly-go.vercel.app/)**

![URLshort demo](static/demo.gif)

## What you can do

- **Shorten and share:** create a short link that automatically redirects visitors to its destination.
- **Make it recognizable:** use a custom alias such as `reading-list`, or leave it blank for a generated code.
- **Choose when it expires:** select 1 hour, 24 hours, 7 days, 30 days, or never. The form starts with 1 hour selected.
- **Copy in one click:** copy the result from the page and share it.
- **Get useful feedback:** see a message when a URL is invalid or an alias is taken; visitors get dedicated pages for missing and expired links.
- **Limit excessive creation:** requests to create links are limited per IP address, with a message when the quota is reached.

## How it works

1. Paste the destination URL.
2. Optionally choose an alias and change the expiration time.
3. Click **Shorten URL**, then **Copy**. Opening the short link redirects to the destination while the link is active.

For example, with Shortly running locally:

```text
Destination: https://example.com/articles/url-shortening?ref=reading-list
Alias:       reading-list
Expires:     In 24 hours

Short link:  http://127.0.0.1:5000/reading-list
```

## Built with

| Area | Technologies |
| --- | --- |
| Application | Python, Flask |
| Interface | HTML, CSS, JavaScript, Jinja templates |
| Database | PostgreSQL, psycopg |
| Hosting | Vercel, Neon |
| Local environment | Docker, Docker Compose, Gunicorn |
| Tests | Python `unittest` |

## Hosting

The live demo runs on **Vercel**, which serves the Flask pages, API, and redirects. **Neon** provides the hosted PostgreSQL database. Flask uses the same `psycopg` driver for hosted and local database connections.

You can also run the app and database entirely on your computer with Docker Compose. See the [hosting notes](docs/development.md#deployment-notes) for a brief explanation of the deployment files and environment configuration.

## Try it locally

You'll need Docker Desktop running with Linux containers. Clone or download the repository, then run these **PowerShell** commands from the project folder:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build --wait
```

The command starts the app and PostgreSQL together, waits for their health checks, and creates the database tables. Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)**. A separate Python installation isn't needed for this workflow.

Stop the services with `docker compose stop`. Your links stay in the database's named volume. After changing application code or dependencies, rebuild with `docker compose up --build --wait`.

The example credentials are for local development. See the [development guide](docs/development.md) for configuration, DBeaver access, troubleshooting, and running Flask directly with Python.

## A look at the implementation

I built Shortly to practice taking a small web application from form input to database storage and redirects, with tests around the cases that can go wrong.

- **Separate responsibilities:** [Flask routes](app.py), [link rules](url_service.py), [database access](database.py), and [rate limiting](rate_limit.py) live in separate modules.
- **Input handling:** URL, alias, and expiration validation happen before a request consumes creation quota. The API returns JSON errors the interface can display.
- **Data integrity:** parameterized SQL stores links in PostgreSQL; unique aliases and collision retries prevent an existing destination from being overwritten.
- **Predictable link lifetimes:** expired links stop redirecting and keep their aliases reserved. Dynamic redirects and missing/expired pages use `Cache-Control: no-store`.
- **Repeatable local setup:** Docker Compose starts both services with health checks and persistent database storage.

The [API reference](docs/api.md) covers request formats, validation rules, rate-limit behavior, and HTTP responses.

## Testing

The suite combines database-free unit tests with PostgreSQL integration tests. It checks creation and redirects, malformed inputs, alias conflicts, expiration boundaries, rate-limit resets, and forwarded-header behavior. Time-sensitive tests use a controlled clock.

Create the separate test database once, then run the suite:

```powershell
docker compose up -d --wait db
docker compose exec db createdb -U shortly shortly_test
docker compose run --build --rm web python -m unittest discover -s tests -v
```

Skip `createdb` if `shortly_test` already exists. Integration tests clear that database's test tables, so keep it for tests only and run the suite serially.

For tests that run without PostgreSQL, see [testing options](docs/development.md#tests-without-postgresql). Browse the cases in [tests/](tests/).

## Explore further

- [Development guide](docs/development.md): project structure, configuration, database tools, testing, and deployment notes.
- [API reference](docs/api.md): examples, input rules, and response behavior.
- [Container maintenance and security review](docs/security.md): image updates, scanning, and the dated vulnerability assessment.

Shortly is a personal portfolio project. Future ideas include QR codes and link information; the [scope and future improvements](docs/development.md#scope-and-future-improvements) section outlines what a public production service would need.
