# Import libraries needed for file monitoring, process management, subprocess handling, and threading.
import os
import time
import getpass
import psutil
import shutil
import subprocess
import threading
from models import Session, FileEvent
import config

SYSTEM_PROCESS_NAMES = {'systemd', 'python', 'python3', 'python.exe'}

# Dictionary to store the last known state of monitored files.
file_states = {}

# Global variable to hold the Socket.IO instance for real-time updates.
socketio_instance = None
monitor_thread = None
monitor_lock = threading.Lock()

# Dictionary to track recent file operations for each process.
recent_file_operations = {}


def normalize_path(path):
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def is_path_in_directory(path, directory):
    try:
        normalized_path = normalize_path(path)
        normalized_directory = normalize_path(directory)
        return os.path.commonpath([normalized_path, normalized_directory]) == normalized_directory
    except ValueError:
        return False


def is_internal_database_file(path):
    db_path = normalize_path(config.DB_PATH)
    sqlite_files = {
        db_path,
        f"{db_path}-journal",
        f"{db_path}-shm",
        f"{db_path}-wal"
    }
    return normalize_path(path) in sqlite_files


def current_username():
    try:
        return getpass.getuser()
    except Exception:
        return "Unknown"


def process_details(proc, info=None):
    info = info or {}
    name = info.get('name') or proc.name()
    username = info.get('username') or proc.username()
    cmdline = info.get('cmdline')

    if cmdline is None:
        cmdline = proc.cmdline()

    command = ' '.join(cmdline[:3]) if cmdline else name
    return {
        'process_name': name,
        'pid': info.get('pid') or proc.pid,
        'username': username or "Unknown",
        'command': command
    }


# Function to track recent file operations for a process.
# It stores the time and file path.
# It keeps only the last 10 operations per process within 30 seconds.
def track_process_file_access(pid, file_path):
    current_time = time.time()
    if pid not in recent_file_operations:
        recent_file_operations[pid] = []
    
    recent_file_operations[pid].append({
        'time': current_time,
        'file': file_path
    })
    
    # Keep only the most recent 10 operations within 30 seconds.
    recent_file_operations[pid] = [
        op for op in recent_file_operations[pid]
        if current_time - op['time'] < 30
    ][-10:]

# Function to identify the process responsible for a file operation.
# It uses multiple methods to obtain process information.
def get_process_info_for_file(file_path, operation_type):
    current_time = time.time()
    normalized_file_path = normalize_path(file_path)
    filename = os.path.basename(file_path)

    # Check recently tracked operations first for repeated events from a process.
    for pid, operations in list(recent_file_operations.items()):
        recent_file_operations[pid] = [
            op for op in operations
            if current_time - op['time'] < 30
        ][-10:]

        if not recent_file_operations[pid]:
            del recent_file_operations[pid]
            continue

        for op in recent_file_operations[pid]:
            if normalize_path(op['file']) == normalized_file_path and current_time - op['time'] < 2:
                try:
                    return process_details(psutil.Process(pid))
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    continue

    # First look for a process that currently has the file open or references
    # the file name in its command line.
    for proc in psutil.process_iter(['pid', 'name', 'username', 'cmdline', 'create_time']):
        try:
            info = proc.info
            process_name = (info.get('name') or '').lower()
            if info.get('pid', 0) <= 1 or process_name in SYSTEM_PROCESS_NAMES:
                continue

            try:
                for opened_file in proc.open_files() or []:
                    if normalize_path(opened_file.path) == normalized_file_path:
                        return process_details(proc, info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass

            cmdline = info.get('cmdline') or []
            if filename and any(filename in argument for argument in cmdline):
                return process_details(proc, info)

            create_time = info.get('create_time')
            if create_time and current_time - create_time < 10 and filename:
                if any(filename.lower() in argument.lower() for argument in cmdline):
                    return process_details(proc, info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError, OSError):
            continue

    current_user = current_username()

    # lsof can identify open files on Unix-like systems when available.
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

    return {
        'process_name': 'Unknown Process',
        'pid': 0,
        'username': current_user,
        'command': operation_type
    }

# Function to log file events in the database.
# It records process details, prints events to console, and sends them to the dashboard.
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
            
    except Exception as e:
        print(f"Error logging event: {e}")
        session.rollback()
    finally:
        session.close()

# Function to scan a directory and collect metadata for all files.
# It safely handles permission errors and missing files.
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
                    files[path] = {
                        'mtime': stat.st_mtime,
                        'size': stat.st_size,
                        'ctime': stat.st_ctime
                    }
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except Exception as e:
        print(f"Error scanning directory {directory}: {e}")
    
    return files

# Main loop to monitor directories continuously.
# It detects file creation, modification, and deletion events.
def monitor_loop():
    print("File monitoring started")
    print("=" * 50)

    if os.name == 'posix' and shutil.which('lsof'):
        print("[OK] lsof available for process detection")
    else:
        print("[INFO] Using psutil-based process detection")
    
    # Initialize file state for monitored directories.
    for directory in config.MONITOR_DIRS:
        if not os.path.isdir(directory):
            print(f"[WARN] Skipping missing directory: {directory}")
            continue

        current_files = scan_directory(directory)
        file_states.update(current_files)
        print(f"Monitoring: {directory} ({len(current_files)} files)")
    
    print("=" * 50)
    print("Listening for file changes...\n")
    
    while True:
        try:
            for directory in config.MONITOR_DIRS:
                current = scan_directory(directory)
                
                # Detect new or modified files.
                for path, info in current.items():
                    if path not in file_states:
                        log_event("File Created", path)
                        file_states[path] = info
                    elif (
                        info['mtime'] != file_states[path]['mtime'] or
                        info['size'] != file_states[path]['size']
                    ):
                        log_event("File Modified", path)
                        file_states[path] = info
                
                # Detect deleted files.
                deleted_paths = [
                    path for path in file_states
                    if is_path_in_directory(path, directory) and not os.path.exists(path)
                ]
                for path in deleted_paths:
                    log_event("File Deleted", path)
                    del file_states[path]
            
            # Pause between scans.
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
            break
        except Exception as e:
            print(f"Monitoring error: {e}")
            time.sleep(5)

# Function to start file monitoring in a separate thread.
# It sets the Socket.IO instance used for real-time dashboard updates.
def start_monitoring(socketio):
    global socketio_instance, monitor_thread
    
    try:
        with monitor_lock:
            if monitor_thread and monitor_thread.is_alive():
                print("[INFO] File monitoring is already running")
                return True

            socketio_instance = socketio

            # Start monitoring loop in a background thread.
            monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
            monitor_thread.start()

        print("[OK] File monitoring started successfully")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to start monitoring: {e}")
        return False
