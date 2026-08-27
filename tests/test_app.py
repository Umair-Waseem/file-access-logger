import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy import text

# Set test configuration before importing modules that read it at import time
_TEST_DB = tempfile.NamedTemporaryFile(prefix="file_events_test_", suffix=".db", delete=False)
_TEST_DB.close()
_DIR_ONE = os.path.abspath(os.path.join(tempfile.gettempdir(), "dir-one"))
_DIR_TWO = os.path.abspath(os.path.join(tempfile.gettempdir(), "dir-two"))
os.environ["FILE_ACCESS_LOGGER_DB"] = _TEST_DB.name
os.environ["FILE_ACCESS_LOGGER_DIRS"] = os.pathsep.join([_DIR_ONE, _DIR_TWO])
os.environ.pop("FILE_ACCESS_LOGGER_HOST", None)
os.environ.pop("FILE_ACCESS_LOGGER_PORT", None)

import config  # noqa: E402
import monitor  # noqa: E402
from models import Session, FileEvent, init_db, engine  # noqa: E402
import routes  # noqa: E402
from routes import serialize_event  # noqa: E402
from app import app  # noqa: E402


# Release database connections and delete the temporary database after all tests
def tearDownModule():
    engine.dispose()
    try:
        os.remove(_TEST_DB.name)
    except OSError:
        pass


