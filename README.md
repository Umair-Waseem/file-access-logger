# File Access Logger

File Access Logger is a local web application that monitors selected directories for file activity and presents it on a live dashboard. It detects when files are created, modified, or deleted, attributes each event to the process responsible where possible, records the event in a SQLite database, and streams new events to the browser in real time.

## Features

- Live dashboard that updates automatically as events occur, without reloading the page.
- Detection of file creation, modification, and deletion across one or more directories.
- Best-effort attribution of each event to a process, including its name, process identifier, and user.
- Persistent storage of every event in a SQLite database through SQLAlchemy.
- Running totals for created, modified, and deleted files, alongside a table of recent activity.
- Automatic exclusion of the application's own database files from monitoring.

## How It Works

The application scans each monitored directory every two seconds and compares the result against the previously recorded state to identify new, changed, and removed files. When an event is detected, the application attempts to identify the responsible process with psutil, in order of decreasing confidence: it reuses a recent attribution for the same file, then looks for a process that currently holds the file open, and finally considers a process whose command line names the file. On Unix-like systems, it falls back to `lsof` when that tool is available. Each event is written to the database and broadcast to connected browsers in real time using Flask-SocketIO.

## Project Structure

```text
.
├── app.py                 # Application entry point; starts the server and monitor
├── config.py              # Configuration and default monitored directories
├── models.py              # SQLAlchemy model, engine, and database setup
├── monitor.py             # Directory scanning, event detection, and process attribution
├── routes.py              # Dashboard page and JSON API (Flask blueprint)
├── templates/
│   └── index.html         # Dashboard page
├── static/
│   ├── dashboard.css      # Dashboard styles
│   └── dashboard.js       # Dashboard client-side logic
├── tests/
│   ├── test_app.py        # Tests for the routes, model, and helper functions
│   └── test_dashboard.js  # Tests for the dashboard script
├── requirements.txt       # Python dependencies
├── LICENSE
└── README.md
```

## Requirements

- Python 3.9 or later.
- Windows, macOS, or Linux.

## Installation

Install the dependencies into your environment:

```bash
python -m pip install -r requirements.txt
```

## Running the Application

Start the application from the project directory:

```bash
python app.py
```

Then open the dashboard in a browser:

```text
http://127.0.0.1:5000
```

## Configuration

By default, the application monitors the current user's Documents, Downloads, and Desktop directories when they exist, and the home directory otherwise. All settings are read from environment variables once at startup.

To monitor specific directories, set `FILE_ACCESS_LOGGER_DIRS` to a list of paths separated by the operating system's path separator, which is a semicolon on Windows and a colon on Unix-like systems.

```powershell
# Windows (PowerShell)
$env:FILE_ACCESS_LOGGER_DIRS = "C:\Path\One;C:\Path\Two"
python app.py
```

```bash
# macOS or Linux
export FILE_ACCESS_LOGGER_DIRS="/path/one:/path/two"
python app.py
```

The application supports the following environment variables:

| Variable | Description | Default |
| --- | --- | --- |
| `FILE_ACCESS_LOGGER_DIRS` | Directories to monitor, separated by the OS path separator | Documents, Downloads, and Desktop, or the home directory |
| `FILE_ACCESS_LOGGER_DB` | Path to the SQLite database file | `data/file_events.db` within the project directory |
| `FILE_ACCESS_LOGGER_HOST` | Host interface the server binds to | `127.0.0.1` |
| `FILE_ACCESS_LOGGER_PORT` | Port the server listens on | `5000` |
| `FILE_ACCESS_LOGGER_ASYNC_MODE` | Socket.IO asynchronous mode | `threading` |

The server binds to `127.0.0.1` by default, so the dashboard is reachable only from the same machine. The application has no authentication and exposes an endpoint that deletes all recorded events, so expose it on a network interface only when you understand the risk. To make it reachable from other machines, set `FILE_ACCESS_LOGGER_HOST` to `0.0.0.0`.

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Serves the dashboard page |
| `GET` | `/api/stats` | Returns event totals and counts by type |
| `GET` | `/api/initial_events` | Returns the most recent events |
| `POST` | `/api/clear` | Deletes all recorded events; requires a JSON request |

## Testing

Run the Python test suite from the project directory:

```bash
python -m unittest discover -s tests
```

The dashboard script has its own test suite, which requires Node.js and jsdom:

```bash
npm install jsdom
node tests/test_dashboard.js
```

Both suites run against temporary data and stubbed network calls. They do not modify the configured directories, the database, or any existing data.

## Screenshot

<img width="1584" height="927" alt="File Access Logger dashboard screenshot" src="https://github.com/user-attachments/assets/f608582c-f57b-48ed-86da-42d4d494902f" />

## Limitations

The application detects changes by polling at a fixed interval, so files that are created and removed between two consecutive scans may not be recorded. When a monitored directory cannot be read, for example because a removable drive was disconnected or its permissions changed, the application skips that directory until access is restored rather than reporting its contents as deleted. Process attribution is best-effort and may report the process as unknown when the responsible process has already exited or its details are not accessible. The event table grows without bound, so use the Clear All Events action periodically to keep the database small. The built-in server is intended for local use and is not suitable for production deployment.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
