"""Single-host durable C23 control records and effect-scoped OS locks.

The root must be a trusted private directory on one host's local filesystem.
SQLite WAL/FULL and flock are not distributed leases or NFS guarantees. A lease
must remain open throughout every runtime effect. Process death releases its OS
lock, but never proves a sandbox stopped: reacquisition requires reconciliation.
No record, elapsed time or missing state grants dispatch or C22 release authority.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from types import ModuleType
import uuid
import weakref

from orchestration.experiment_sandbox.contracts import SandboxError

VERSION = 'c23-durable-journal-v1'
MAX_EVENTS = 4096
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_EPOCH = 2**63 - 1
_JOB = re.compile(r'^c23-[a-f0-9]{48}$')
_SHA = re.compile(r'^[a-f0-9]{64}$')
_KIND = re.compile(r'^[a-z][a-z_]{0,39}$')
_ZERO = '0' * 64
_RESERVED = {'claimed', 'finished'}
_AUTHORITY = {'dispatch_eligible': False, 'reservation_released': False,
              'scientific_approval': 'not_independently_verified'}
_DATABASE_MUTEX = threading.RLock()
_LIVE_DATABASES = {}


def _reset_database_registry_after_fork():
    # Never acquire an inherited lock, which another vanished thread may hold.
    global _DATABASE_MUTEX
    _DATABASE_MUTEX = threading.RLock()
    _LIVE_DATABASES.clear()


os.register_at_fork(after_in_child=_reset_database_registry_after_fork)

_TABLES = {
    'metadata': 'CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL CHECK(length(CAST(value AS BLOB)) <= 4096))',
    'jobs': '''CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY, envelope_sha256 TEXT NOT NULL,
        epoch INTEGER NOT NULL CHECK(epoch >= 0), sequence INTEGER NOT NULL CHECK(sequence >= 0),
        head_sha256 TEXT NOT NULL, lock_device INTEGER NOT NULL, lock_inode INTEGER NOT NULL)''',
    'events': '''CREATE TABLE events (
        job_id TEXT NOT NULL REFERENCES jobs(job_id), sequence INTEGER NOT NULL,
        epoch INTEGER NOT NULL, envelope_sha256 TEXT NOT NULL, host_id TEXT NOT NULL,
        host_boot_id TEXT NOT NULL, monotonic_ns INTEGER NOT NULL, kind TEXT NOT NULL,
        payload_json TEXT NOT NULL CHECK(length(CAST(payload_json AS BLOB)) <= 65536),
        previous_sha256 TEXT NOT NULL, sha256 TEXT NOT NULL,
        PRIMARY KEY(job_id, sequence))''',
    'results': '''CREATE TABLE results (
        job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), epoch INTEGER NOT NULL,
        document_json TEXT NOT NULL CHECK(length(CAST(document_json AS BLOB)) <= 1048576),
        sha256 TEXT NOT NULL,
        event_sequence INTEGER NOT NULL, event_sha256 TEXT NOT NULL)''',
}
_TRIGGERS = {
    f'{table}_no_{operation.lower()}':
    f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
    "BEGIN SELECT RAISE(ABORT, 'immutable journal record'); END"
    for table in ('metadata', 'events', 'results') for operation in ('UPDATE', 'DELETE')
}
_TRIGGERS.update({
    'jobs_identity': "CREATE TRIGGER jobs_identity BEFORE UPDATE OF job_id, envelope_sha256, lock_device, lock_inode ON jobs BEGIN SELECT RAISE(ABORT, 'immutable job identity'); END",
    'jobs_no_delete': "CREATE TRIGGER jobs_no_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT, 'immutable job identity'); END",
})


def _error(reason):
    raise SandboxError(reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(job_id, envelope_sha256):
    if (type(job_id) is not str or not _JOB.fullmatch(job_id)
            or type(envelope_sha256) is not str or not _SHA.fullmatch(envelope_sha256)):
        _error('sandbox_journal_identity')


def _boot(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, AttributeError):
        _error('sandbox_journal_host_identity')


def _linux_identity(path, *, boot=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            raw = os.read(fd, 129)
            if len(raw) > 128:
                raise ValueError
        finally:
            os.close(fd)
        value = raw.decode('ascii').strip()
        if boot:
            return _boot(value)
        if not re.fullmatch(r'[a-f0-9]{32}', value):
            raise ValueError
        return _sha(('c23-linux-machine-id:' + value).encode())
    except (OSError, ValueError, UnicodeError):
        _error('sandbox_journal_host_identity')


def _encode(value, maximum):
    """Bound JSON before serialization, reject custom types and cycles."""
    seen, count, approximate = set(), 0, 0

    def visit(item, depth):
        nonlocal count, approximate
        count += 1
        if depth > 32 or count > 65536:
            _error('sandbox_journal_limit')
        kind = type(item)
        if kind is str:
            if len(item) > maximum:
                _error('sandbox_journal_limit')
            approximate += len(item.encode('utf-8'))
        elif kind is int:
            if not -2**63 <= item <= MAX_EPOCH:
                _error('sandbox_journal_limit')
            approximate += len(str(item))
        elif kind is float:
            if not math.isfinite(item):
                _error('sandbox_journal_integrity')
            approximate += len(repr(item))
        elif item is None or kind is bool:
            approximate += len('null' if item is None else 'true' if item else 'false')
        elif kind in (dict, list):
            if id(item) in seen or len(item) > 65536:
                _error('sandbox_journal_limit')
            seen.add(id(item))
            approximate += len(item) + 2 + (len(item) if kind is dict else 0)
            for key in item if kind is list else item.keys():
                if kind is dict:
                    if type(key) is not str:
                        _error('sandbox_journal_integrity')
                    visit(key, depth + 1)
                    visit(item[key], depth + 1)
                else:
                    visit(key, depth + 1)
            seen.remove(id(item))
        else:
            _error('sandbox_journal_integrity')
        if approximate > maximum:
            _error('sandbox_journal_limit')

    try:
        if type(value) is not dict:
            _error('sandbox_journal_integrity')
        visit(value, 0)
        text = json.dumps(value, allow_nan=False, ensure_ascii=False,
                          sort_keys=True, separators=(',', ':'))
        if len(text.encode('utf-8')) > maximum:
            _error('sandbox_journal_limit')
        return text
    except SandboxError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _error('sandbox_journal_integrity')


def _decode(text, maximum):
    try:
        if type(text) is not str or len(text) > maximum:
            _error('sandbox_journal_limit')
        if len(text.encode('utf-8')) > maximum:
            _error('sandbox_journal_limit')
        value = json.loads(text, parse_constant=lambda _: _error('sandbox_journal_integrity'))
        if _encode(value, maximum) != text:
            _error('sandbox_journal_integrity')
        return value
    except SandboxError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _error('sandbox_journal_integrity')


def _file_id(st):
    return st.st_dev, st.st_ino


def _private(st, mode, *, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(st.st_mode) or stat.S_IMODE(st.st_mode) != mode
            or st.st_uid != os.geteuid() or (not directory and st.st_nlink != 1)):
        _error('sandbox_journal_path')


def _db_error(error):
    code = getattr(error, 'sqlite_errorcode', None)
    if code is not None and code & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        _error('sandbox_journal_busy')
    if code is not None and code & 255 in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
        _error('sandbox_journal_integrity')
    _error('sandbox_journal_unavailable')


def _safe_sqlite_version(version):
    # Official fixed releases for the 2026 WAL-reset race. No arbitrary
    # "backport approved" Boolean can bypass this gate.
    return (version >= (3, 51, 3)
            or version[:2] == (3, 50) and version[2] >= 7
            or version[:2] == (3, 44) and version[2] >= 6)


def _text_column(name, maximum):
    # Only fixed internal column names are passed. Check byte length in SQLite
    # before transferring a value to Python, including drivers without setlimit.
    return (f"CASE WHEN typeof({name})='text' AND length(CAST({name} AS BLOB))<={maximum} "
            f"THEN {name} ELSE NULL END AS {name}")


def _int_column(name):
    return f"CASE WHEN typeof({name})='integer' THEN {name} ELSE NULL END AS {name}"


@dataclass(frozen=True)
class DurableJournalEvent:
    sequence: int
    epoch: int
    job_id: str
    envelope_sha256: str
    host_id: str
    host_boot_id: str
    monotonic_ns: int
    kind: str
    payload_json: str
    previous_sha256: str
    sha256: str

    @property
    def payload(self):
        return json.loads(self.payload_json)


@dataclass(frozen=True)
class DurableJobSnapshot:
    job_id: str
    envelope_sha256: str
    epoch: int
    events: tuple[DurableJournalEvent, ...]
    reconciliation_required: bool
    _result_json: str | None

    @property
    def result(self):
        return json.loads(self._result_json) if self._result_json is not None else None

    @property
    def terminal(self):
        return self._result_json is not None


class DurableLease:
    """Internal, PID-bound handle; keep its context open around runtime effects."""
    __slots__ = ('_journal', '_pid', '_fd', '_file_id', '_job', '_envelope', '_epoch', '_closed')

    def __init__(self, *args, **kwargs):
        raise TypeError('Use DurableExecutionJournal.claim')

    @property
    def job_id(self):
        return self._job

    @property
    def envelope_sha256(self):
        return self._envelope

    @property
    def epoch(self):
        return self._epoch

    @property
    def reconciliation_required(self):
        return self.snapshot().reconciliation_required

    def require_current(self):
        return self._journal.require_current(self)

    def snapshot(self):
        return self.require_current()

    def append(self, kind, payload):
        return self._journal.append(self, kind, payload)

    def finish(self, result):
        return self._journal.finish(self, result)

    def close(self):
        self._journal._close_lease(self)

    def __enter__(self):
        self.require_current()
        return self

    def __exit__(self, *_):
        self.close()


class DurableExecutionJournal:
    """Durable control history, not a runtime adapter or authorization service.

    Linux defaults read OS machine/boot identity. Tests may supply explicit
    trusted identities; a boot change allows a new monotonic clock origin, while
    changing the stable host identity or moving/copying the root fails closed.
    Recovered jobs never execute, terminate or release reservations automatically.
    """
    durable = True
    distributed = False
    grants_execution = False
    releases_reservations = False

    def __init__(self, root, *, host_boot_id=None, host_id=None,
                 clock_ns=time.monotonic_ns, sqlite_module=sqlite3):
        self._pid, self._closed = os.getpid(), False
        self._registered = False
        self._mutex, self._leases, self._fds = threading.RLock(), {}, []
        if type(sqlite_module) is not ModuleType or any(
            not hasattr(sqlite_module, name) for name in ('connect', 'Row', 'Error')
        ):
            _error('sandbox_journal_sqlite_driver')
        if (not callable(sqlite_module.connect) or not callable(sqlite_module.Row)
                or not isinstance(sqlite_module.Error, type)
                or not issubclass(sqlite_module.Error, Exception)):
            _error('sandbox_journal_sqlite_driver')
        self._sqlite = sqlite_module
        self._driver_fingerprint = (sqlite_module, sqlite_module.connect, sqlite_module.Row, sqlite_module.Error)
        # Verify the selected trusted driver's running library before touching
        # the persistent root. The module's reported version string is not used.
        probe = None
        try:
            probe = self._sqlite.connect(':memory:')
            self.sqlite_runtime_version = self._verify_sqlite(probe)
            self.sqlite_readback_bounds = self._limit_connection(probe)
        except self._sqlite.Error as error:
            _db_error(error)
        finally:
            if probe is not None:
                probe.close()
        self.host_boot_id = _boot(host_boot_id if host_boot_id is not None else
                                  _linux_identity('/proc/sys/kernel/random/boot_id', boot=True))
        self.host_id = host_id if host_id is not None else _linux_identity('/etc/machine-id')
        if type(self.host_id) is not str or not _SHA.fullmatch(self.host_id) or not callable(clock_ns):
            _error('sandbox_journal_host_identity')
        self._clock_ns = clock_ns
        try:
            self.root = Path(root)
            if not self.root.is_absolute() or self.root != self.root.resolve(strict=True):
                _error('sandbox_journal_path')
            _private(self.root.lstat(), 0o700, directory=True)
            self._root_fd = self._directory(self.root)
            self._schema_fd = self._open('schema.lock', self._root_fd, create=True)
            # Initialization only: job effect locks remain nonblocking.
            fcntl.flock(self._schema_fd, fcntl.LOCK_EX)
            try:
                self._initialize()
            finally:
                fcntl.flock(self._schema_fd, fcntl.LOCK_UN)
            self._guard()
        except SandboxError:
            self._close_fds()
            raise
        except (OSError, ValueError, TypeError, self._sqlite.Error):
            self._close_fds()
            _error('sandbox_journal_path')
        reference = weakref.ref(self)

        def after_fork():
            journal = reference()
            if journal is not None:
                journal._after_fork()

        os.register_at_fork(after_in_child=after_fork)

    def _directory(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self._fds.append(fd)
        _private(os.fstat(fd), 0o700, directory=True)
        if _file_id(path.lstat()) != _file_id(os.fstat(fd)):
            _error('sandbox_journal_path')
        return fd

    def _open(self, name, parent, *, create=False):
        try:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            if not create:
                raise
        else:
            # Reject existing hardlinks/symlinks before opening them. In
            # particular, never open a SQLite DB inode as a control-file alias.
            _private(before, 0o600)
            with _DATABASE_MUTEX:
                if _file_id(before) in _LIVE_DATABASES:
                    _error('sandbox_journal_path')
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        if create:
            flags |= os.O_CREAT
        fd = os.open(name, flags, 0o600, dir_fd=parent)
        try:
            _private(os.fstat(fd), 0o600)
            st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if _file_id(st) != _file_id(os.fstat(fd)):
                _error('sandbox_journal_path')
        except Exception:
            os.close(fd)
            raise
        self._fds.append(fd)
        return fd

    def _initialize(self):
        try:
            marker = os.stat('identity.json', dir_fd=self._root_fd, follow_symlinks=False)
        except FileNotFoundError:
            marker = None
        if marker is None:
            # A missing database/marker in an established root is never a reset.
            allowed = {'schema.lock'}
            if set(os.listdir(self._root_fd)) != allowed:
                _error('sandbox_journal_integrity')
            os.mkdir('locks', 0o700, dir_fd=self._root_fd)
            self._locks_fd = self._directory(self.root / 'locks')
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
            fd = os.open('journal.sqlite3', flags, 0o600, dir_fd=self._root_fd)
            try:
                _private(os.fstat(fd), 0o600)
                self._database_identity = _file_id(os.fstat(fd))
                os.fsync(fd)
            finally:
                # MUST precede every SQLite connection. Closing any raw DB FD
                # later can cancel SQLite's same-process POSIX locks (§2.2 of
                # sqlite.org/howtocorrupt.html), even for another journal object.
                os.close(fd)
            self._register_database()
            self._marker = {'version': VERSION, 'host_id': self.host_id, 'root_path': str(self.root),
                            'journal_id': str(uuid.uuid4())}
            for label, fd in (('root', self._root_fd), ('locks', self._locks_fd),
                              ('schema_lock', self._schema_fd)):
                self._marker[label + '_device'], self._marker[label + '_inode'] = _file_id(os.fstat(fd))
            self._marker['database_device'], self._marker['database_inode'] = self._database_identity
            encoded = _encode(self._marker, 4096)
            connection = self._connect(initial=True)
            try:
                connection.execute('BEGIN IMMEDIATE')
                for statement in (*_TABLES.values(), *_TRIGGERS.values()):
                    connection.execute(statement)
                connection.execute('INSERT INTO metadata VALUES (?, ?)', ('identity', encoded))
                connection.execute('COMMIT')
            finally:
                connection.close()
            fd = os.open('identity.json', flags, 0o600, dir_fd=self._root_fd)
            try:
                raw = encoded.encode('utf-8')
                with os.fdopen(fd, 'wb', closefd=False) as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(self._locks_fd)
            os.fsync(self._root_fd)
        else:
            _private(marker, 0o600)
            self._locks_fd = self._directory(self.root / 'locks')
            database = os.stat('journal.sqlite3', dir_fd=self._root_fd, follow_symlinks=False)
            _private(database, 0o600)
            self._database_identity = _file_id(database)
            self._register_database()
            fd = self._open('identity.json', self._root_fd)
            raw = os.read(fd, 4097)
            self._marker = _decode(raw.decode('utf-8'), 4096)
            self._marker_fd = fd
            if self._marker.get('version') != VERSION or self._marker.get('host_id') != self.host_id:
                _error('sandbox_journal_host_identity')
        self._marker_fd = getattr(self, '_marker_fd', None)
        if self._marker_fd is None:
            self._marker_fd = self._open('identity.json', self._root_fd)
        self._marker_encoded = _encode(self._marker, 4096)
        self._guard()
        with self._connection() as connection:
            self._schema(connection)

    def _assert_owner(self):
        if self._closed or self._pid != os.getpid():
            _error('sandbox_fence_lost')

    def _register_database(self):
        with _DATABASE_MUTEX:
            previous = _LIVE_DATABASES.get(self._database_identity)
            if previous is not None and not all(
                left is right for left, right in zip(previous[0], self._driver_fingerprint)
            ):
                _error('sandbox_journal_sqlite_driver')
            _LIVE_DATABASES[self._database_identity] = (
                self._driver_fingerprint, previous[1] + 1 if previous is not None else 1)
            self._registered = True

    def _unregister_database(self):
        if not self._registered or self._pid != os.getpid():
            return
        with _DATABASE_MUTEX:
            previous = _LIVE_DATABASES.get(self._database_identity)
            if previous is not None:
                if previous[1] == 1:
                    del _LIVE_DATABASES[self._database_identity]
                else:
                    _LIVE_DATABASES[self._database_identity] = previous[0], previous[1] - 1
            self._registered = False

    def _guard(self):
        self._assert_owner()
        try:
            if self._marker['root_path'] != str(self.root):
                _error('sandbox_journal_path')
            for label, path, fd, directory in (
                ('root', self.root, self._root_fd, True),
                ('locks', self.root / 'locks', self._locks_fd, True),
                ('schema_lock', self.root / 'schema.lock', self._schema_fd, False),
            ):
                st, current = os.fstat(fd), path.lstat()
                _private(st, 0o700 if directory else 0o600, directory=directory)
                _private(current, 0o700 if directory else 0o600, directory=directory)
                expected = (self._marker[label + '_device'], self._marker[label + '_inode'])
                if _file_id(st) != expected or _file_id(current) != expected:
                    _error('sandbox_journal_path')
            database = os.stat('journal.sqlite3', dir_fd=self._root_fd, follow_symlinks=False)
            _private(database, 0o600)
            expected = self._marker['database_device'], self._marker['database_inode']
            if _file_id(database) != expected or self._database_identity != expected:
                _error('sandbox_journal_path')
            fingerprint = (self._sqlite, self._sqlite.connect, self._sqlite.Row, self._sqlite.Error)
            if not all(left is right for left, right in zip(fingerprint, self._driver_fingerprint)):
                _error('sandbox_journal_sqlite_driver')
            with _DATABASE_MUTEX:
                registered = _LIVE_DATABASES.get(self._database_identity)
                if registered is None or not all(
                    left is right for left, right in zip(registered[0], self._driver_fingerprint)
                ):
                    _error('sandbox_journal_sqlite_driver')
            for name in ('journal.sqlite3-wal', 'journal.sqlite3-shm'):
                try:
                    _private(os.stat(name, dir_fd=self._root_fd, follow_symlinks=False), 0o600)
                except FileNotFoundError:
                    pass  # SQLite may remove sidecars on the last connection close.
            if hasattr(self, '_marker_fd') and self._marker_fd is not None:
                current = os.stat('identity.json', dir_fd=self._root_fd, follow_symlinks=False)
                opened = os.fstat(self._marker_fd)
                _private(current, 0o600)
                _private(opened, 0o600)
                if _file_id(current) != _file_id(opened):
                    _error('sandbox_journal_path')
                raw = os.pread(self._marker_fd, 4097, 0)
                if raw.decode('utf-8') != self._marker_encoded:
                    _error('sandbox_journal_integrity')
        except SandboxError:
            raise
        except (OSError, ValueError, KeyError, UnicodeError):
            _error('sandbox_journal_path')

    def _connect(self, *, initial=False):
        if not initial:
            self._guard()
        connection = self._sqlite.connect(str(self.root / 'journal.sqlite3'), timeout=0,
                                          isolation_level=None)
        try:
            if self._verify_sqlite(connection) != self.sqlite_runtime_version:
                _error('sandbox_journal_sqlite_driver')
            if self._limit_connection(connection) != self.sqlite_readback_bounds:
                _error('sandbox_journal_sqlite_driver')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('PRAGMA fullfsync=ON')
            connection.execute('PRAGMA checkpoint_fullfsync=ON')
            if initial:
                connection.execute('PRAGMA journal_mode=WAL')
            if (connection.execute('PRAGMA journal_mode').fetchone()[0] != 'wal'
                    or connection.execute('PRAGMA synchronous').fetchone()[0] != 2
                    or connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1):
                _error('sandbox_journal_unavailable')
            connection.row_factory = self._sqlite.Row
            return connection
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _verify_sqlite(connection):
        try:
            text = connection.execute('SELECT sqlite_version()').fetchone()[0]
            if type(text) is not str or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', text):
                _error('sandbox_journal_sqlite_version')
            version = tuple(map(int, text.split('.')))
            if not _safe_sqlite_version(version):
                _error('sandbox_journal_sqlite_version')
            return text
        except (AttributeError, TypeError, IndexError):
            _error('sandbox_journal_sqlite_driver')

    @staticmethod
    def _limit_connection(connection):
        if (not callable(getattr(connection, 'setlimit', None))
                or not callable(getattr(connection, 'getlimit', None))):
            return 'bounded-sql-projections'
        maximum = MAX_RESULT_BYTES + MAX_PAYLOAD_BYTES + 16384
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, maximum)
        if connection.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) > maximum:
            _error('sandbox_journal_sqlite_driver')
        return 'sqlite-length-limit-and-bounded-sql-projections'

    @contextmanager
    def _connection(self, *, write=False):
        connection = None
        try:
            connection = self._connect()
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            self._schema(connection)
            yield connection
            self._guard()
            connection.execute('COMMIT')
        except self._sqlite.Error as error:
            _db_error(error)
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def _schema(self, connection):
        expected = {**_TABLES, **_TRIGGERS}
        query = ('SELECT ' + _text_column('name', 128) + ',' + _text_column('sql', 16384)
                 + " FROM sqlite_master WHERE type IN ('table','trigger') LIMIT ?")
        actual = {row['name']: row['sql'] for row in connection.execute(query, (len(expected) + 1,))}
        if actual != expected:
            _error('sandbox_journal_integrity')
        rows = connection.execute('SELECT ' + _text_column('key', 64) + ','
                                  + _text_column('value', 4096) + ' FROM metadata LIMIT 2').fetchall()
        if len(rows) != 1 or rows[0]['key'] != 'identity' or rows[0]['value'] != self._marker_encoded:
            _error('sandbox_journal_integrity')

    def _now(self):
        try:
            value = self._clock_ns()
        except Exception:
            _error('sandbox_journal_clock')
        if type(value) is not int or not 0 <= value <= MAX_EPOCH:
            _error('sandbox_journal_clock')
        return value

    def _load(self, connection, job_id, envelope_sha256):
        job_columns = [_text_column(name, maximum) for name, maximum in (
            ('job_id', 52), ('envelope_sha256', 64), ('head_sha256', 64))]
        job_columns.extend(_int_column(name) for name in ('epoch', 'sequence', 'lock_device', 'lock_inode'))
        row = connection.execute('SELECT ' + ','.join(job_columns) + ' FROM jobs WHERE job_id=?',
                                 (job_id,)).fetchone()
        if row is None:
            return None
        if row['envelope_sha256'] != envelope_sha256:
            _error('sandbox_journal_identity')
        if any(type(row[key]) is not int or row[key] < 0
               for key in ('epoch', 'sequence', 'lock_device', 'lock_inode')):
            _error('sandbox_journal_integrity')
        event_columns = [_text_column(name, maximum) for name, maximum in (
            ('job_id', 52), ('envelope_sha256', 64), ('host_id', 64), ('host_boot_id', 36),
            ('kind', 40), ('payload_json', MAX_PAYLOAD_BYTES), ('previous_sha256', 64), ('sha256', 64))]
        event_columns.extend(_int_column(name) for name in ('sequence', 'epoch', 'monotonic_ns'))
        events = connection.execute('SELECT ' + ','.join(event_columns)
                                    + ' FROM events WHERE job_id=? ORDER BY sequence LIMIT ?',
                                    (job_id, MAX_EVENTS + 1)).fetchall()
        if not events or len(events) > MAX_EVENTS:
            _error('sandbox_journal_integrity')
        current_epoch, previous, clocks, finished = 0, _ZERO, {}, False
        detached, reconcile = [], False
        for sequence, item in enumerate(events, 1):
            fields = {key: item[key] for key in item.keys() if key != 'sha256'}
            if (finished or item['sequence'] != sequence or item['envelope_sha256'] != envelope_sha256
                    or item['host_id'] != self.host_id or item['previous_sha256'] != previous
                    or type(item['epoch']) is not int or not 1 <= item['epoch'] <= MAX_EPOCH
                    or type(item['monotonic_ns']) is not int or not 0 <= item['monotonic_ns'] <= MAX_EPOCH
                    or type(item['kind']) is not str or not _KIND.fullmatch(item['kind'])):
                _error('sandbox_journal_integrity')
            boot = _boot(item['host_boot_id'])
            if boot in clocks and item['monotonic_ns'] < clocks[boot]:
                _error('sandbox_journal_clock')
            clocks[boot] = item['monotonic_ns']
            payload = _decode(item['payload_json'], MAX_PAYLOAD_BYTES)
            if item['kind'] == 'claimed':
                if item['epoch'] != current_epoch + 1 or payload != {
                    'previous_epoch': current_epoch, 'reconciliation_required': current_epoch != 0
                }:
                    _error('sandbox_journal_integrity')
                reconcile, current_epoch = current_epoch != 0, item['epoch']
            elif item['epoch'] != current_epoch or current_epoch == 0:
                _error('sandbox_journal_integrity')
            expected_hash = _sha(_encode(fields, MAX_PAYLOAD_BYTES * 2 + 4096).encode())
            if item['sha256'] != expected_hash:
                _error('sandbox_journal_integrity')
            previous, finished = item['sha256'], item['kind'] == 'finished'
            detached.append(DurableJournalEvent(**dict(item)))
        if row['epoch'] != current_epoch or row['sequence'] != len(detached) or row['head_sha256'] != previous:
            _error('sandbox_journal_integrity')
        result_columns = [_text_column(name, maximum) for name, maximum in (
            ('job_id', 52), ('document_json', MAX_RESULT_BYTES), ('sha256', 64), ('event_sha256', 64))]
        result_columns.extend(_int_column(name) for name in ('epoch', 'event_sequence'))
        result = connection.execute('SELECT ' + ','.join(result_columns)
                                    + ' FROM results WHERE job_id=?', (job_id,)).fetchone()
        encoded = None
        if result is not None:
            encoded = result['document_json']
            document = _decode(encoded, MAX_RESULT_BYTES)
            if (not finished or result['epoch'] != current_epoch
                    or result['event_sequence'] != len(detached) or result['event_sha256'] != previous
                    or result['sha256'] != _sha(encoded.encode())
                    or detached[-1].payload != {'result_sha256': result['sha256']}
                    or set(document) != {'version', 'job_id', 'envelope_sha256', 'epoch', 'record', *_AUTHORITY}
                    or document['version'] != 'c23-durable-control-result-v1'
                    or document['job_id'] != job_id or document['envelope_sha256'] != envelope_sha256
                    or type(document['epoch']) is not int or document['epoch'] != current_epoch
                    or type(document['record']) is not dict
                    or any(type(document[key]) is not type(value) or document[key] != value
                           for key, value in _AUTHORITY.items())):
                _error('sandbox_journal_integrity')
        elif finished:
            _error('sandbox_journal_integrity')
        return DurableJobSnapshot(job_id, envelope_sha256, current_epoch, tuple(detached),
                                  reconcile if encoded is None else False, encoded)

    def _append(self, connection, snapshot, kind, encoded, at):
        if snapshot.terminal:
            _error('sandbox_result_immutable')
        if len(snapshot.events) >= MAX_EVENTS:
            _error('sandbox_journal_limit')
        for event in reversed(snapshot.events):
            if event.host_boot_id == self.host_boot_id:
                if at < event.monotonic_ns:
                    _error('sandbox_journal_clock')
                break
        fields = {'job_id': snapshot.job_id, 'sequence': len(snapshot.events) + 1,
                  'epoch': snapshot.epoch, 'envelope_sha256': snapshot.envelope_sha256,
                  'host_id': self.host_id, 'host_boot_id': self.host_boot_id,
                  'monotonic_ns': at, 'kind': kind, 'payload_json': encoded,
                  'previous_sha256': snapshot.events[-1].sha256 if snapshot.events else _ZERO}
        checksum = _sha(_encode(fields, MAX_PAYLOAD_BYTES * 2 + 4096).encode())
        connection.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (*fields.values(), checksum))
        connection.execute('UPDATE jobs SET epoch=?, sequence=?, head_sha256=? WHERE job_id=?',
                           (snapshot.epoch, fields['sequence'], checksum, snapshot.job_id))
        return DurableJournalEvent(**fields, sha256=checksum)

    def _lock_guard(self, job_id, fd, identity):
        self._guard()
        try:
            st = os.fstat(fd)
            current = os.stat(job_id + '.lock', dir_fd=self._locks_fd, follow_symlinks=False)
            _private(st, 0o600)
            _private(current, 0o600)
            if _file_id(st) != identity or _file_id(current) != identity:
                _error('sandbox_fence_lost')
        except (OSError, ValueError):
            _error('sandbox_fence_lost')

    def claim(self, job_id, envelope_sha256):
        _identity(job_id, envelope_sha256)
        with self._mutex:
            self._guard()
            if job_id in self._leases:
                _error('sandbox_worker_busy')
            fd = None
            try:
                with self._connection() as connection:
                    existing = self._load(connection, job_id, envelope_sha256)
                # Existing jobs must retain their original lock inode forever.
                fd = self._open(job_id + '.lock', self._locks_fd, create=existing is None)
                self._fds.remove(fd)  # Lease owns this descriptor from here.
                identity = _file_id(os.fstat(fd))
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EAGAIN, errno.EACCES):
                        _error('sandbox_worker_busy')
                    raise
                self._lock_guard(job_id, fd, identity)
                if existing is None:
                    os.fsync(fd)
                    os.fsync(self._locks_fd)
                with self._connection(write=True) as connection:
                    snapshot = self._load(connection, job_id, envelope_sha256)
                    if snapshot is None:
                        connection.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                                           (job_id, envelope_sha256, 0, 0, _ZERO, *identity))
                        snapshot = DurableJobSnapshot(job_id, envelope_sha256, 0, (), False, None)
                    else:
                        row = connection.execute('SELECT lock_device,lock_inode FROM jobs WHERE job_id=?',
                                                 (job_id,)).fetchone()
                        if tuple(row) != identity:
                            _error('sandbox_fence_lost')
                    if not snapshot.terminal:
                        if snapshot.epoch >= MAX_EPOCH:
                            _error('sandbox_journal_limit')
                        fresh = DurableJobSnapshot(job_id, envelope_sha256, snapshot.epoch + 1,
                                                   snapshot.events, snapshot.epoch != 0, None)
                        self._append(connection, fresh, 'claimed', _encode({
                            'previous_epoch': snapshot.epoch,
                            'reconciliation_required': snapshot.epoch != 0,
                        }, MAX_PAYLOAD_BYTES), self._now())
                lease = object.__new__(DurableLease)
                for key, value in {'_journal': self, '_pid': os.getpid(), '_fd': fd,
                                   '_file_id': identity, '_job': job_id, '_envelope': envelope_sha256,
                                   '_epoch': fresh.epoch if not snapshot.terminal else snapshot.epoch,
                                   '_closed': False}.items():
                    setattr(lease, key, value)
                self._leases[job_id] = lease
                lease.require_current()  # Verify durable readback before acknowledgement.
                return lease
            except SandboxError:
                self._leases.pop(job_id, None)
                if fd is not None:
                    os.close(fd)
                raise
            except (OSError, ValueError, TypeError, self._sqlite.Error):
                self._leases.pop(job_id, None)
                if fd is not None:
                    os.close(fd)
                _error('sandbox_journal_path')

    def _lease(self, lease, connection):
        try:
            valid = (type(lease) is DurableLease and lease._journal is self
                     and lease._pid == os.getpid() and lease._closed is False
                     and type(lease._epoch) is int and 1 <= lease._epoch <= MAX_EPOCH
                     and type(lease._fd) is int and lease._fd >= 0
                     and self._leases.get(lease._job) is lease)
        except (AttributeError, TypeError):
            valid = False
        if not valid:
            _error('sandbox_fence_lost')
        self._lock_guard(lease._job, lease._fd, lease._file_id)
        snapshot = self._load(connection, lease._job, lease._envelope)
        if snapshot is None or snapshot.epoch != lease._epoch:
            _error('sandbox_fence_lost')
        row = connection.execute('SELECT lock_device,lock_inode FROM jobs WHERE job_id=?',
                                 (lease._job,)).fetchone()
        if tuple(row) != lease._file_id:
            _error('sandbox_fence_lost')
        return snapshot

    def require_current(self, lease):
        with self._mutex, self._connection() as connection:
            return self._lease(lease, connection)

    def read(self, job_id, envelope_sha256):
        """A detached consistent snapshot, never effect or termination authority."""
        _identity(job_id, envelope_sha256)
        with self._mutex, self._connection() as connection:
            return self._load(connection, job_id, envelope_sha256)

    def append(self, lease, kind, payload):
        if type(kind) is not str or not _KIND.fullmatch(kind) or kind in _RESERVED:
            _error('sandbox_journal_integrity')
        encoded = _encode(payload, MAX_PAYLOAD_BYTES)
        with self._mutex:
            with self._connection(write=True) as connection:
                snapshot = self._lease(lease, connection)
                event = self._append(connection, snapshot, kind, encoded, self._now())
            retained = self.require_current(lease)
            if retained.events[-1] != event:
                _error('sandbox_journal_integrity')
            return event

    def finish(self, lease, result):
        encoded_input = _encode(result, MAX_RESULT_BYTES)
        with self._mutex:
            with self._connection(write=True) as connection:
                snapshot = self._lease(lease, connection)
                document = {'version': 'c23-durable-control-result-v1', 'job_id': snapshot.job_id,
                            'envelope_sha256': snapshot.envelope_sha256, 'epoch': snapshot.epoch,
                            'record': json.loads(encoded_input), **_AUTHORITY}
                encoded = _encode(document, MAX_RESULT_BYTES)
                if snapshot.terminal:
                    if snapshot._result_json != encoded:
                        _error('sandbox_result_immutable')
                else:
                    checksum = _sha(encoded.encode())
                    event = self._append(connection, snapshot, 'finished', _encode({
                        'result_sha256': checksum}, MAX_PAYLOAD_BYTES), self._now())
                    connection.execute('INSERT INTO results VALUES (?,?,?,?,?,?)',
                                       (snapshot.job_id, snapshot.epoch, encoded, checksum,
                                        event.sequence, event.sha256))
            retained = self.require_current(lease)
            if retained._result_json != encoded:
                _error('sandbox_journal_integrity')
            return retained.result

    def _close_lease(self, lease):
        with self._mutex:
            if type(lease) is not DurableLease or lease._journal is not self or lease._pid != os.getpid():
                _error('sandbox_fence_lost')
            if lease._closed:
                return
            if self._leases.get(lease._job) is not lease:
                _error('sandbox_fence_lost')
            self._leases.pop(lease._job)
            lease._closed = True
            try:
                if _file_id(os.fstat(lease._fd)) == lease._file_id:
                    try:
                        fcntl.flock(lease._fd, fcntl.LOCK_UN)
                    finally:
                        os.close(lease._fd)
            except OSError:
                pass  # Lost descriptor is not termination or result authority.

    def _close_fds(self):
        for fd in reversed(self._fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds.clear()
        self._unregister_database()

    def _after_fork(self):
        # A different parent thread may have held this lock at fork. No child
        # API may block on the inherited lock before reaching its PID guard.
        self._mutex = threading.RLock()
        # Never LOCK_UN an inherited descriptor: that would unlock the parent's
        # same open-file description. Closing only the child copy is safe.
        for lease in self._leases.values():
            try:
                os.close(lease._fd)
            except OSError:
                pass
            lease._closed = True
        self._leases.clear()
        self._close_fds()
        self._registered = False  # Global child registry was reset, not decremented.
        self._closed = True

    def close(self):
        with self._mutex:
            if self._pid != os.getpid():
                _error('sandbox_fence_lost')
            if self._closed:
                return
            for lease in tuple(self._leases.values()):
                self._close_lease(lease)
            self._close_fds()
            self._closed = True

    def __enter__(self):
        self._assert_owner()
        return self

    def __exit__(self, *_):
        self.close()
