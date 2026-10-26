# C23 guest namespace guard — intentional profile-v4 supersession

This amendment changes only the additive execution profile and its focused tests.
Their prior v3 bytes are preserved in `prior-source/`. Original seventeen C23
preparation sources, accepted profile.py, earlier receipts, wrapper and image
remain unchanged. No actual namespace exploit or containment acceptance is
claimed by this source audit or its host-safe policy tests.

## Confirmed pinned source risk

All references use gVisor `release-20261019.0`.

- [task_clone.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/kernel/task_clone.go#L34)
  supports CLONE_NEWUSER and CLONE_NEWNS. Its clone path creates the user namespace
  first (lines130–153), clones the mount namespace under that owner (lines257–264),
  and forks credentials into it (lines322–325). The unshare path likewise creates
  a user namespace before checking namespace privileges (lines986–1000).
- [user_namespace.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/kernel/auth/user_namespace.go#L233)
  permits child user namespaces for a mapped effective UID/GID subject to depth
  and resource limits. It does not require the original CAP_SYS_ADMIN.
- [credentials.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/kernel/auth/credentials.go#L160)
  gives the new namespace complete permitted/effective/bounding capability sets.
  Previous empty capability sets and noNewPrivs do not prevent this namespace
  transition. UID65532 is explicitly mapped by the execution profile.
- [sys_thread.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/syscalls/linux/sys_thread.go#L224)
  implements clone3 by reading its argument structure and calling the same clone
  path. Its unshare entry passes the requested flags into Task.Unshare (line495).
- [sys_mount.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/syscalls/linux/sys_mount.go#L26)
  checks CAP_SYS_ADMIN in the mount namespace's owner. A newly owned user/mount
  namespace can therefore undermine the intended fixed tmpfs quota boundary.
  The exact current runtime outcome must still be measured; default namespace
  resource counters or other accidental restrictions are not our guard.

## Supported narrow guard

[flags.go](https://github.com/google/gvisor/blob/release-20261019.0/runsc/config/flags.go#L118)
defaults OCI guest seccomp to false.
[boot/seccomp.go](https://github.com/google/gvisor/blob/release-20261019.0/runsc/boot/seccomp.go#L40)
ignores the OCI JSON policy when that switch is disabled. Profile-v4 therefore
sets both explicit `--oci-seccomp=true` and a fixed Linux seccomp document.

The document allows ordinary syscalls by default, denies unshare and setns with
EPERM, and denies clone3 with ENOSYS. The latter preserves glibc's ordinary
thread fallback to clone while preventing pointer-contained namespace flags.
Seven separate clone rules deny each individual NEWNS,NEWCGROUP,NEWUTS,NEWIPC,
NEWUSER,NEWPID and NEWNET bit using masked equality. A single rule matching the
combined mask would be insufficient because it would match only all bits set.

[OCI converter](https://github.com/google/gvisor/blob/release-20261019.0/runsc/specutils/seccomp/seccomp.go#L247)
supports masked equality and explicit errno. Its syscall-name lookup may ignore
unsupported names, so a successfully parsed configuration alone is not proof.
[loader.go](https://github.com/google/gvisor/blob/release-20261019.0/runsc/boot/loader.go#L1762)
installs the OCI filter on the new task before execution, and
[task_clone.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/kernel/task_clone.go#L426)
copies filters into descendants. This is the guest policy; Sentry's separate
host syscall filter is not a substitute.

Mount remains allowed by the syscall policy so sealed PID1 can perform its two
fixed mounts with transient SYS_ADMIN. The analysis must have no capabilities
and no route to a newly privileged namespace. Existing UID/group/capability,
noNewPrivs, rootfs sealing and trusted-init cleanup checks remain required.

## Required actual probes

Run stored adversarial programs only through the actual isolated operator path:

1. unshare(0) must return EPERM, demonstrating an active filter rather than just
   a missing namespace capability. NEWUSER and NEWUSER|NEWNS must also fail.
2. setns with an invalid FD must return EPERM; clone3 with an invalid/empty
   structure must return ENOSYS. These invalid calls otherwise have different
   kernel errors and help detect an ignored policy.
3. Raw clone with NEWUSER,NEWNS and combined namespace flags must fail; if an
   unexpected child is created it must immediately exit and the parent must
   reap/report failure. Every descendant remains inside the trusted cleanup.
4. Child direct mount,remount and umount attempts must fail. The parent init's
   original fixed tmpfs mounts and exact quota readbacks must still succeed.
5. Ordinary subprocess, fork and Python/native scientific threads must work;
   repeat namespace denial after exec/fork to verify filter inheritance.

No generated analysis or privileged syscall is executed by the local serializer
tests. Actual startup, namespace/mount denial, byte/inode exhaustion and ordinary
scientific compatibility remain open acceptance gates. Dispatch and release
eligibility stay false.
