"""Private, single-job worker loop over the retained execution ledger."""
from dataclasses import dataclass
import fcntl
import json
import os
import threading

from orchestration.experiment_sandbox.contracts import SandboxError
from orchestration.experiment_sandbox.journal import DurableExecutionJournal
from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
from orchestration.experiment_sandbox.physical_termination import LinuxTerminationIssuer, PhysicalIssuerConfig
from orchestration.experiment_sandbox.retained_admission import RetainedAdmissionSourcePolicy, RetainedRuntimeHooks
from orchestration.experiment_sandbox.retained_output_store import RetainedOutputWriter
from orchestration.experiment_sandbox.retained_runner import RetainedRunReport, run_retained
from orchestration.experiment_sandbox.retained_work import RetainedWorkQueue
from orchestration.research_experiments import ResearchExperimentError


@dataclass(frozen=True)
class RetainedPollResult:
    state: str
    released: tuple[tuple[str, str], ...] = ()
    report: RetainedRunReport | None = None


class RetainedWorkerSupervisor:
    """Poll one exact worker and drain locally without cancelling active work.

    The host supplies a context manager for preparing and cleaning up the
    read-only job mount. The retained runner owns all admission and execution.
    Callers on the same worker must use the same private journal directory.
    """

    def __init__(self, *, queue, adapter, issuer, source_policy, prepare, output_writer=None):
        if (type(queue) is not RetainedWorkQueue or type(adapter) is not LinuxExecutionAdapter
                or type(adapter.journal) is not DurableExecutionJournal
                or type(issuer) is not LinuxTerminationIssuer or type(issuer.config) is not PhysicalIssuerConfig
                or type(source_policy) is not RetainedAdmissionSourcePolicy or not callable(prepare)
                or (output_writer is not None and type(output_writer) is not RetainedOutputWriter)):
            raise ValueError('An explicit retained execution worker is required')
        self._queue, self._adapter, self._issuer = queue, adapter, issuer
        self._journal, self._issuer_config = adapter.journal, issuer.config
        self._source_policy, self._prepare, self._output_writer = source_policy, prepare, output_writer
        self._state_lock = threading.Lock()
        self._draining = False
        self._active = False
        self._binding()

    def _binding(self):
        self._queue._binding()
        config, source = self._issuer_config, self._source_policy
        if (self._adapter.journal is not self._journal or self._issuer.config is not config
                or config.store is not self._queue._store or config.enabled is not True
                or config.registry.enabled is not True or config.store.config.verifier_registry.enabled is not True
                or config.scope.model_dump() != json.loads(self._queue._policy_json)
                or config.scope.worker_id != self._journal.host_id or config.source_root != source.source_root
                or config._source_policy_bytes != source._policy_bytes
                or config.registry.trust_scope != source.trust_scope):
            raise SandboxError('sandbox_retained_supervisor_binding')
        self._journal._guard()

    def drain(self):
        """Stop picking up new work. An accepted local poll may finish cleanup."""
        with self._state_lock:
            self._draining = True

    def status(self):
        with self._state_lock:
            return {'draining': self._draining, 'active': self._active}

    def poll(self):
        self._binding()
        # Lock the pinned journal directory itself, separate from its per-job
        # effect leases. Hold this lock through staging, execution and teardown.
        fd = os.open(self._journal.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            opened, pinned = os.fstat(fd), os.fstat(self._journal._root_fd)
            if (opened.st_dev, opened.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise SandboxError('sandbox_retained_supervisor_binding')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return RetainedPollResult('busy')
            return self._poll_locked()
        finally:
            os.close(fd)

    def _poll_locked(self):
        released = self._queue.reconcile_recorded_releases()
        with self._state_lock:
            if self._draining:
                return RetainedPollResult('draining', released)
        held = self._queue.list_unreleased()
        if any(row.state != 'reserved' or not row.exact_material for row in held):
            return RetainedPollResult('held', released)
        for row in held:
            try:
                work = self._queue.reopen(row.execution_id)
            except ResearchExperimentError as error:
                if error.status_code not in {403, 404, 409}:
                    raise
                continue
            envelope = work.envelope
            if self._journal.read(envelope.job_id, envelope.envelope_sha256) is not None:
                return RetainedPollResult('held', released)
            with self._state_lock:
                if self._draining:
                    return RetainedPollResult('draining', released)
                self._active = True
            try:
                hooks = RetainedRuntimeHooks(self._queue._bridge, work.owner, self._source_policy,
                    output_writer=self._output_writer)
                with self._prepare(work) as profile:
                    self._binding()
                    report = run_retained(self._adapter, work.identity, envelope, profile,
                        hooks=hooks, issuer=self._issuer)
                return RetainedPollResult('ran', released, report)
            except BaseException:
                self.drain()
                raise
            finally:
                with self._state_lock:
                    self._active = False
        return RetainedPollResult('held' if held else 'idle', released)
