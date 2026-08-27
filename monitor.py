# Standard library and third-party imports for monitoring and process attribution
import os
import time
import getpass
import psutil
import shutil
import subprocess
import threading
from models import Session, FileEvent
import config

# Process names excluded from attribution so the logger never blames itself
SYSTEM_PROCESS_NAMES = {'systemd', 'python', 'python3', 'python.exe'}

# Last known metadata of every monitored file
file_states = {}

# Socket.IO instance and monitor thread shared across the module
socketio_instance = None
monitor_thread = None
monitor_lock = threading.Lock()

# Recent file operations per process, used to attribute repeated events quickly
recent_file_operations = {}


# Return an absolute, case-normalized path for reliable comparison
def normalize_path(path):
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


# True when path lies inside directory
def is_path_in_directory(path, directory):
    try:
        normalized_path = normalize_path(path)
        normalized_directory = normalize_path(directory)
        return os.path.commonpath([normalized_path, normalized_directory]) == normalized_directory
    except ValueError:
        return False


# True when a file's modification time or size differs from the recorded state
def has_file_changed(previous, current):
    return previous['mtime'] != current['mtime'] or previous['size'] != current['size']


# True when a tracked path in this directory is no longer a file
def is_deleted_from_directory(path, directory):
    return is_path_in_directory(path, directory) and not os.path.isfile(path)


# Return an absolute, symlink-resolved, case-normalized path for reliable comparison
def resolve_path(path):
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


# True when the directory exists and its contents can be listed
def is_directory_readable(directory):
    try:
        os.listdir(os.path.abspath(os.path.expanduser(directory)))
        return True
    except OSError:
        return False


# True for the logger's own SQLite database and its journal/WAL side files
def is_internal_database_file(path):
    db_path = resolve_path(config.DB_PATH)
    sqlite_files = {
        db_path,
        f"{db_path}-journal",
        f"{db_path}-shm",
        f"{db_path}-wal"
    }
    return resolve_path(path) in sqlite_files


# Current login name, or "Unknown" when it cannot be determined
def current_username():
    try:
        return getpass.getuser()
    except Exception:
        return "Unknown"


# Read a process attribute without raising when the process is gone or denied
def _safe(getter, default=None):
    try:
        return getter()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return default


# Build the attribution record for a process, tolerating missing metadata
def process_details(proc, info=None):
    info = info or {}
    name = info.get('name') or _safe(proc.name) or 'Unknown Process'
    username = info.get('username') or _safe(proc.username) or 'Unknown'

    cmdline = info.get('cmdline')
    if cmdline is None:
        cmdline = _safe(proc.cmdline, [])

    command = ' '.join(cmdline[:3]) if cmdline else name
    return {
        'process_name': name,
        'pid': info.get('pid') or proc.pid,
        'username': username,
        'command': command
    }


# Record a file operation for a process, keeping the last 10 within 30 seconds
def track_process_file_access(pid, file_path):
    current_time = time.time()
    if pid not in recent_file_operations:
        recent_file_operations[pid] = []

    recent_file_operations[pid].append({
        'time': current_time,
        'file': file_path
    })

    recent_file_operations[pid] = [
        op for op in recent_file_operations[pid]
        if current_time - op['time'] < 30
    ][-10:]


