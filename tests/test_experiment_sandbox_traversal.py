"""Pure-byte and FD-mocked traversal tests; never set a real host ACL."""
import errno
import os
from pathlib import Path
import stat
import struct
from types import SimpleNamespace

import pytest

from orchestration.experiment_sandbox import traversal


def test_exact_acl_is_only_owner_full_and_named_uid_search():
    raw = traversal.SEARCH_ACL
    assert len(raw) == 44 and struct.unpack_from('<I', raw) == (2,)
    assert list(struct.iter_unpack('<HHI', raw[4:])) == [
        (1, 7, 0xffffffff), (2, 1, 100000), (4, 0, 0xffffffff),
        (16, 1, 0xffffffff), (32, 0, 0xffffffff)]


def test_actual_plain_private_directory_without_mutation(tmp_path):
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    before = directory.stat()
    assert traversal.private_directory(directory) == directory
    assert traversal.private_directory(directory, allow_search=True) == directory
    after = directory.stat()
    assert (before.st_dev, before.st_ino, before.st_mode, before.st_uid, before.st_gid,
            before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_dev, after.st_ino, after.st_mode, after.st_uid, after.st_gid,
        after.st_mtime_ns, after.st_ctime_ns)


@pytest.mark.parametrize('kind', ['symlink', 'file', 'relative', 'mode'])
def test_unsafe_or_nonprivate_path_is_rejected(tmp_path, kind):
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    target = directory
    if kind == 'symlink':
        target = tmp_path / 'linked'
        target.symlink_to(directory, target_is_directory=True)
    elif kind == 'file':
        target = tmp_path / 'file'
        target.write_bytes(b'inert')
    elif kind == 'relative':
        target = Path('.')
    else:
        directory.chmod(0o710)
    with pytest.raises(traversal.TraversalError):
        traversal.private_directory(target)


