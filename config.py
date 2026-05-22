import os
from pathlib import Path


# Base directory of the project.
BASE_DIR = Path(__file__).resolve().parent

# Path to SQLite database file. Can be overridden for tests or deployments.
DB_PATH = os.getenv(
    "FILE_ACCESS_LOGGER_DB",
    str(BASE_DIR / "data" / "file_events.db")
)

# Flask server settings.
HOST = os.getenv("FILE_ACCESS_LOGGER_HOST", "0.0.0.0")
SOCKETIO_ASYNC_MODE = os.getenv("FILE_ACCESS_LOGGER_ASYNC_MODE", "threading")


def _get_port():
    try:
        return int(os.getenv("FILE_ACCESS_LOGGER_PORT", "5000"))
    except ValueError:
        return 5000


def _configured_monitor_dirs():
    raw_dirs = os.getenv("FILE_ACCESS_LOGGER_DIRS", "")
    if not raw_dirs:
        return []

    return [path.strip() for path in raw_dirs.split(os.pathsep) if path.strip()]


def _default_monitor_dirs():
    home = Path.home()
    candidates = [home / "Documents", home / "Downloads", home / "Desktop"]
    existing_dirs = [str(path) for path in candidates if path.is_dir()]
    return existing_dirs or [str(home)]


PORT = _get_port()

# Directories to monitor for file events. Use FILE_ACCESS_LOGGER_DIRS to provide
# multiple paths separated by the OS path separator (";" on Windows, ":" on Unix).
MONITOR_DIRS = _configured_monitor_dirs() or _default_monitor_dirs()
