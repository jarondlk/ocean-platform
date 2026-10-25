# C23 fixed guest tmpfs quota amendment

This intentionally supersedes only the four additive trusted-init/profile-v2
source files listed in `prior-source.json`. Their exact earlier bytes are
preserved in `prior-source/`; the original 78-case receipt and initially built
scientific image remain historical evidence. Original accepted C23 preparation,
C22 services/models/migrations, and their receipts are unchanged. This is local
preparation evidence; execution, dispatch, capacity release and C23 completion
remain false.

## Pinned upstream findings

Audited upstream ref: `google/gvisor release-20261019.0`.

- [runsc/boot/vfs.go](https://github.com/google/gvisor/blob/release-20261019.0/runsc/boot/vfs.go#L75)
  permits OCI tmpfs data keys mode,size,uid,gid. The tmpfs branch at line1081
  filters through that whitelist, so nr_inodes does not reach the filesystem.
  ParseMountOptions at line1168 ignores unknown remaining options. Merely putting
  nr_inodes in OCI options therefore cannot prove an inode limit.
- [tmpfs.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/fsimpl/tmpfs/tmpfs.go)
  parses size and nr_inodes when supplied directly, reports bounded page/inode
  totals, and counts the root directory as one inode.
  [filesystem.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/fsimpl/tmpfs/filesystem.go)
  accounts inode/page allocations against those limits. These implementation
  findings still require actual write/fallocate/mmap/inode exhaustion probes.
- [sys_mount.go](https://github.com/google/gvisor/blob/release-20261019.0/pkg/sentry/syscalls/linux/sys_mount.go#L26)
  requires CAP_SYS_ADMIN in the guest mount namespace, sets nosuid/nodev/noexec
  flags, copies mount data directly to GetFilesystemOptions.Data (line93), and
  calls MountAt (line141). This path bypasses the OCI whitelist.
- [automatic /tmp](https://github.com/google/gvisor/blob/release-20261019.0/runsc/boot/vfs.go#L1259)
  is skipped for an explicit mount. Otherwise an empty/absent /tmp gets writable
  mode01777 tmpfs. Profile-v3 explicitly mounts tiny readonly /tmp and /dev/shm.
  Mandatory mounts also include proc/sys/dev/devpts; no automatic /run or
  /var/tmp mount was found in this pinned boot path. Those stay on readonly root.
- No enforcing maskedPaths implementation was found in the audited boot/loader
  path; this amendment does not rely on that OCI field. Readonly tmpfs ro,size,
  nosuid,noexec are handled by the boot parser. Its nodev text is not treated as
  separate proof for the tiny readonly directories; those contain no device
  nodes and deny writes. The two writable mounts use the syscall path, which
  explicitly implements nodev.

## Exact privilege and mount boundary

The sealed init version becomes `c23-trusted-init-v2`; profile version becomes
`c23-oci-execution-preparation-v3`. The image/helper path and ImagePreparation
schema stay unchanged. Policy adds only bounded,4096-aligned scratch_max_bytes;
the existing output_file_budget_bytes is now explicitly page-aligned as well.
No policy field can select another mount path, source, type, UID/GID, flags or
inode quota.

Before analysis exists, trusted root PID1 requires the exact six starting
capabilities: original DAC_READ_SEARCH,KILL,SETGID,SETUID,SETPCAP plus transient
SYS_ADMIN. Existing guest/PID1 guards run before privileged operations. Init
disables dumpability and keepcaps, then mounts exactly:

| Path | Byte quota | Inode quota | Owner/mode | Flags |
|---|---|---|---|---|
| /outputs | approved derived file budget | 512 including root | 65532:65532,0700 | nosuid,nodev,noexec |
| /scratch | approved derived scratch budget | 4096 including root | 65532:65532,0700 | nosuid,nodev,noexec |

Each mount must read back exact blocks, free blocks, inode totals/free counts,
owner/mode and safety flags through stat/statvfs. An ignored inode option, wrong
mount result or residual resource use refuses startup. Real filesystem type,
ENOSPC and hostile behavior remain actual-host acceptance gates.

After mounting, init drops all six bounding bits, applies Linux capability ABIv3
capset to retain exactly the original five CURRENT effective/permitted bits,
clears ambient capabilities, and verifies bounding/inheritable/ambient zero,
SYS_ADMIN absent, and noNewPrivs1. Only then may it fork the analysis. The analysis
still transitions to UID/GID65532, empty groups, all capability sets zero and
noNewPrivs1. No untrusted code or arbitrary host exec runs during the mount window.

Readonly /tmp and /dev/shm have fixed size4096,uid/gid0,mode0555; the application
uses HOME/TMPDIR=/scratch and MPLCONFIGDIR=/scratch/matplotlib. Actual write-denial
probes must cover /tmp,/dev/shm,/run,/var/tmp and discover any remaining writable
path. This document makes no all-guest byte/inode claim from static options.

## Required actual acceptance

Rebuild a separately tagged image from the new frozen wrapper, preserving the
old image. Bind its digest and materialized readonly rootfs inventory to the
profile. On the pinned Linux/runsc worker, measure actual output/scratch byte
and inode exhaustion, readback, analysis capability/UID/proc-FD isolation,
temporary-path denials and descendants/outer-cgroup termination. Local mocked
capability/mount tests never execute real mount,kill,setuid or cap operations.
Their receipt is insufficient for real containment or C22 reservation release.
