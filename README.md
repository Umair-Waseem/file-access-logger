# File Access Logger

File Access Logger is a lightweight Flask dashboard for monitoring file activity in local directories. It detects file creation, modification, and deletion events, stores them in a SQLite database, and displays recent activity in a real-time web dashboard using Flask-SocketIO.

## Features

- Real-time browser dashboard for file activity
- SQLite event storage with SQLAlchemy
- Configurable monitored directories
- Event counts for created, modified, and deleted files
- Recent activity table with file, directory, process, PID, user, and timestamp details
- Safe exclusion of the app's own SQLite database files from monitoring

## Project Structure

```text
.
├── app.py              # Flask application entry point
├── config.py           # Runtime configuration and monitored directory defaults
├── models.py           # SQLAlchemy database model and setup
├── monitor.py          # File scanning, event detection, and logging
├── routes.py           # Dashboard and API routes
└── requirements.txt    # Python dependencies
```

## Requirements

- Python 3.10 or newer
- Windows, macOS, or Linux

## Installation

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

Open the dashboard:

```text
http://127.0.0.1:5000
```

## Configuration

By default, the app monitors the current user's `Documents`, `Downloads`, and `Desktop` directories when they exist.

To monitor custom directories, set `FILE_ACCESS_LOGGER_DIRS` before starting the app. On Windows, separate multiple paths with semicolons:

```powershell
$env:FILE_ACCESS_LOGGER_DIRS="C:\Path\One;C:\Path\Two"
python app.py
```

Optional environment variables:

```text
FILE_ACCESS_LOGGER_DB          SQLite database path
FILE_ACCESS_LOGGER_HOST        Flask host, default 0.0.0.0
FILE_ACCESS_LOGGER_PORT        Flask port, default 5000
FILE_ACCESS_LOGGER_ASYNC_MODE  Socket.IO async mode, default threading
```

## API Endpoints

```text
GET  /api/stats           Event totals and counts by type
GET  /api/initial_events  Most recent file events
POST /api/clear           Clear all logged events, JSON request required
```

## Notes

This project uses polling to detect file changes. Very fast create/delete operations between scan intervals may be missed, and process attribution is best-effort.
