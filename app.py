"""Application entry point for the URL shortener."""

from pathlib import Path
import os
import hashlib

from flask import Flask, jsonify, make_response, redirect, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from database import close_db, init_db
from rate_limit import consume_rate_limit
from url_service import (
    AliasTakenError,
    InvalidAliasError,
    InvalidUrlError,
    create_short_url,
    get_destination,
    validate_short_url,
)


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_mapping(
        # Render supplies DATABASE_URL in production. SQLite keeps local setup simple.
        DATABASE=os.environ.get("DATABASE_URL") or Path(__file__).with_name("database.db"),
        MAX_EXPIRY_HOURS=8_760,
        RATE_LIMIT_MAX_REQUESTS=int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "10")),
        RATE_LIMIT_WINDOW_SECONDS=int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "3600")),
        RATE_LIMIT_SECRET=os.environ.get("RATE_LIMIT_SECRET", "development-only-change-me"),
    )
    if test_config:
        app.config.update(test_config)

    # Render forwards the original client address and HTTPS scheme in these headers.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.post("/api/shorten")
    def shorten_url():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_error("Send a JSON object in the request body.")
        try:
            normalized_url, alias, expires_at = validate_short_url(
                data.get("original_url"),
                data.get("custom_url"),
                data.get("expires_in_hours"),
                app.config["MAX_EXPIRY_HOURS"],
                request.host,
            )
        except (InvalidUrlError, InvalidAliasError) as error:
            return api_error(str(error))

        client_key = get_client_key(app.config["RATE_LIMIT_SECRET"])
        if not consume_rate_limit(
            client_key,
            app.config["RATE_LIMIT_MAX_REQUESTS"],
            app.config["RATE_LIMIT_WINDOW_SECONDS"],
        ):
            response, status = api_error(
                "Too many links created from this address. Please try again later.",
                429,
            )
            response.headers["Retry-After"] = str(app.config["RATE_LIMIT_WINDOW_SECONDS"])
            return response, status

        try:
            short_code = create_short_url(normalized_url, alias, expires_at)
        except AliasTakenError:
            return api_error("This custom alias is already taken.", 409)
        return jsonify(short_code=short_code, short_url=f"{request.url_root}{short_code}"), 201

    @app.get("/<short_code>")
    def redirect_to_url(short_code):
        destination = get_destination(short_code)
        if destination is None:
            return dynamic_link_response(render_template("not_found.html"), 404)
        if destination == "expired":
            return dynamic_link_response(render_template("expired.html"), 410)
        return dynamic_link_response(redirect(destination))

    return app


def api_error(message, status=400):
    return jsonify(error=message), status


def dynamic_link_response(body, status=None):
    """Prevent browsers from caching redirects or status pages for reused aliases."""
    response = make_response(body, status) if status is not None else make_response(body)
    response.headers["Cache-Control"] = "no-store"
    return response


def get_client_key(secret):
    """Hash the client IP so the rate-limit table does not store it directly."""
    client_ip = request.remote_addr or "unknown"
    return hashlib.sha256(f"{secret}:{client_ip}".encode()).hexdigest()


app = create_app()


if __name__ == "__main__":
    app.run()
