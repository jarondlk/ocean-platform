"""Exact operator traversal exception; it grants no read or dispatch authority.

Linux may grant only host UID100000 search on selected supervisor directories.
Files and all other descendants keep their separate private checks. macOS plain
0700 checks are preparation conveniences, not a claim about native macOS ACLs.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
import struct
import sys

SEARCH_UID = 100000
ACCESS_ACL = 'system.posix_acl_access'
DEFAULT_ACL = 'system.posix_acl_default'
_UNDEFINED = 0xffffffff
# Linux POSIX ACL xattr v2: header, then USER_OBJ, named USER, GROUP_OBJ,
# MASK and OTHER. Only named UID100000 receives execute/search permission.
SEARCH_ACL = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in (
    (0x01, 7, _UNDEFINED), (0x02, 1, SEARCH_UID), (0x04, 0, _UNDEFINED),
    (0x10, 1, _UNDEFINED), (0x20, 0, _UNDEFINED)))


class TraversalError(ValueError):
    pass


def _missing_attribute(error):
    if sys.platform == 'linux':
        return error.errno == errno.ENODATA
    if sys.platform == 'darwin':
        return error.errno in {errno.ENODATA, errno.ENOTSUP, errno.EINVAL,
                              getattr(errno, 'ENOATTR', errno.ENODATA)}
    return False


def _attribute(descriptor, name):
    getter = getattr(os, 'getxattr', None)
    if not callable(getter):
        # Some macOS Python builds expose no POSIX xattr API. Only the plain
        # mode/owner preparation branch can pass; this makes no native ACL claim.
        if sys.platform == 'darwin':
            return None
        raise TraversalError('private_directory_acl_unavailable')
    try:
        return getter(descriptor, name)
    except OSError as error:
        if _missing_attribute(error):
            return None
        raise TraversalError('private_directory_acl_unavailable') from error


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid


def _bound(path, descriptor, expected=None):
    opened = os.fstat(descriptor)
    current = path.lstat()
    if (not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(current.st_mode)
            or _stamp(opened) != _stamp(current)
            or expected is not None and _identity(opened) != expected
            or path != path.resolve(strict=True)):
        raise TraversalError('private_directory_changed')
    return opened


def _open(path):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise TraversalError('canonical_private_directory_required')
    before = path.lstat()
    if not stat.S_ISDIR(before.st_mode):
        raise TraversalError('canonical_private_directory_required')
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if _stamp(os.fstat(descriptor)) != _stamp(before):
            raise TraversalError('private_directory_changed')
        _bound(path, descriptor, _identity(before))
    except BaseException:
        os.close(descriptor)
        raise
    return path, descriptor


def _inspect(path, descriptor, *, allow_search):
    before = _bound(path, descriptor)
    access = _attribute(descriptor, ACCESS_ACL)
    default = _attribute(descriptor, DEFAULT_ACL)
    after = _bound(path, descriptor, _identity(before))
    if _stamp(before) != _stamp(after) or default is not None:
        raise TraversalError('private_directory_acl_changed_or_inherited')
    plain = (stat.S_IMODE(after.st_mode) == 0o700
             and after.st_uid == os.geteuid() and access is None)
    search = (allow_search and sys.platform == 'linux'
              and os.getuid() == os.geteuid() == 0
              and (after.st_uid, after.st_gid) == (0, 0)
              and stat.S_IMODE(after.st_mode) == 0o710 and access == SEARCH_ACL)
    if not (plain or search):
        raise TraversalError('private_directory_acl_or_mode')
    return after, access


def private_directory(path, *, allow_search=False):
    """Validate an unchanged canonical directory, permitting only an exact ACL.

``allow_search=False`` rejects even the approved traversal ACL, so journal,
state and diagnostic directories can retain stricter independent boundaries.
"""
    if type(allow_search) is not bool:
        raise TraversalError('private_directory_policy')
    descriptor = None
    try:
        path, descriptor = _open(path)
        _inspect(path, descriptor, allow_search=allow_search)
        return path
    except TraversalError:
        raise
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise TraversalError('private_directory_unavailable') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def grant_search(path):
    """Root/Linux only: create the fixed ACL on the already bound directory FD.

Unknown or default ACLs are refused rather than overwritten. A failed readback
does not infer rollback, availability, execution permission or any release.
"""
    if sys.platform != 'linux' or os.getuid() != 0 or os.geteuid() != 0:
        raise TraversalError('linux_root_traversal_required')
    descriptor = None
    try:
        path, descriptor = _open(path)
        before, access = _inspect(path, descriptor, allow_search=True)
        if (before.st_uid, before.st_gid) != (0, 0):
            raise TraversalError('root_directory_required')
        if access is None:
            # CREATE closes the absent-xattr race; never replace an unknown ACL.
            _bound(path, descriptor, _identity(before))
            os.setxattr(descriptor, ACCESS_ACL, SEARCH_ACL, flags=os.XATTR_CREATE)
        _bound(path, descriptor, _identity(before))
        after, access = _inspect(path, descriptor, allow_search=True)
        if (access != SEARCH_ACL or stat.S_IMODE(after.st_mode) != 0o710
                or _identity(after) != _identity(before)):
            raise TraversalError('search_acl_readback')
        return path
    except TraversalError:
        raise
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise TraversalError('search_acl_unavailable') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
