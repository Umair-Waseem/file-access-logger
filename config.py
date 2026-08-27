import os
from pathlib import Path


# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Path to the SQLite database file; override for tests or deployments
DB_PATH = os.getenv(
    "FILE_ACCESS_LOGGER_DB",
    str(BASE_DIR / "data" / "file_events.db")
)

# Flask server settings; bind to localhost by default, override to expose the dashboard
HOST = os.getenv("FILE_ACCESS_LOGGER_HOST", "127.0.0.1")
SOCKETIO_ASYNC_MODE = os.getenv("FILE_ACCESS_LOGGER_ASYNC_MODE", "threading")


# Read the server port, falling back to 5000 when unset or invalid
def _get_port():
    try:
        return int(os.getenv("FILE_ACCESS_LOGGER_PORT", "5000"))
    except ValueError:
        return 5000


# Make paths absolute and drop duplicates, keeping the order they were given in
def _unique_dirs(paths):
    seen = set()
    unique = []
    for path in paths:
        directory = os.path.abspath(os.path.expanduser(path))
        key = os.path.normcase(directory)
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique


# Directories requested through the environment variable
def _configured_monitor_dirs():
    raw_dirs = os.getenv("FILE_ACCESS_LOGGER_DIRS", "")
    if not raw_dirs:
        return []

    return [path.strip() for path in raw_dirs.split(os.pathsep) if path.strip()]


# Default directories to monitor when none are configured
def _default_monitor_dirs():
    home = Path.home()
    candidates = [home / "Documents", home / "Downloads", home / "Desktop"]
    existing_dirs = [str(path) for path in candidates if path.is_dir()]
    return existing_dirs or [str(home)]


PORT = _get_port()

# Directories to monitor; set FILE_ACCESS_LOGGER_DIRS to override, separated by os.pathsep
MONITOR_DIRS = _unique_dirs(_configured_monitor_dirs() or _default_monitor_dirs())
