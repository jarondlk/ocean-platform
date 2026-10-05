#!/bin/sh
# Read-only inventory of the exact runtime. No exploits, mounts or secret reads.
set -eu
uid=$(id -u)
test "$uid" -ne 0
printf 'runtime_uid=%s\n' "$uid"
for binary in infocmp nsenter mount umount; do
    if command -v "$binary" >/dev/null 2>&1; then
        printf 'Unexpected runtime CLI: %s\n' "$binary" >&2
        exit 1
    fi
done
printf 'unused_affected_cli_paths=absent\n'
for path in /usr/lib/systemd/systemd-homed /usr/libexec/systemd-homed /lib/systemd/systemd-homed; do
    test ! -e "$path"
done
printf 'systemd_homed=absent\n'
if command -v perl >/dev/null 2>&1; then
    if module_output=$(perl -MArchive::Tar -e 1 2>&1); then
        printf 'Unexpected Archive::Tar runtime module\n' >&2
        exit 1
    fi
    case "$module_output" in
        *"Can't locate Archive/Tar.pm"*) printf 'perl_archive_tar=absent\n' ;;
        *) printf 'Could not verify Archive::Tar absence\n' >&2; exit 1 ;;
    esac
else
    printf 'perl_runtime=absent\n'
fi
entries=''
if test -e /etc/fstab; then
    entries=$(awk '!/^[[:space:]]*(#|$)/ {print}' /etc/fstab)
fi
test -z "$entries"
printf 'configured_fstab_mounts=none\n'
# Unreadable private directories are unreachable to this runtime UID. The
# Containerfile removes privilege bits with root visibility before USER changes.
privileged=$(find / -xdev -type f -perm /6000 -print 2>/dev/null || true)
test -z "$privileged"
printf 'reachable_setuid_setgid_files=none\n'
awk '/^CapEff:/ {print "effective_capabilities=" $2; if ($2 !~ /^0+$/) exit 1}' /proc/self/status
