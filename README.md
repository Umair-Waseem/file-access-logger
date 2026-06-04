# 📁 File Access Logger

**File Access Logger** is a lightweight **Flask-based web dashboard** for monitoring file activity in local directories. It detects file **creation**, **modification**, and **deletion** events, stores the logged activity in a **SQLite** database, and displays recent file events in real time using **Flask-SocketIO**.

---

## ✨ Features

* 📡 **Real-time browser-based dashboard** for monitoring file activity
* 🗄️ **SQLite event storage** managed with SQLAlchemy
* ⚙️ **Configurable directory monitoring**
* 📊 **Event counters** for created, modified, and deleted files
* 📝 **Recent activity table** displaying:

  * File path
  * Directory
  * Process
  * PID
  * User
  * Timestamp
* 🛡️ **Safe exclusion** of the application’s own SQLite database files from monitoring

---

## 🗂️ Project Structure

```text
.
├── app.py              # Flask application entry point
├── config.py           # Runtime configuration and default monitored directories
├── models.py           # SQLAlchemy database model and database setup
├── monitor.py          # File scanning, event detection, and event logging
├── routes.py           # Dashboard and API routes
└── requirements.txt    # Python dependencies
```

---

## ✅ Requirements

* Python **3.10** or newer
* Windows, macOS, or Linux

---

## ⚙️ Installation

Install the required dependencies:

```powershell
python -m pip install -r requirements.txt
```

---

## ▶️ Running the Application

Start the application:

```powershell
python app.py
```

Open the dashboard in your browser:

```text
http://127.0.0.1:5000
```

---

## 🛠️ Configuration

By default, the application monitors the current user’s **Documents**, **Downloads**, and **Desktop** directories, if they exist.

To monitor custom directories, set the `FILE_ACCESS_LOGGER_DIRS` environment variable before starting the application.

On Windows, separate multiple directory paths with semicolons:

```powershell
$env:FILE_ACCESS_LOGGER_DIRS="C:\Path\One;C:\Path\Two"
python app.py
```

### Optional Environment Variables

| Variable                        | Description                                  |
| ------------------------------- | -------------------------------------------- |
| `FILE_ACCESS_LOGGER_DB`         | SQLite database path                         |
| `FILE_ACCESS_LOGGER_HOST`       | Flask host; default is `0.0.0.0`             |
| `FILE_ACCESS_LOGGER_PORT`       | Flask port; default is `5000`                |
| `FILE_ACCESS_LOGGER_ASYNC_MODE` | Socket.IO async mode; default is `threading` |

---

## 🔌 API Endpoints

| Method | Endpoint              | Description                                       |
| ------ | --------------------- | ------------------------------------------------- |
| `GET`  | `/api/stats`          | Returns event totals and counts by event type     |
| `GET`  | `/api/initial_events` | Returns the most recent file events               |
| `POST` | `/api/clear`          | Clears all logged events; requires a JSON request |

---

## 🖼️ Screenshots

<img width="1584" height="927" alt="File Access Logger dashboard screenshot" src="https://github.com/user-attachments/assets/f608582c-f57b-48ed-86da-42d4d494902f" />

---

## 📝 Notes

This project uses **polling** to detect file changes. Very fast create/delete operations that occur between scan intervals may be missed.

Process attribution is performed on a **best-effort** basis and may not always identify the exact process responsible for a file event.