# Identify the process responsible for a file operation using several methods
def get_process_info_for_file(file_path, operation_type):
    current_time = time.time()
    # psutil reports resolved paths, so match the scanned path and its resolved form
    file_path_forms = {normalize_path(file_path), resolve_path(file_path)}
    filename = os.path.basename(file_path)

    # Reuse a recent attribution when the same file was just handled by a process
    for pid, operations in list(recent_file_operations.items()):
        recent_file_operations[pid] = [
            op for op in operations
            if current_time - op['time'] < 30
        ][-10:]

        if not recent_file_operations[pid]:
            del recent_file_operations[pid]
            continue

        for op in recent_file_operations[pid]:
            if normalize_path(op['file']) in file_path_forms and current_time - op['time'] < 2:
                try:
                    return process_details(psutil.Process(pid))
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    continue

    # A process holding the file open is stronger evidence than one merely naming it
    named_match = None
    for proc in psutil.process_iter(['pid', 'name', 'username', 'cmdline']):
        try:
            info = proc.info
            process_name = (info.get('name') or '').lower()
            if info.get('pid', 0) <= 1 or process_name in SYSTEM_PROCESS_NAMES:
                continue

            try:
                for opened_file in proc.open_files() or []:
                    if normalize_path(opened_file.path) in file_path_forms:
                        return process_details(proc, info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass

            # Remember the first command line naming the file, used only if nothing has it open
            if named_match is None and filename:
                cmdline = info.get('cmdline') or []
                if any(filename.lower() in argument.lower() for argument in cmdline):
                    named_match = process_details(proc, info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, OSError):
            continue

    if named_match:
        return named_match

    current_user = current_username()

    # Fall back to lsof on Unix-like systems when it is available
    if os.name == 'posix' and shutil.which('lsof'):
        try:
            result = subprocess.run(
                ['lsof', file_path],
                capture_output=True,
                text=True,
                timeout=0.5
            )

            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        proc = psutil.Process(int(parts[1]))
                        details = process_details(proc)
                        details['process_name'] = parts[0]
                        return details
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError,
                psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass

    # No process could be identified for this file
    return {
        'process_name': 'Unknown Process',
        'pid': 0,
        'username': current_user,
        'command': operation_type
    }


# Persist a file event, print it, and stream it to connected dashboards
def log_event(event_type, file_path):
    if is_internal_database_file(file_path):
        return

    session = Session()
    try:
        process_info = get_process_info_for_file(file_path, event_type)

        event = FileEvent(
            event_type=event_type,
            file_path=file_path,
            process_name=process_info['process_name'],
            pid=process_info['pid'],
            username=process_info['username'],
            command=process_info['command']
        )

        session.add(event)
        session.commit()

        directory = os.path.dirname(file_path) or os.path.sep
        filename = os.path.basename(file_path)

        print(f"Event: {event_type} - {filename} in {directory}")
        print(f"  Process: {process_info['process_name']} (PID: {process_info['pid']})")
        print(f"  User: {process_info['username']}")

        if process_info['pid'] > 0:
            track_process_file_access(process_info['pid'], file_path)

        if socketio_instance:
            event_data = {
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type,
                'file_path': event.file_path,
                'directory': directory,
                'process_name': event.process_name,
                'pid': event.pid,
                'username': event.username,
                'command': event.command
            }
            socketio_instance.emit('new_event', event_data)

    except Exception as error:
        print(f"Error logging event: {error}")
        session.rollback()
    finally:
        session.close()


# Scan a directory and return metadata for every readable file
def scan_directory(directory):
    directory = os.path.abspath(os.path.expanduser(directory))
    if not os.path.isdir(directory):
        return {}

    files = {}
    try:
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                path = os.path.join(root, filename)
                if is_internal_database_file(path):
                    continue

                try:
                    stat = os.stat(path)
                    files[path] = {'mtime': stat.st_mtime, 'size': stat.st_size}
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except Exception as error:
        print(f"Error scanning directory {directory}: {error}")

    return files


# Continuously poll the monitored directories for created, modified, and deleted files
def monitor_loop():
    print("File monitoring started")
    print("=" * 50)

    if os.name == 'posix' and shutil.which('lsof'):
        print("[OK] lsof available for process detection")
    else:
        print("[INFO] Using psutil-based process detection")

    # Record the initial state of every monitored directory
    for directory in config.MONITOR_DIRS:
        if not is_directory_readable(directory):
            print(f"[WARN] Skipping unreadable directory: {directory}")
            continue

        current_files = scan_directory(directory)
        file_states.update(current_files)
        print(f"Monitoring: {directory} ({len(current_files)} files)")

    print("=" * 50)
    print("Listening for file changes...\n")

    while True:
        try:
            for directory in config.MONITOR_DIRS:
                # Skip an unreadable directory so its files are not reported as deleted
                if not is_directory_readable(directory):
                    continue

                current = scan_directory(directory)

                # Detect new or modified files
                for path, info in current.items():
                    if path not in file_states:
                        log_event("File Created", path)
                        file_states[path] = info
                    elif has_file_changed(file_states[path], info):
                        log_event("File Modified", path)
                        file_states[path] = info

                # A path that is no longer a file counts as deleted, even if a directory replaced it
                deleted_paths = [
                    path for path in file_states
                    if is_deleted_from_directory(path, directory)
                ]
                for path in deleted_paths:
                    log_event("File Deleted", path)
                    del file_states[path]

            # Pause between scans
            time.sleep(2)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
            break
        except Exception as error:
            print(f"Monitoring error: {error}")
            time.sleep(5)


# Start the monitor loop in a background thread and store the Socket.IO instance
def start_monitoring(socketio):
    global socketio_instance, monitor_thread

    try:
        with monitor_lock:
            if monitor_thread and monitor_thread.is_alive():
                print("[INFO] File monitoring is already running")
                return True

            socketio_instance = socketio

            monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
            monitor_thread.start()

        print("[OK] File monitoring started successfully")
        return True
    except Exception as error:
        print(f"[ERROR] Failed to start monitoring: {error}")
        return False
