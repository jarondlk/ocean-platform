# C23 durable single-host journal

This is a new trusted control-plane module, independent of the original
non-executing supervisor. Its97-case final local acceptance is recorded in
`review-amendment/acceptance.json`. The earlier93-case receipt is immutable and
is explicitly superseded after independent review found two real safety issues.
It must not be treated as acceptance of the corrected source.

`DurableExecutionJournal(root, *, host_boot_id=None, host_id=None,
clock_ns=time.monotonic_ns, sqlite_module=sqlite3)` requires an existing canonical
absolute0700 directory owned by the controller. Linux defaults read the actual
boot UUID and hash `/etc/machine-id`. A root marker binds the single local host,
root path and control-file inodes; partial loss, copied roots or wrong identities
fail closed. Operators must not discard/replace the directory as a recovery
strategy. Total storage loss still requires independent runtime reconciliation;
this module does not infer termination from absent data.

Use `with journal.claim(job_id, envelope_sha256) as lease:` and keep the context
open through every runtime effect. `lease.require_current()` / `snapshot()`
returns immutable detached events, epoch, result and `reconciliation_required`.
`append(kind, payload)` records an intent/observation; `finish(dict)` atomically
retains one immutable generic control result. `journal.read(job_id, hash)` returns
a detached snapshot orNone and grants no effect authority. Subsequent nonterminal
claims always require reconciliation; no elapsed lease, missing state, journal
result or process crash proves a sandbox stopped or releases C22 capacity.

The job's persistent0600 lock uses nonblocking exclusive flock through effects.
Claims/append/finish use SQLite BEGIN IMMEDIATE, WAL and synchronous FULL, followed
by verified readback. Every event binds job/envelope/epoch, stable host identity,
boot UUID, per-boot monotonic clock, exact finite JSON and prior hash. Limits are
4096events,64KiB event payloads and1MiB terminal records. Trusted driver selection
queries `SELECT sqlite_version()` on each real connection; the safe-version gate
requires3.51.3+ or the documented3.50.7+/3.44.6+ backports for the WAL-reset fix.
Drivers without setlimit use byte-bounded SQL projections and SQL payload/result
constraints; no version-bypass Boolean is supplied.

Independent review corrections are covered by actual regressions:

- No persistent raw database FD remains. The first-create descriptor closes
  before any SQLite connection; subsequent checks use lstat inode pins. Real
  spawned POSIX byte-lock probes show that closing another journal does not
  cancel a live SQLite transaction's locks; a later unlocked probe is the
  positive control.
- A process-wide registry rejects different selected driver/module/function
  identities for one live database. Use one approved operator environment and
  pin its actual library; matching a reported version alone is not provenance.
- Fork callbacks reset both the global registry mutex and each journal mutex,
  close only child copies of lock FDs without LOCK_UN, and deny inherited PID
  authority. The bounded multithreaded-fork test proves a vanished parent thread
  cannot leave a child blocked before the PID check.

Other tests use actual separate-process contention, SIGKILL during committed and
uncommitted work, reopen/fencing, atomic finish rollback, SQL immutability,
hashchain corruption, path/hardlink/symlink/inode failures, clock reboot/rollback,
finite JSON/resource bounds and detached terminal replay. All97 final cases and
Ruff pass with both new source files unchanged during the recorded run.

This receipt covers macOS local SQLite/flock/process behavior with SQLite3.53.4.
It does not claim Linux/gVisor containment, whole-sandbox termination, output
extraction, scientific correctness, cloud durability under power loss or C23
completion. FULL durability depends on a working local filesystem/storage stack;
WAL/flock is not a distributed/NFS lease. The root/controller and selected SQLite
driver are trusted. SQL triggers/hash chains do not defend against a privileged
host attacker who replaces both retained data and its integrity metadata.

Primary references inspected2026-10-24:
[SQLite WAL and fixed releases](https://www.sqlite.org/wal.html),
[synchronous settings](https://www.sqlite.org/pragma.html#pragma_synchronous),
[SQLite POSIX-close/multiple-library hazards](https://sqlite.org/howtocorrupt.html),
[flock semantics](https://man7.org/linux/man-pages/man2/flock.2.html).
