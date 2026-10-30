"""Publish Flask's existing static paths through Vercel's public directory."""

from pathlib import Path
from shutil import copytree


def prepare_static_files():
    project_root = Path(__file__).resolve().parents[1]
    source = project_root / "static"
    destination = project_root / "public" / "static"
    copytree(source, destination, dirs_exist_ok=True)
    print("Static assets are ready in public/static.")


if __name__ == "__main__":
    prepare_static_files()
