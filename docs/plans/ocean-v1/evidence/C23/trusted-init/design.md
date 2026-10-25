# Sealed guest init preparation

This additive implementation is configuration/local-test preparation. It does
not grant execution eligibility. Original C23 profile, synthetic supervisor,
C22 application source and receipts remain unchanged. Real tests under the
pinned image/runtime must clear every outstanding gate.

The new execution profile uses a trusted root PID1 inside the guest, mapped to a
distinct non-root host UID. Generated analysis remains UID/GID65532. The init's
five capabilities are DAC_READ_SEARCH, KILL, SETGID, SETUID and SETPCAP. It drops
the bounding set before fork; the child drops supplementary groups and all UID/
GID slots, verifies all capability sets empty and noNewPrivileges, then executes
only the fixed approved analysis path with Python isolated mode. PID1's private
host result pipe is replaced by separate child stdout/stderr pipes before child
exec, and all higher descriptors are closed. PID1 disables dumpability.

Every dangerous entrypoint first requires Linux, root PID1 (or its immediate
root child during the UID drop) and the gVisor proc marker directory. Negative
host tests never simulate a successful privileged guard. The additive profile
explicitly requests the optional gVisor marker flag. Actual release support and
marker/capability behavior are runtime gates.

When the main analysis exits, PID1 repeatedly sends SIGKILL to all other guest
processes and reaps until ECHILD. In this sole-init sandbox, no additional host
exec is allowed; every analysis process is a descendant. Only after ECHILD does
PID1 extract exact declared files from tmpfs using bounded FD no-follow reads,
regular/single-link/owner checks and stable metadata. Cleanup time is reserved
inside the approved wall limit, not added after it. Logs are bounded throughout.
Host shutdown/whole-cgroup proof remains separate from the guest writer-stop
condition and must precede reservation release.

The control frame has magic, length, SHA256 and bounded JSON/base64 bytes.
SHA256 detects corruption, not authentication: authority comes from the host
binding the pipe to the exact pinned trusted init. A pre-decode structural
scanner bounds JSON depth/token counts before Python object allocation. Child
logs are opaque data. The host must still run the existing strict output-format
validator, fresh admission and durable journal logic.

V2 inputs are application-owned0500, with exact application-owned0400 files;
the outer job directory remains supervisor-private. This explicitly resolves
v1's structural assumption that the supervisor owns the private input directory.
No temporary permission changes occur during rendering. Actual mapped gofer
readability is still unverified. The independently owned outer cgroup charges
both host command/gofer and sandbox leaves and survives runsc deletion long
enough for the host to prove populated=0.

## Why direct runtime reads were not used

Current upstream `runsc read --size N` is bounded but its Fs.Read implementation
opens using root credentials and O_RDONLY; it supplies neither no-follow nor
regular/single-link metadata evidence. It cannot establish this output contract
alone. [Command](https://github.com/google/gvisor/blob/master/runsc/cmd/read.go),
[implementation](https://github.com/google/gvisor/blob/master/pkg/sentry/control/fs.go).

`tar rootfs-upper` applies only to an overlay rootfs upper layer. The accepted
profile's separate `/outputs` tmpfs is not that layer.
[Command](https://github.com/google/gvisor/blob/master/runsc/cmd/tar.go),
[guide](https://gvisor.dev/docs/user_guide/rootfs_snapshot/).

Filesystem checkpointing supports selected non-root tmpfs only when it has a
private disk-backed memory file; ordinary main-memory tmpfs is excluded. It
does not directly supply typed byte extraction for this profile.
[Guide](https://gvisor.dev/docs/user_guide/fs_snapshot/).

These observations informed the sealed-init design; source inspection and
mock/host tests do not substitute for actual containment evidence.