@pytest.fixture
def model(monkeypatch, tmp_path):
    """Only metadata/xattr syscalls are simulated; real FDs remain closeable."""
    path = (tmp_path / 'private').resolve()
    path.mkdir(mode=0o700)
    actual = path.stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
              'st_size', 'st_mtime_ns', 'st_ctime_ns')
    state = SimpleNamespace(path=path, attrs={}, mode=stat.S_IFDIR | 0o700,
                            uid=0, gid=0, inode=actual.st_ino, calls=[],
                            descriptors=set(), opened=[], closed=[], set_hook=None)
    original_open, original_close, original_fstat = os.open, os.close, os.fstat
    original_lstat = Path.lstat

    def metadata():
        values = {name: getattr(actual, name) for name in fields}
        values.update(st_mode=state.mode, st_uid=state.uid, st_gid=state.gid,
                      st_ino=state.inode)
        return SimpleNamespace(**values)

    def opened(value, flags, *args, **kwargs):
        fd = original_open(value, flags, *args, **kwargs)
        if Path(value) == path:
            state.descriptors.add(fd)
            state.opened.append((fd, flags))
        return fd

    def close(fd):
        if fd in state.descriptors:
            state.closed.append(fd)
            state.descriptors.remove(fd)
        return original_close(fd)

    def get(fd, name):
        assert fd in state.descriptors, 'xattrs must use the bound directory FD'
        value = state.attrs.get(name)
        if isinstance(value, BaseException):
            raise value
        if value is None:
            raise OSError(errno.ENODATA, 'mocked missing POSIX ACL')
        return value

    def set_attribute(fd, name, value, *, flags):
        assert fd in state.descriptors
        assert name == traversal.ACCESS_ACL and flags == os.XATTR_CREATE
        state.calls.append((fd, name, value, flags))
        if state.set_hook is not None:
            state.set_hook()
        else:
            state.attrs[name] = value
            state.mode = stat.S_IFDIR | 0o710

    monkeypatch.setattr(traversal.sys, 'platform', 'linux')
    monkeypatch.setattr(traversal.os, 'getuid', lambda: 0)
    monkeypatch.setattr(traversal.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(traversal.os, 'open', opened)
    monkeypatch.setattr(traversal.os, 'close', close)
    monkeypatch.setattr(traversal.os, 'fstat', lambda fd: metadata() if fd in state.descriptors else original_fstat(fd))
    monkeypatch.setattr(Path, 'lstat', lambda item: metadata() if item == path else original_lstat(item))
    monkeypatch.setattr(traversal.os, 'getxattr', get, raising=False)
    monkeypatch.setattr(traversal.os, 'setxattr', set_attribute, raising=False)
    monkeypatch.setattr(traversal.os, 'XATTR_CREATE', 1, raising=False)
    return state


def test_grant_is_fd_bound_exact_create_only_and_idempotent(model):
    assert traversal.grant_search(model.path) == model.path
    assert len(model.calls) == 1 and model.calls[0][2] == traversal.SEARCH_ACL
    assert traversal.private_directory(model.path, allow_search=True) == model.path
    assert traversal.grant_search(model.path) == model.path
    assert len(model.calls) == 1
    with pytest.raises(traversal.TraversalError):
        traversal.private_directory(model.path)
    assert not model.descriptors
    for _fd, flags in model.opened:
        assert flags & os.O_DIRECTORY and flags & os.O_NOFOLLOW and flags & os.O_CLOEXEC
    assert len(model.closed) == len(model.opened)


@pytest.mark.parametrize('attribute,raw', [
    (traversal.ACCESS_ACL, b'unknown'),
    (traversal.ACCESS_ACL, traversal.SEARCH_ACL + b'\0'),
    (traversal.DEFAULT_ACL, traversal.SEARCH_ACL),
    (traversal.DEFAULT_ACL, b''),
])
def test_unknown_or_default_acl_cannot_be_replaced(model, attribute, raw):
    model.attrs[attribute] = raw
    with pytest.raises(traversal.TraversalError):
        traversal.grant_search(model.path)
    assert model.calls == [] and not model.descriptors


@pytest.mark.parametrize('entry,permissions', [(1, 5), (2, 7), (4, 1), (16, 7), (32, 1)])
def test_extra_read_write_or_other_search_permissions_are_rejected(model, entry, permissions):
    raw = bytearray(traversal.SEARCH_ACL)
    for index in range(5):
        offset = 4 + index * 8
        if struct.unpack_from('<H', raw, offset)[0] == entry:
            struct.pack_into('<H', raw, offset + 2, permissions)
    model.attrs[traversal.ACCESS_ACL] = bytes(raw)
    model.mode = stat.S_IFDIR | 0o710
    with pytest.raises(traversal.TraversalError):
        traversal.private_directory(model.path, allow_search=True)


@pytest.mark.parametrize('problem', ['root_uid', 'root_gid', 'inode_after_set', 'readback', 'set_failure'])
def test_grant_refuses_identity_and_readback_failures_without_chmod_fallback(model, problem):
    if problem == 'root_uid':
        model.uid = 12
    elif problem == 'root_gid':
        model.gid = 12
    else:
        def changed():
            if problem == 'set_failure':
                raise OSError(errno.EEXIST, 'concurrent ACL creation')
            if problem == 'inode_after_set':
                model.inode += 1
            model.mode = stat.S_IFDIR | 0o710
            model.attrs[traversal.ACCESS_ACL] = b'wrong' if problem == 'readback' else traversal.SEARCH_ACL
        model.set_hook = changed
    with pytest.raises(traversal.TraversalError):
        traversal.grant_search(model.path)
    assert not model.descriptors
    if problem.startswith('root_'):
        assert model.calls == []


@pytest.mark.parametrize('attribute', [traversal.ACCESS_ACL, traversal.DEFAULT_ACL])
@pytest.mark.parametrize('number', [errno.ENOTSUP, errno.EINVAL, errno.EACCES, errno.EIO])
def test_linux_only_enodata_means_no_attribute(model, attribute, number):
    model.attrs[attribute] = OSError(number, 'not verified absent')
    with pytest.raises(traversal.TraversalError):
        traversal.private_directory(model.path)


@pytest.mark.parametrize('number', sorted({errno.ENODATA, errno.ENOTSUP, errno.EINVAL,
                                         getattr(errno, 'ENOATTR', errno.ENODATA)}))
def test_macos_plain_mode_preparation_accepts_unavailable_posix_xattr_without_acl_claim(model, monkeypatch, number):
    monkeypatch.setattr(traversal.sys, 'platform', 'darwin')
    model.attrs = {name: OSError(number, 'mocked macOS POSIX ACL unavailable')
                   for name in (traversal.ACCESS_ACL, traversal.DEFAULT_ACL)}
    assert traversal.private_directory(model.path) == model.path
    with pytest.raises(traversal.TraversalError, match='linux_root'):
        traversal.grant_search(model.path)
    assert model.calls == []


@pytest.mark.parametrize('platform', ['darwin', 'linux'])
def test_absent_python_xattr_api_is_preparation_only_on_macos(model, monkeypatch, platform):
    monkeypatch.setattr(traversal.sys, 'platform', platform)
    monkeypatch.delattr(traversal.os, 'getxattr')
    if platform == 'darwin':
        assert traversal.private_directory(model.path) == model.path
        model.mode = stat.S_IFDIR | 0o710
        with pytest.raises(traversal.TraversalError):
            traversal.private_directory(model.path, allow_search=True)
    else:
        with pytest.raises(traversal.TraversalError, match='acl_unavailable'):
            traversal.private_directory(model.path)
        with pytest.raises(traversal.TraversalError, match='acl_unavailable'):
            traversal.grant_search(model.path)
    assert model.calls == []


@pytest.mark.parametrize('platform,ruid,euid', [('darwin', 0, 0), ('linux', 1, 0), ('linux', 0, 1)])
def test_platform_and_both_root_guards_precede_fd_or_acl_effects(monkeypatch, platform, ruid, euid):
    monkeypatch.setattr(traversal.sys, 'platform', platform)
    monkeypatch.setattr(traversal.os, 'getuid', lambda: ruid)
    monkeypatch.setattr(traversal.os, 'geteuid', lambda: euid)
    def forbidden(*args, **kwargs):
        raise AssertionError('effect before Linux real/effective root guard')
    monkeypatch.setattr(traversal, '_open', forbidden)
    with pytest.raises(traversal.TraversalError, match='linux_root'):
        traversal.grant_search('/unread')


@pytest.mark.parametrize('value', [1, 'yes', None])
def test_search_policy_requires_actual_boolean(model, value):
    with pytest.raises(traversal.TraversalError, match='policy'):
        traversal.private_directory(model.path, allow_search=value)
    assert model.opened == []