class HelperTests(unittest.TestCase):
    def test_configured_monitor_dirs_are_parsed(self):
        self.assertEqual(config.MONITOR_DIRS, [_DIR_ONE, _DIR_TWO])

    def test_duplicate_directories_are_removed(self):
        path = os.path.join(tempfile.gettempdir(), "a")
        self.assertEqual(config._unique_dirs([path, path]), [os.path.abspath(path)])

    def test_trailing_separator_is_not_a_separate_directory(self):
        path = os.path.join(tempfile.gettempdir(), "a")
        self.assertEqual(config._unique_dirs([path, path + os.sep]), [os.path.abspath(path)])

    def test_directories_are_made_absolute_and_keep_their_order(self):
        home = os.path.abspath(os.path.expanduser("~"))
        other = os.path.join(tempfile.gettempdir(), "b")
        self.assertEqual(config._unique_dirs(["~", other]), [home, os.path.abspath(other)])

    def test_nested_path_is_inside_directory(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        nested_file = os.path.join(directory, "sub", "file.txt")
        self.assertTrue(monitor.is_path_in_directory(nested_file, directory))

    def test_directory_with_shared_prefix_is_not_inside(self):
        parent = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        directory = os.path.join(parent, "watched")
        sibling_file = os.path.join(parent, "watched-backup", "file.txt")
        self.assertFalse(monitor.is_path_in_directory(sibling_file, directory))

    def test_existing_directory_is_readable(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        self.assertTrue(monitor.is_directory_readable(directory))

    def test_missing_directory_is_not_readable(self):
        directory = tempfile.mkdtemp()
        shutil.rmtree(directory, ignore_errors=True)
        self.assertFalse(monitor.is_directory_readable(directory))

    def test_file_path_is_not_a_readable_directory(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        self.assertFalse(monitor.is_directory_readable(handle.name))

    def test_symlink_to_the_database_is_detected(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        link = os.path.join(directory, "shortcut.db")
        try:
            os.symlink(config.DB_PATH, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this system")
        self.assertTrue(monitor.is_internal_database_file(link))

    def test_symlinked_database_is_skipped_by_the_scan(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        link = os.path.join(directory, "shortcut.db")
        try:
            os.symlink(config.DB_PATH, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this system")
        self.assertEqual(monitor.scan_directory(directory), {})

    def test_unrelated_files_are_still_scanned(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "note.txt")
        with open(path, "w") as handle:
            handle.write("data")
        self.assertEqual(list(monitor.scan_directory(directory)), [path])

    def test_file_replaced_by_directory_counts_as_deleted(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "thing")
        with open(path, "w") as handle:
            handle.write("data")
        self.assertEqual(list(monitor.scan_directory(directory)), [path])
        self.assertFalse(monitor.is_deleted_from_directory(path, directory))

        os.remove(path)
        os.mkdir(path)
        self.assertEqual(monitor.scan_directory(directory), {})
        self.assertTrue(monitor.is_deleted_from_directory(path, directory))

    def test_removed_file_counts_as_deleted(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "gone.txt")
        with open(path, "w") as handle:
            handle.write("data")
        os.remove(path)
        self.assertTrue(monitor.is_deleted_from_directory(path, directory))

    def test_file_outside_the_directory_is_not_counted_as_deleted(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        outside = os.path.join(tempfile.gettempdir(), "outside-missing.txt")
        self.assertFalse(monitor.is_deleted_from_directory(outside, directory))

    def test_internal_database_files_are_detected(self):
        db = config.DB_PATH
        self.assertTrue(monitor.is_internal_database_file(db))
        self.assertTrue(monitor.is_internal_database_file(db + "-wal"))
        self.assertTrue(monitor.is_internal_database_file(db + "-journal"))
        self.assertFalse(monitor.is_internal_database_file(os.path.join(tempfile.gettempdir(), "unrelated.txt")))


class SerializeEventTests(unittest.TestCase):
    def test_missing_fields_get_defaults(self):
        data = serialize_event(FileEvent())
        self.assertEqual(data['event_type'], 'Unknown')
        self.assertEqual(data['process_name'], 'Unknown')
        self.assertEqual(data['username'], 'Unknown')
        self.assertEqual(data['pid'], 0)
        self.assertEqual(data['file_path'], '')
        self.assertEqual(data['directory'], os.sep)
        # The timestamp is always a valid ISO-8601 string
        datetime.fromisoformat(data['timestamp'])

    def test_populated_fields_are_preserved(self):
        path = os.path.join(os.sep + "tmp", "sub", "file.txt")
        event = FileEvent(
            file_path=path,
            event_type="File Created",
            process_name="bash",
            pid=42,
            username="alice",
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        )
        data = serialize_event(event)
        self.assertEqual(data['directory'], os.path.dirname(path))
        self.assertEqual(data['pid'], 42)
        self.assertTrue(data['timestamp'].startswith("2026-01-01T12:00:00"))

    def test_naive_timestamp_is_treated_as_utc(self):
        event = FileEvent(timestamp=datetime(2026, 1, 1, 12, 0))
        data = serialize_event(event)
        self.assertTrue(data['timestamp'].endswith("+00:00"))


class DatabaseSetupTests(unittest.TestCase):
    def test_timestamp_column_is_indexed(self):
        init_db()
        names = {index.name for index in FileEvent.__table__.indexes}
        self.assertIn('ix_file_events_timestamp', names)

    def test_index_exists_in_the_database(self):
        init_db()
        session = Session()
        try:
            rows = session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='file_events'"
            )).fetchall()
        finally:
            session.close()
        self.assertIn('ix_file_events_timestamp', {row[0] for row in rows})

    def test_index_is_added_to_a_database_created_without_it(self):
        # A database from an earlier version has the table but no index on timestamp
        legacy = tempfile.NamedTemporaryFile(prefix="legacy_", suffix=".db", delete=False)
        legacy.close()
        self.addCleanup(os.remove, legacy.name)

        connection = sqlite3.connect(legacy.name)
        connection.execute(
            "CREATE TABLE file_events (id INTEGER PRIMARY KEY, timestamp DATETIME, "
            "event_type VARCHAR(50), file_path VARCHAR(500), process_name VARCHAR(100), "
            "pid INTEGER, username VARCHAR(50), command TEXT)"
        )
        connection.execute(
            "INSERT INTO file_events (timestamp, event_type, file_path) "
            "VALUES ('2026-01-01 00:00:00', 'File Created', 'kept.txt')"
        )
        connection.commit()
        connection.close()
        self.assertEqual(self._index_names(legacy.name), set())

        # Run the real init_db against that database, as an upgrading user would
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        environment = dict(os.environ, FILE_ACCESS_LOGGER_DB=legacy.name)
        result = subprocess.run(
            [sys.executable, "-c", "import models; models.init_db()"],
            cwd=project_root, env=environment, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertIn('ix_file_events_timestamp', self._index_names(legacy.name))

        # The upgrade must not disturb rows already stored
        connection = sqlite3.connect(legacy.name)
        kept = connection.execute("SELECT count(*) FROM file_events").fetchone()[0]
        connection.close()
        self.assertEqual(kept, 1)

    @staticmethod
    def _index_names(path):
        connection = sqlite3.connect(path)
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='file_events'"
            ).fetchall()
        finally:
            connection.close()
        return {row[0] for row in rows}

    def test_init_db_can_be_called_repeatedly(self):
        init_db()
        init_db()


class ApiTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = app.test_client()
        self._clear_events()

    def _clear_events(self):
        session = Session()
        try:
            session.query(FileEvent).delete()
            session.commit()
        finally:
            session.close()

    def _add_event(self, event_type, path="/tmp/x", when=None):
        session = Session()
        try:
            event = FileEvent(
                event_type=event_type,
                file_path=path,
                process_name="p",
                pid=1,
                username="u",
                command="c"
            )
            if when is not None:
                event.timestamp = when
            session.add(event)
            session.commit()
        finally:
            session.close()

    def test_index_renders_dashboard(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("File Access Monitor", body)
        self.assertIn("dashboard.css", body)
        self.assertIn("dashboard.js", body)
        self.assertIn(_DIR_ONE, body)

    def test_stats_are_zero_when_empty(self):
        data = self.client.get('/api/stats').get_json()
        self.assertEqual(data['total_events'], 0)
        self.assertEqual(data['recent_events'], 0)
        self.assertEqual(data['created'], 0)
        self.assertEqual(data['modified'], 0)
        self.assertEqual(data['deleted'], 0)

    def test_stats_count_events_by_type(self):
        self._add_event("File Created")
        self._add_event("File Created")
        self._add_event("File Modified")
        self._add_event("File Deleted")

        data = self.client.get('/api/stats').get_json()
        self.assertEqual(data['total_events'], 4)
        self.assertEqual(data['created'], 2)
        self.assertEqual(data['modified'], 1)
        self.assertEqual(data['deleted'], 1)
        self.assertEqual(data['recent_events'], 4)

    def test_recent_events_exclude_events_older_than_an_hour(self):
        self._add_event("File Created", when=datetime.now(timezone.utc) - timedelta(hours=2))

        data = self.client.get('/api/stats').get_json()
        self.assertEqual(data['total_events'], 1)
        self.assertEqual(data['recent_events'], 0)

    def test_initial_events_are_limited_and_newest_first(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(25):
            self._add_event("File Created", path=f"/tmp/f{i}", when=base + timedelta(minutes=i))

        events = self.client.get('/api/initial_events').get_json()['events']
        self.assertEqual(len(events), 20)
        self.assertEqual(events[0]['file_path'], "/tmp/f24")
        self.assertEqual(events[-1]['file_path'], "/tmp/f5")

    def test_clear_requires_json(self):
        self.assertEqual(self.client.post('/api/clear').status_code, 415)

    def test_clear_with_no_events(self):
        response = self.client.post('/api/clear', json={})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'info')
        self.assertEqual(data['cleared'], 0)

    def test_clear_reports_an_error_when_deletion_fails(self):
        self._add_event("File Created")

        class _FailingQuery:
            def count(self):
                return 1

            def delete(self):
                raise RuntimeError("database unavailable")

        class _FailingSession:
            def query(self, *args):
                return _FailingQuery()

            def commit(self):
                pass

            def rollback(self):
                self.rolled_back = True

            def close(self):
                pass

        failing = _FailingSession()
        original = routes.Session
        routes.Session = lambda: failing
        try:
            response = self.client.post('/api/clear', json={})
        finally:
            routes.Session = original

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()['status'], 'error')
        self.assertTrue(getattr(failing, 'rolled_back', False))

    def test_clear_removes_all_events(self):
        self._add_event("File Created")
        self._add_event("File Modified")

        data = self.client.post('/api/clear', json={}).get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['cleared'], 2)

        session = Session()
        try:
            self.assertEqual(session.query(FileEvent).count(), 0)
        finally:
            session.close()


class AttributionPrecedenceTests(unittest.TestCase):
    # Attribution must prefer the process holding the file over one that only names it
    def test_open_file_beats_command_line_mention(self):
        if shutil.which('tail') is None:
            self.skipTest("tail is not available on this system")

        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "held.txt")
        with open(path, "w") as handle:
            handle.write("data")

        # This process only names the file, while tail actually holds it open
        namer = subprocess.Popen(['sh', '-c', 'sleep 30', path],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(namer.wait)
        self.addCleanup(namer.terminate)
        holder = subprocess.Popen(['tail', '-f', path],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.terminate)
        time.sleep(1)

        # The namer must be running, or the test would not be exercising precedence
        self.assertIsNone(namer.poll())
        self.assertIsNone(holder.poll())

        details = monitor.get_process_info_for_file(path, "File Modified")
        self.assertEqual(details['pid'], holder.pid)
        self.assertEqual(details['process_name'], 'tail')

    # Attribution keeps the first command line naming the file, not the last
    def test_first_named_process_is_kept(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "named.txt")

        class _NamingProcess:
            def __init__(self, pid, name):
                self.pid = pid
                self.info = {'pid': pid, 'name': name, 'username': 'u', 'cmdline': ['editor', path]}

            def open_files(self):
                return []

        processes = [_NamingProcess(41, 'first'), _NamingProcess(42, 'second')]
        original = psutil.process_iter
        psutil.process_iter = lambda attrs=None: iter(processes)
        try:
            details = monitor.get_process_info_for_file(path, "File Modified")
        finally:
            psutil.process_iter = original

        self.assertEqual(details['pid'], 41)
        self.assertEqual(details['process_name'], 'first')

    # System processes and init are never blamed for file activity
    def test_system_processes_are_not_attributed(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = os.path.join(directory, "named.txt")

        class _NamingProcess:
            def __init__(self, pid, name):
                self.pid = pid
                self.info = {'pid': pid, 'name': name, 'username': 'u', 'cmdline': ['x', path]}

            def open_files(self):
                return []

        # A python process and init both name the file, so neither may be chosen
        processes = [_NamingProcess(1, 'init'), _NamingProcess(50, 'python3')]
        original = psutil.process_iter
        psutil.process_iter = lambda attrs=None: iter(processes)
        try:
            details = monitor.get_process_info_for_file(path, "File Modified")
        finally:
            psutil.process_iter = original

        self.assertEqual(details['process_name'], 'Unknown Process')
        self.assertEqual(details['pid'], 0)


class ConfigDefaultsTests(unittest.TestCase):
    def test_server_binds_to_localhost_by_default(self):
        self.assertEqual(config.HOST, "127.0.0.1")

    def test_default_port_is_5000(self):
        self.assertEqual(config.PORT, 5000)

    def test_invalid_port_falls_back_to_5000(self):
        os.environ["FILE_ACCESS_LOGGER_PORT"] = "not-a-number"
        self.addCleanup(os.environ.pop, "FILE_ACCESS_LOGGER_PORT", None)
        self.assertEqual(config._get_port(), 5000)

    def test_valid_port_is_used(self):
        os.environ["FILE_ACCESS_LOGGER_PORT"] = "8123"
        self.addCleanup(os.environ.pop, "FILE_ACCESS_LOGGER_PORT", None)
        self.assertEqual(config._get_port(), 8123)


class ChangeDetectionTests(unittest.TestCase):
    def test_identical_state_is_not_a_change(self):
        state = {'mtime': 100.0, 'size': 10}
        self.assertFalse(monitor.has_file_changed(state, dict(state)))

    def test_new_modification_time_is_a_change(self):
        self.assertTrue(monitor.has_file_changed({'mtime': 100.0, 'size': 10},
                                                 {'mtime': 101.0, 'size': 10}))

    def test_new_size_is_a_change(self):
        self.assertTrue(monitor.has_file_changed({'mtime': 100.0, 'size': 10},
                                                 {'mtime': 100.0, 'size': 20}))


class AccessCacheTests(unittest.TestCase):
    def setUp(self):
        monitor.recent_file_operations.clear()
        self.addCleanup(monitor.recent_file_operations.clear)

    def test_operations_are_recorded_for_a_process(self):
        monitor.track_process_file_access(77, "/tmp/one.txt")
        self.assertEqual(len(monitor.recent_file_operations[77]), 1)

    def test_only_the_last_ten_operations_are_kept(self):
        for index in range(15):
            monitor.track_process_file_access(77, f"/tmp/f{index}.txt")
        kept = monitor.recent_file_operations[77]
        self.assertEqual(len(kept), 10)
        self.assertEqual(kept[-1]['file'], "/tmp/f14.txt")

    def test_entries_older_than_thirty_seconds_are_dropped(self):
        monitor.track_process_file_access(77, "/tmp/old.txt")
        monitor.recent_file_operations[77][0]['time'] -= 60
        monitor.track_process_file_access(77, "/tmp/new.txt")
        files = [operation['file'] for operation in monitor.recent_file_operations[77]]
        self.assertEqual(files, ["/tmp/new.txt"])

    def test_recent_attribution_is_reused(self):
        path = os.path.join(tempfile.gettempdir(), "cached.txt")
        monitor.track_process_file_access(os.getpid(), path)

        original = psutil.process_iter
        psutil.process_iter = lambda attrs=None: iter([])
        try:
            details = monitor.get_process_info_for_file(path, "File Modified")
        finally:
            psutil.process_iter = original

        self.assertEqual(details['pid'], os.getpid())

    def test_stale_attribution_is_not_reused(self):
        path = os.path.join(tempfile.gettempdir(), "cached.txt")
        monitor.track_process_file_access(os.getpid(), path)
        # Age the entry past the short reuse window but within the cache lifetime
        monitor.recent_file_operations[os.getpid()][0]['time'] -= 5

        original = psutil.process_iter
        psutil.process_iter = lambda attrs=None: iter([])
        try:
            details = monitor.get_process_info_for_file(path, "File Modified")
        finally:
            psutil.process_iter = original

        self.assertEqual(details['pid'], 0)
        self.assertEqual(details['process_name'], 'Unknown Process')


class ProcessDetailsTests(unittest.TestCase):
    # Minimal stand-in for a psutil.Process that can deny selected attributes
    class _FakeProcess:
        def __init__(self, pid, name=None, username=None, cmdline=None, deny=()):
            self.pid = pid
            self._name = name
            self._username = username
            self._cmdline = cmdline
            self._deny = deny

        def name(self):
            if 'name' in self._deny:
                raise psutil.AccessDenied(self.pid)
            return self._name

        def username(self):
            if 'username' in self._deny:
                raise psutil.AccessDenied(self.pid)
            return self._username

        def cmdline(self):
            if 'cmdline' in self._deny:
                raise psutil.AccessDenied(self.pid)
            return self._cmdline

    def test_provided_info_is_used_and_denied_cmdline_falls_back_to_name(self):
        proc = self._FakeProcess(pid=101, deny=('cmdline',))
        info = {'name': 'bash', 'username': 'alice', 'cmdline': None, 'pid': 101}
        details = monitor.process_details(proc, info)
        self.assertEqual(details['process_name'], 'bash')
        self.assertEqual(details['username'], 'alice')
        self.assertEqual(details['pid'], 101)
        self.assertEqual(details['command'], 'bash')

    def test_all_denied_metadata_yields_defaults_without_raising(self):
        proc = self._FakeProcess(pid=202, deny=('name', 'username', 'cmdline'))
        details = monitor.process_details(proc)
        self.assertEqual(details['process_name'], 'Unknown Process')
        self.assertEqual(details['username'], 'Unknown')
        self.assertEqual(details['pid'], 202)
        self.assertEqual(details['command'], 'Unknown Process')

    def test_command_is_built_from_first_three_cmdline_arguments(self):
        proc = self._FakeProcess(
            pid=303,
            name='python',
            username='u',
            cmdline=['python', 'app.py', '--flag', 'extra']
        )
        details = monitor.process_details(proc)
        self.assertEqual(details['process_name'], 'python')
        self.assertEqual(details['command'], 'python app.py --flag')


if __name__ == '__main__':
    unittest.main()
