"""Expose the Flask application for Vercel's Python framework detection."""

from app import create_app

app = create_app()
