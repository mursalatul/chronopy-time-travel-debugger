"""Server package — FastAPI backend serving the web UI and replay API."""
from .app import create_app

__all__ = ["create_app"]
