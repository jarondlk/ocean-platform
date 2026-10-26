"""C23 operator-owned synthetic acceptance; never serving/C22 dispatch wiring.

`prepare-blueprint` generates fake-service fixture bytes locally without running
analysis Python. `run` is guarded to one authorized Linux GCP worker before any
mount, cgroup or runtime effect. Rehashed operator fixtures are explicitly NOT
retained real C22 approvals or reservations and confer no release authority.
"""

from __future__ import annotations

import argparse
import ast
import base64
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
import urllib.error
import uuid

VERSION = "c23-operator-synthetic-acceptance-v1"
PURPOSE = "operator-owned synthetic acceptance"
PROJECT = "ocean-v1-c23-20261024"
INSTANCE = "c23-containment-01"
GCP_API = "https://www.googleapis.com/compute/v1/"
NETWORK = GCP_API + "projects/" + PROJECT + "/global/networks/c23-private"
SUBNET = (
    GCP_API + "projects/" + PROJECT + "/regions/asia-northeast1/subnetworks/c23-tokyo"
)
CONTROL_UID = CONTROL_GID = 100000
APP_UID = APP_GID = 100001
FIXED_ROOT = Path("/var/lib/ocean-c23")
ATTEMPTS_ROOT = FIXED_ROOT / "operator-acceptance"
MAX_FIXTURE = 4 * 1024 * 1024
METADATA_EXTERNAL_IP = "instance/network-interfaces/0/access-configs/0/external-ip"


class OperatorError(ValueError):
    pass


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _read(path, maximum):
    before = Path(path).lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 0 <= before.st_size <= maximum
    ):
        raise OperatorError("operator_file_integrity")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise OperatorError("operator_file_changed")
        raw = bytearray()
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        after = Path(path).lstat()

        def stamp(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_uid,
                info.st_gid,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        if (
            len(raw) != before.st_size
            or stamp(before) != stamp(os.fstat(fd))
            or stamp(before) != stamp(after)
        ):
            raise OperatorError("operator_file_changed")
        return bytes(raw)
    finally:
        os.close(fd)


def _create(path, raw, *, mode=0o400):
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode
    )
    try:
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OperatorError("operator_write_failed")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(
        Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def prepare_blueprint(output):
    """Pure synthetic fixture setup. It never interprets stored analysis code."""
    from unittest.mock import patch
    from sqlalchemy import create_engine, event, select
    from db.app_models import AppBase, ResearchExperimentReservation
    from schema.research_experiments import content_sha256
    from tests.research_experiment_support import make_experiment_fixture

    with tempfile.TemporaryDirectory(prefix="c23-operator-blueprint-") as directory:
        engine = create_engine("sqlite+pysqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        try:
            with patch.dict(
                os.environ,
                {"ENABLE_V1_CATALOGUE": "true", "ENABLE_V1_INVESTIGATIONS": "true"},
            ):
                AppBase.metadata.create_all(engine)
                fixture = make_experiment_fixture(engine, Path(directory))
                request = fixture.request()
                request["proposal"]["question"] = (
                    "Operator-owned synthetic acceptance input blueprint"
                )
                request["proposal"]["python_code"] = (
                    "# Blueprint only; no analysis execution.\npass\n"
                )
                first = fixture.service.invoke("create", request, fixture.user)[
                    "experiment"
                ]
                approved = fixture.service.invoke(
                    "approve", fixture.decision(first), fixture.user
                )["experiment"]
                dispatched = fixture.service.invoke(
                    "dispatch", fixture.decision(approved), fixture.user
                )["experiment"]
                reservation_id = dispatched["dispatch"]["reservation_id"]
                raw = fixture.service.load_execution_envelope(
                    reservation_id, user=fixture.user
                )
                with fixture.factory() as session:
                    retained = session.scalar(
                        select(ResearchExperimentReservation.envelope_sha256).where(
                            ResearchExperimentReservation.id
                            == uuid.UUID(reservation_id)
                        )
                    )
                if retained != content_sha256(raw["metadata"]):
                    raise OperatorError("synthetic_blueprint_hash")
                document = {
                    "version": VERSION,
                    "purpose": PURPOSE,
                    "retained_C22_real_approval": False,
                    "real_C22_reservation_consumption_verified": False,
                    "scientific_approval": "not_independently_verified",
                    "source": "tests.research_experiment_support.make_experiment_fixture; generated CTD/metagenome/SST/eDNA fixtures only",
                    "source_fake_envelope_sha256": retained,
                    "metadata": raw["metadata"],
                    "files_base64": {
                        name: base64.b64encode(value).decode("ascii")
                        for name, value in sorted(raw["files"].items())
                    },
                }
        finally:
            engine.dispose()
    encoded = _canonical(document)
    if len(encoded) > MAX_FIXTURE:
        raise OperatorError("synthetic_blueprint_size")
    _create(Path(output), encoded)
    return {
        "path": str(output),
        "sha256": _sha(encoded),
        "size_bytes": len(encoded),
        "retained_C22_real_approval": False,
        "analysis_executed": False,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise OperatorError("metadata_redirect_denied")


def _metadata(name):
    if name not in {
        "project/project-id",
        "instance/name",
        "instance/id",
        "instance/network-interfaces/",
        "instance/network-interfaces/0/access-configs/",
        METADATA_EXTERNAL_IP,
    }:
        raise OperatorError("metadata_path")
    url = "http://169.254.169.254/computeMetadata/v1/" + name
    request = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=3) as response:
            raw = response.read(257)
            if (
                response.status != 200
                or response.geturl() != url
                or response.headers.get("Metadata-Flavor") != "Google"
                or len(raw) > 256
            ):
                raise OperatorError("metadata_response")
    except urllib.error.HTTPError as error:
        if (
            error.code == 404
            and name == "instance/network-interfaces/0/access-configs/"
            and error.geturl() == url
            and error.headers.get("Metadata-Flavor") == "Google"
        ):
            return ""
        raise
    # Only a verified terminal HTTP200 with an actually empty body proves this
    # live address observation. A known config folder may persist without an IP.
    return (
        raw.decode("ascii")
        if name == METADATA_EXTERNAL_IP
        else raw.decode("ascii").strip()
    )


def _boot_id():
    value = _kernel_read("/proc/sys/kernel/random/boot_id", 128).decode("ascii").strip()
    if str(uuid.UUID(value)) != value:
        raise OperatorError("operator_host_boot_identity")
    return value


def require_worker(metadata_reader=_metadata):
    if (
        sys.platform != "linux"
        or os.getuid() != 0
        or os.geteuid() != 0
        or os.uname().machine != "x86_64"
        or socket.gethostname().split(".")[0] != INSTANCE
    ):
        raise OperatorError("dedicated_linux_root_worker_required")
    if (
        metadata_reader("project/project-id") != PROJECT
        or metadata_reader("instance/name") != INSTANCE
    ):
        raise OperatorError("dedicated_gcp_target_required")
    return {"project": PROJECT, "instance": INSTANCE, "linux_root_guard": True}


def prepare_host_controls(output):
    """Trusted setup ONLY, before temporary VM egress is removed."""
    target = require_worker()
    _control_output(output)
    target.update(host_boot_id=_boot_id(), instance_id=_metadata("instance/id"))
    with socket.create_connection(("1.1.1.1", 443), timeout=3):
        pass
    document = {
        "version": "c23-host-positive-controls-v1",
        "purpose": PURPOSE,
        "target": target,
        "monotonic_ns": time.monotonic_ns(),
        "host_external_tcp_connect": True,
        "external_endpoint": {"address": "1.1.1.1", "port": 443},
        "metadata_read_positive": True,
        "untrusted_execution_performed": False,
        "qualification": "Trusted setup observation before egress removal; actual guest runs require separate current no-egress evidence",
    }
    _create(output, _canonical(document))
    return {
        "path": str(output),
        "sha256": _sha(_canonical(document)),
        "untrusted_execution_performed": False,
    }


def _control_output(path):
    path = Path(path)
    if path.parent != FIXED_ROOT / "evidence" or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,80}\.json", path.name
    ):
        raise OperatorError("operator_control_output_path")
    return path


def seal_network_isolation(arguments):
    """Seal root-supplied complete GCP reads on the target; no GCP commands."""
    require_worker()
    _control_output(arguments.output)
    sources = {}
    for name in (
        "instance_resource",
        "routers",
        "network_resource",
        "subnetwork_resource",
    ):
        path = getattr(arguments, name)
        raw = _read(path, MAX_FIXTURE)
        sources[name] = (json.loads(raw), _sha(raw))
    document = {
        "version": "c23-host-network-isolation-v1",
        "project": PROJECT,
        "instance": INSTANCE,
        "host_boot_id": _boot_id(),
        "observed_monotonic_ns": time.monotonic_ns(),
        "complete_router_inventory": True,
        **{name: value[0] for name, value in sources.items()},
        "source_sha256": {name: value[1] for name, value in sources.items()},
        "qualification": "Operator supplied complete current GCP reads; harness did not call cloud APIs",
        "snapshot_time_basis": "Worker seal time; API read recency and completeness remain trusted operator provenance",
    }
    _create(arguments.output, _canonical(document))
    return {"path": str(arguments.output), "sha256": _sha(_canonical(document))}


def validate_network_controls(
    host,
    isolated,
    target,
    *,
    instance_id,
    boot_id,
    interfaces,
    access_configs,
    external_ip,
    now_ns,
):
    """Validate retained trusted observations plus live metadata; no cloud API."""
    if any(type(value) is not dict for value in (host, isolated, target)):
        raise OperatorError("host_network_receipt_shape")
    if (
        host.get("version") != "c23-host-positive-controls-v1"
        or host.get("purpose") != PURPOSE
        or host.get("host_external_tcp_connect") is not True
        or host.get("metadata_read_positive") is not True
        or host.get("untrusted_execution_performed") is not False
        or host.get("external_endpoint") != {"address": "1.1.1.1", "port": 443}
        or type(host.get("monotonic_ns")) is not int
        or type(now_ns) is not int
        or not 0 <= now_ns - host["monotonic_ns"] <= 2 * 3600 * 10**9
    ):
        raise OperatorError("host_network_positive_control_invalid")
    expected_target = {**target, "host_boot_id": boot_id, "instance_id": instance_id}
    if (
        type(host.get("target")) is not dict
        or host["target"] != expected_target
        or set(host["target"]) != set(expected_target)
        or any(
            type(host["target"][key]) is not type(value)
            for key, value in expected_target.items()
        )
    ):
        raise OperatorError("host_network_positive_control_target")
    if (
        isolated.get("version") != "c23-host-network-isolation-v1"
        or isolated.get("project") != PROJECT
        or isolated.get("instance") != INSTANCE
        or isolated.get("host_boot_id") != boot_id
        or isolated.get("complete_router_inventory") is not True
        or type(isolated.get("routers")) is not list
        or type(isolated.get("observed_monotonic_ns")) is not int
        or not host["monotonic_ns"] <= isolated["observed_monotonic_ns"] <= now_ns
        or now_ns - isolated["observed_monotonic_ns"] > 1800 * 10**9
    ):
        raise OperatorError("host_network_isolation_receipt")
    resource = isolated.get("instance_resource", {})
    if type(resource) is not dict:
        raise OperatorError("host_instance_resource_shape")
    if (
        resource.get("name") != INSTANCE
        or str(resource.get("id")) != instance_id
        or resource.get("status") != "RUNNING"
        or type(resource.get("networkInterfaces")) is not list
        or len(resource["networkInterfaces"]) != 1
        or resource.get("zone")
        != GCP_API + "projects/" + PROJECT + "/zones/asia-northeast1-a"
        or interfaces != "0/"
        or type(access_configs) is not str
        or access_configs not in {"", "0/"}
        or type(external_ip) is not str
        or external_ip != ""
    ):
        raise OperatorError("host_external_ip_not_absent")
    networks = set()
    for nic in resource["networkInterfaces"]:
        if (
            type(nic) is not dict
            or type(nic.get("accessConfigs", [])) is not list
            or type(nic.get("ipv6AccessConfigs", [])) is not list
        ):
            raise OperatorError("host_network_interface_shape")
        if (
            nic.get("accessConfigs")
            or nic.get("ipv6AccessConfigs")
            or nic.get("ipv6AccessType") == "EXTERNAL"
            or type(nic.get("network")) is not str
            or nic["network"] != NETWORK
            or nic.get("subnetwork") != SUBNET
        ):
            raise OperatorError("host_external_ip_not_absent")
        networks.add(nic["network"])
    network = isolated.get("network_resource", {})
    subnet = isolated.get("subnetwork_resource", {})
    if (
        type(network) is not dict
        or type(subnet) is not dict
        or type(network.get("peerings", [])) is not list
    ):
        raise OperatorError("host_network_or_subnet_shape")
    if (
        network.get("selfLink") != NETWORK
        or network.get("name") != "c23-private"
        or network.get("peerings")
        or network.get("autoCreateSubnetworks") is not False
        or subnet.get("selfLink") != SUBNET
        or subnet.get("name") != "c23-tokyo"
        or subnet.get("network") != NETWORK
        or subnet.get("region")
        != GCP_API + "projects/" + PROJECT + "/regions/asia-northeast1"
    ):
        raise OperatorError("host_network_or_subnet_not_isolated")
    for router in isolated["routers"]:
        if (
            type(router) is not dict
            or type(router.get("network")) is not str
            or type(router.get("nats", [])) is not list
        ):
            raise OperatorError("host_router_inventory")
        if router["network"] in networks and router.get("nats"):
            raise OperatorError("host_cloud_nat_present")
    return {
        "host_external_tcp_positive_before_egress_removal": True,
        "current_metadata_external_ip_absent": True,
        "current_metadata_access_configs": access_configs,
        "current_metadata_terminal_external_ip": external_ip,
        "retained_router_inventory_no_nat": True,
        "host_boot_id": boot_id,
        "instance_id": instance_id,
        "qualification": "No-NAT is the target-bound complete trusted operator inventory snapshot; recency/completeness is operator provenance, the worker timestamp is sealing time. Live metadata rechecks only NIC0 and the exact terminal external-IP with verified HTTP200/Metadata-Flavor and empty body; a known empty config folder may remain. This is not continuous cloud-state attestation.",
    }


def _immutable_document(path, expected_sha):
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
        raise OperatorError("operator_control_receipt_hash")
    info = Path(path).lstat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o222:
        raise OperatorError("operator_control_receipt_not_immutable")
    raw = _read(path, MAX_FIXTURE)
    if _sha(raw) != expected_sha:
        raise OperatorError("operator_control_receipt_changed")
    return json.loads(raw)


@dataclass(frozen=True)
class OperatorCase:
    name: str
    body: str
    expectation: str = "completed"
    resources: dict | None = None
    outputs: tuple = (("summary.json", "table"),)
    seeds: dict | None = None


def cases():
    """Return stored guest programs. Nothing here evaluates or executes them."""
    definitions = [
        OperatorCase(
            "smoke",
            """
            import os, json
            assert os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []
            values = {}
            for line in open('/proc/self/status', encoding='ascii'):
                name, _, value = line.partition(':')
                if name in {'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}:
                    values[name] = int(value.strip(),16)
            assert len(values) == 5 and all(value == 0 for value in values.values())
            source = json.load(open('/inputs/' + INPUT_MACHINE, encoding='utf-8'))
            assert source['operator_int64_probe'] == [9223372036854775806, 9223372036854775807]
            write_summary([['uid',os.getuid()],['gid',os.getgid()],['capabilities_zero',True],
                           ['exact_int64',source['operator_int64_probe'][-1]]])
        """,
        ),
        OperatorCase(
            "containment",
            """
            import os, socket, importlib.util, subprocess
            interface_names = {name for _,name in socket.if_nameindex()}
            assert interface_names == {'lo'}
            ipv4_routes = open('/proc/net/route',encoding='ascii').read().splitlines()[1:]
            assert all(line.split()[0] == 'lo' for line in ipv4_routes if line.strip())
            try:
                ipv6_routes = open('/proc/net/ipv6_route',encoding='ascii').read().splitlines()
            except FileNotFoundError:
                ipv6_routes = None
            if ipv6_routes is not None:
                assert all(line.split()[-1] == 'lo' for line in ipv6_routes if line.strip())
            for address,port in [('1.1.1.1',443),('169.254.169.254',80)]:
                connection = socket.socket()
                connection.settimeout(1)
                try:
                    connection.connect((address,port))
                except OSError:
                    pass
                else:
                    raise AssertionError('network unexpectedly reachable: ' + address)
                finally:
                    connection.close()
            try:
                open(HOST_CANARY,'rb').read(1)
            except OSError:
                pass
            else:
                raise AssertionError('host canary readable')
            connection = socket.socket(socket.AF_UNIX)
            try:
                connection.connect(HOST_SOCKET)
            except OSError:
                pass
            else:
                raise AssertionError('host socket reachable')
            finally:
                connection.close()
            for path in ['/inputs/analysis.py','/inputs/new-file','/usr/local/c23-write',
                         '/tmp/c23-write','/dev/shm/c23-write','/run/c23-write','/var/tmp/c23-write']:
                try:
                    with open(path,'ab') as stream:
                        stream.write(b'no')
                except OSError:
                    pass
                else:
                    raise AssertionError('forbidden write succeeded: ' + path)
            assert importlib.util.find_spec('pip') is None
            assert importlib.util.find_spec('ensurepip') is None
            assert subprocess.run(['/usr/local/bin/python3','-m','pip','--version'],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3).returncode != 0
            try:
                os.readlink('/proc/1/fd/1')
            except OSError:
                pass
            else:
                raise AssertionError('trusted frame FD readable')
            mounts = open('/proc/self/mountinfo',encoding='utf-8').read()
            for path in ['/tmp','/dev/shm']:
                assert any(line.split()[4] == path and 'ro' in line.split()[5].split(',')
                           for line in mounts.splitlines())
            write_summary([['external_network_denied',True],['metadata_denied',True],
                           ['host_file_socket_denied',True],['forbidden_writes_denied',True],
                           ['pip_absent',True],['trusted_frame_fd_denied',True],
                           ['guest_interfaces',','.join(sorted(interface_names))],
                           ['ipv4_route_rows',len(ipv4_routes)],
                           ['ipv6_route_readback','present' if ipv6_routes is not None else 'not_exposed']])
        """,
        ),
        OperatorCase(
            "namespaces",
            """
            import ctypes, errno, os, signal, subprocess, threading
            assert os.uname().machine == 'x86_64'
            assert os.getuid() == 65532 and os.getgid() == 65532 and os.getgroups() == []
            capabilities = {}
            for line in open('/proc/self/status',encoding='ascii'):
                name, _, value = line.partition(':')
                if name in {'CapInh','CapPrm','CapEff','CapBnd','CapAmb'}:
                    capabilities[name] = int(value.strip(),16)
            assert len(capabilities) == 5 and all(value == 0 for value in capabilities.values())
            libc = ctypes.CDLL(None,use_errno=True)
            libc.syscall.restype = ctypes.c_long
            namespace_bits = [0x00020000,0x02000000,0x04000000,0x08000000,
                              0x10000000,0x20000000,0x40000000]
            observations = []
            def denied(name,number,*arguments,expected=errno.EPERM,clone_child=False):
                ctypes.set_errno(0)
                result = libc.syscall(ctypes.c_long(number),*arguments)
                actual_errno = ctypes.get_errno()
                if clone_child and result == 0:
                    # An unexpected clone child must not continue any probe.
                    os._exit(0)
                if clone_child and result > 0:
                    os.waitpid(result,0)
                assert result == -1 and actual_errno == expected, (name,result,actual_errno,expected)
                observations.append([name,actual_errno])
            # AMD64 Linux syscall numbers; no host syscall is issued by setup.
            # unshare(0) and setns(-1) errno distinguish early deny from ordinary
            # success/FD validation; neither invalid clone3 input proves userns alone.
            for bit in [0,*namespace_bits,0x80]:
                denied('unshare_' + hex(bit),272,ctypes.c_ulong(bit))
            denied('setns_invalid_fd',308,ctypes.c_long(-1),ctypes.c_ulong(0))
            for bit in namespace_bits:
                denied('clone_' + hex(bit),56,ctypes.c_ulong(bit|signal.SIGCHLD),
                       ctypes.c_void_p(0),ctypes.c_void_p(0),ctypes.c_void_p(0),
                       ctypes.c_ulong(0),clone_child=True)
            clone_args = (ctypes.c_uint64*11)()
            clone_args[0] = 0x10000000
            clone_args[4] = signal.SIGCHLD
            denied('clone3_newuser',435,ctypes.byref(clone_args),
                   ctypes.c_size_t(ctypes.sizeof(clone_args)),expected=errno.ENOSYS,clone_child=True)
            denied('clone3_invalid_pointer',435,ctypes.c_void_p(1),
                   ctypes.c_size_t(ctypes.sizeof(clone_args)),expected=errno.ENOSYS,clone_child=True)
            denied('clone3_zero_size',435,ctypes.c_void_p(0),ctypes.c_size_t(0),
                   expected=errno.ENOSYS,clone_child=True)
            os.mkdir('/scratch/ns-probe')
            target = ctypes.c_char_p(b'/scratch/ns-probe')
            denied('mount_tmpfs',165,ctypes.c_char_p(b'tmpfs'),target,
                   ctypes.c_char_p(b'tmpfs'),ctypes.c_ulong(0),
                   ctypes.c_char_p(b'size=4096,nr_inodes=4'))
            denied('mount_bind',165,ctypes.c_char_p(b'/inputs'),target,
                   ctypes.c_void_p(0),ctypes.c_ulong(4096),ctypes.c_void_p(0))
            denied('mount_remount',165,ctypes.c_void_p(0),ctypes.c_char_p(b'/scratch'),
                   ctypes.c_void_p(0),ctypes.c_ulong(32|1),ctypes.c_void_p(0))
            denied('umount2',166,ctypes.c_char_p(b'/scratch'),ctypes.c_int(0))
            os.rmdir('/scratch/ns-probe')
            # Compatibility controls are deliberately after all risky clone calls
            # so those calls run before this program creates any Python thread.
            pid = os.fork()
            if pid == 0:
                os._exit(0)
            waited,status = os.waitpid(pid,0)
            assert waited == pid and os.waitstatus_to_exitcode(status) == 0
            process = subprocess.run(['/usr/local/bin/python3','-I','-S','-B','-c',
                'print("ordinary-child-ok")'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3)
            assert process.returncode == 0 and process.stdout == b'ordinary-child-ok\\n'
            threaded = []
            worker = threading.Thread(target=lambda: threaded.append('ordinary-thread-ok'))
            worker.start()
            worker.join(timeout=3)
            assert not worker.is_alive() and threaded == ['ordinary-thread-ok']
            write_summary(observations + [['uid',os.getuid()],['capabilities_zero',True],
                ['ordinary_fork',True],['ordinary_subprocess',True],['ordinary_thread',True]])
        """,
        ),
        OperatorCase(
            "descendants",
            """
            import os,time
            reader,writer = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(reader)
                os.setsid()
                grandchild = os.fork()
                if grandchild:
                    os._exit(0)
                os.write(writer,b'D')
                os.close(writer)
                while True:
                    time.sleep(0.05)
            os.close(writer)
            assert os.read(reader,1) == b'D'
            os.close(reader)
            write_summary([['double_fork_descendant_started',True],['first_child_pid',pid]])
        """,
        ),
        OperatorCase(
            "cancel",
            "import time\nwhile True: time.sleep(0.05)\n",
            expectation="cancelled",
            resources={"wall_seconds": 30},
        ),
        OperatorCase(
            "wall",
            "import time\nwhile True: time.sleep(0.05)\n",
            expectation="timed_out",
            resources={"wall_seconds": 10},
        ),
        OperatorCase(
            "memory",
            """
            import time
            values = []
            for _ in range(1024):
                value = bytearray(1024*1024)
                for offset in range(0,len(value),4096): value[offset] = 1
                values.append(value)
            raise AssertionError('memory limit not enforced')
        """,
            expectation="memory_bound",
            resources={"memory_bytes": 256 * 1024**2, "wall_seconds": 30},
        ),
        OperatorCase(
            "processes",
            """
            import os,time,errno
            count = 0
            denied = False
            for _ in range(160):
                try:
                    pid = os.fork()
                except OSError as error:
                    assert error.errno == errno.EAGAIN
                    denied = True
                    break
                if pid == 0:
                    time.sleep(25)
                    os._exit(0)
                count += 1
            assert denied and 1 <= count <= 126
            write_summary([['forks_before_EAGAIN',count],['guest_task_bound',128]])
        """,
        ),
        OperatorCase(
            "output-bytes",
            """
            import os,errno
            paths = ['/outputs/.fill-a','/outputs/.fill-b']
            streams = [open(path,'wb',buffering=0) for path in paths]
            denied = False
            written = 0
            try:
                for index in range(64):
                    try:
                        written += streams[index%2].write(b'X'*4096)
                    except OSError as error:
                        assert error.errno == errno.ENOSPC
                        denied = True
                        break
            finally:
                for stream in streams: stream.close()
                for path in paths: os.unlink(path)
            assert denied
            write_summary([['aggregate_output_ENOSPC',True],['written_bytes',written]])
        """,
            resources={"max_output_bytes": 65536},
        ),
        OperatorCase(
            "scratch-bytes",
            """
            import os,errno
            paths = ['/scratch/fill-' + str(i) for i in range(8)]
            streams = [open(path,'wb',buffering=0) for path in paths]
            denied = False
            written = 0
            try:
                for index in range(300):
                    try:
                        written += streams[index%8].write(b'X'*(512*1024))
                    except OSError as error:
                        assert error.errno == errno.ENOSPC
                        denied = True
                        break
            finally:
                for stream in streams: stream.close()
                for path in paths: os.unlink(path)
            assert denied
            write_summary([['scratch_ENOSPC',True],['written_bytes',written]])
        """,
            resources={"memory_bytes": 512 * 1024**2},
        ),
        OperatorCase(
            "output-inodes",
            """
            import os,errno
            names = []
            denied = False
            for index in range(520):
                name = '/outputs/.inode-' + str(index)
                try:
                    with open(name,'xb'): pass
                except OSError as error:
                    assert error.errno == errno.ENOSPC
                    denied = True
                    break
                names.append(name)
            for name in names: os.unlink(name)
            assert denied and 1 <= len(names) <= 511
            write_summary([['output_inode_ENOSPC',True],['files_created',len(names)]])
        """,
        ),
        OperatorCase(
            "scratch-inodes",
            """
            import os,errno
            names = []
            denied = False
            for index in range(4100):
                name = '/scratch/.inode-' + str(index)
                try:
                    with open(name,'xb'): pass
                except OSError as error:
                    assert error.errno == errno.ENOSPC
                    denied = True
                    break
                names.append(name)
            for name in names: os.unlink(name)
            assert denied and 1 <= len(names) <= 4095
            write_summary([['scratch_inode_ENOSPC',True],['files_created',len(names)]])
        """,
        ),
        OperatorCase(
            "logs",
            "import os\nfor _ in range(40): os.write(1,b'X'*65536)\n",
            expectation="log_bound",
        ),
        OperatorCase(
            "unsafe-symlink",
            "import os\nos.symlink('/inputs/analysis.py','summary.json')\n",
            expectation="unsafe_output",
        ),
        OperatorCase(
            "unsafe-hardlink",
            "import os\nwrite_summary([['synthetic',1]])\nos.link('summary.json','alias.json')\n",
            expectation="unsafe_output",
            outputs=(("alias.json", "table"), ("summary.json", "table")),
        ),
        OperatorCase(
            "unsafe-fifo",
            "import os\nos.mkfifo('summary.json')\n",
            expectation="unsafe_output",
        ),
        OperatorCase(
            "traversal",
            """
            for path in ['../outside.json','/inputs/escaped.json','/usr/local/escaped.json']:
                try:
                    with open(path,'w') as stream: stream.write('unexpected')
                except OSError:
                    pass
                else:
                    raise AssertionError('traversal write escaped outputs/scratch')
            write_summary([['outside_write_denied',True]])
        """,
        ),
        OperatorCase(
            "cpu",
            """
            import os,time
            children = []
            for _ in range(4):
                pid = os.fork()
                if pid == 0:
                    end = time.monotonic()+3
                    value = 1
                    while time.monotonic()<end: value = (value*3+1)%1000000007
                    os._exit(0)
                children.append(pid)
            for pid in children: assert os.waitpid(pid,0)[1] == 0
            write_summary([['competing_cpu_workers',len(children)]])
        """,
            expectation="cpu_bound",
            resources={"cpus": 1},
        ),
        OperatorCase(
            "raster",
            """
            import numpy as np
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            from PIL import Image
            figure = Figure(figsize=(2,2),dpi=32)
            canvas = FigureCanvasAgg(figure)
            figure.add_subplot(111).plot([0,1,2],[0,1,0])
            canvas.draw()
            image = Image.fromarray(np.asarray(canvas.buffer_rgba()))
            image.save('plot.png',format='PNG',compress_level=9)
            write_summary([['width',image.width],['height',image.height]])
        """,
            outputs=(("plot.png", "raster"), ("summary.json", "table")),
        ),
    ]
    numeric = """
        import json,math
        import numpy as np
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
        import scipy.stats as stats
        import statsmodels.api as sm
        exact = json.load(open('/inputs/'+INPUT_MACHINE))['operator_int64_probe']
        frame = pd.DataFrame({'exact':np.asarray(exact,dtype=np.int64)})
        pq.write_table(pa.Table.from_pandas(frame,preserve_index=False),'/scratch/exact.parquet')
        restored = pq.read_table('/scratch/exact.parquet').column('exact').to_pylist()
        assert restored == exact and restored[-1] == 9223372036854775807
        rng = np.random.default_rng(20261024)
        values = rng.normal(size=32)
        test = stats.ttest_1samp(values,0.0)
        fit = sm.OLS(np.array([1.,3.,5.,7.]),sm.add_constant(np.arange(4,dtype=float))).fit()
        assert math.isclose(float(fit.params[0]),1.,rel_tol=1e-10,abs_tol=1e-10)
        assert math.isclose(float(fit.params[1]),2.,rel_tol=1e-10,abs_tol=1e-10)
        assert all(math.isfinite(float(value)) for value in [values.mean(),test.statistic,test.pvalue])
        write_summary([['mean',float(values.mean())],['t_statistic',float(test.statistic)],
                       ['p_value',float(test.pvalue)],['ols_intercept',float(fit.params[0])],
                       ['ols_slope',float(fit.params[1])],['exact_int64',restored[-1]]])
    """
    for name in ("numerics-a", "numerics-b"):
        definitions.append(OperatorCase(name, numeric, seeds={"numpy": 20261024}))
    return {case.name: case for case in definitions}


def load_blueprint(path):
    document = json.loads(_read(path, MAX_FIXTURE))
    if (
        type(document) is not dict
        or document.get("version") != VERSION
        or document.get("purpose") != PURPOSE
        or document.get("retained_C22_real_approval") is not False
        or document.get("real_C22_reservation_consumption_verified") is not False
    ):
        raise OperatorError("operator_blueprint_authority")
    from orchestration.experiment_sandbox.contracts import verify_execution_envelope

    metadata = document["metadata"]
    files = {
        name: base64.b64decode(raw, validate=True)
        for name, raw in document["files_base64"].items()
    }
    environment = metadata["environment"]
    if environment["kind"] != "c22-fake" or environment["test_only"] is not True:
        raise OperatorError("operator_blueprint_not_fake_source")
    verify_execution_envelope(
        {"metadata": metadata, "files": files},
        expected_envelope_sha256=document["source_fake_envelope_sha256"],
        environments={metadata["proposal"]["environment_id"]: environment},
    )
    return document


def make_operator_fixture(
    blueprint, image_receipt, case_name, nonce, *, host_canary, host_socket
):
    """Derive explicitly non-C22 operator bytes; hashes are structural only."""
    from orchestration.experiment_sandbox.profile import ImagePreparation
    from schema.research_experiments import (
        EnvironmentDescriptor,
        ExperimentResources,
        content_sha256,
    )

    if (
        case_name not in cases()
        or type(nonce) is not str
        or not re.fullmatch(r"[a-f0-9]{32}", nonce)
    ):
        raise OperatorError("operator_case_identity")
    if (
        blueprint.get("purpose") != PURPOSE
        or blueprint.get("retained_C22_real_approval") is not False
    ):
        raise OperatorError("operator_blueprint_authority")
    image = ImagePreparation.model_validate(image_receipt)
    environment = EnvironmentDescriptor(
        kind="linux-gvisor",
        test_only=False,
        python_version=image.python_version,
        image_digest=image.image_digest,
        lockfile_sha256=image.lockfile_sha256,
        packages=image.packages,
        description="Actual pinned scientific image for operator-owned synthetic acceptance; no real C22 approval",
    )
    case = cases()[case_name]
    metadata = deepcopy(blueprint["metadata"])
    files = {
        name: base64.b64decode(raw, validate=True)
        for name, raw in blueprint["files_base64"].items()
    }
    machine = next(
        item
        for item in metadata["manifest"]["files"]
        if item["kind"] == "machine_table"
    )
    body = json.loads(files[machine["name"]])
    body["operator_int64_probe"] = [9223372036854775806, 9223372036854775807]
    files[machine["name"]] = _canonical(body)
    machine.update(
        sha256=_sha(files[machine["name"]]), size_bytes=len(files[machine["name"]])
    )
    prefix = (
        f"# Operator-owned synthetic acceptance: {case_name}; nonce={nonce}\n"
        f"INPUT_MACHINE={machine['name']!r}\nHOST_CANARY={str(host_canary)!r}\nHOST_SOCKET={str(host_socket)!r}\n"
        'def write_summary(rows):\n import json\n with open("summary.json","w",encoding="utf-8") as stream:\n'
        '  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))\n'
    )
    code = prefix + textwrap.dedent(case.body).strip() + "\n"
    ast.parse(code)
    for key in (
        "experiment_id",
        "proposal_revision_id",
        "reservation_id",
        "approval_id",
    ):
        metadata[key] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"c23-operator:{nonce}:{case_name}:{key}")
        )
    metadata["site_id"] = "v1:c23-operator-synthetic"
    proposal = metadata["proposal"]
    proposal.update(
        question="Operator-owned synthetic acceptance: " + case_name,
        python_code=code,
        environment_id=environment.identity_sha256,
        assumptions=[
            "Generated synthetic fixture only; retained_C22_real_approval=false"
        ],
        limitations=[
            "No production dispatch, real C22 reservation consumption or scientific approval"
        ],
        seeds=case.seeds or {},
        resources=ExperimentResources.model_validate(
            {**proposal["resources"], "wall_seconds": 60, **(case.resources or {})}
        ).model_dump(mode="json"),
        expected_outputs=[
            {
                "name": name,
                "kind": kind,
                "description": "Operator synthetic acceptance output",
            }
            for name, kind in case.outputs
        ],
    )
    metadata["environment"] = environment.model_dump(mode="json")
    metadata["manifest"].update(
        question=proposal["question"],
        proposal_sha256=content_sha256(proposal),
        max_input_bytes=proposal["resources"]["max_input_bytes"],
    )
    metadata["hashes"] = {
        "proposal_sha256": content_sha256(proposal),
        "code_sha256": _sha(code.encode()),
        "input_manifest_sha256": content_sha256(metadata["manifest"]),
        "environment_sha256": environment.identity_sha256,
        "resources_sha256": content_sha256(proposal["resources"]),
    }
    wrapper = {
        "version": VERSION,
        "purpose": PURPOSE,
        "retained_C22_real_approval": False,
        "real_C22_reservation_consumption_verified": False,
        "case": case_name,
        "nonce": nonce,
        "source_fake_envelope_sha256": blueprint["source_fake_envelope_sha256"],
        "operator_envelope_sha256": content_sha256(metadata),
        "metadata": metadata,
        "environment_registry": {
            environment.identity_sha256: environment.model_dump(mode="json")
        },
        "image_preparation_sha256": content_sha256(image.model_dump(mode="json")),
        "files_base64": {
            name: base64.b64encode(raw).decode("ascii")
            for name, raw in sorted(files.items())
        },
    }
    verify_operator_fixture(wrapper)
    return wrapper


def verify_operator_fixture(wrapper):
    """Pure structural checks under an operator wrapper, NEVER real C22 admission."""
    from orchestration.experiment_sandbox.contracts import verify_execution_envelope

    if (
        type(wrapper) is not dict
        or wrapper.get("version") != VERSION
        or wrapper.get("purpose") != PURPOSE
        or wrapper.get("retained_C22_real_approval") is not False
        or wrapper.get("real_C22_reservation_consumption_verified") is not False
        or wrapper.get("case") not in cases()
    ):
        raise OperatorError("operator_fixture_authority")
    files = {
        name: base64.b64decode(raw, validate=True)
        for name, raw in wrapper["files_base64"].items()
    }
    return verify_execution_envelope(
        {"metadata": wrapper["metadata"], "files": files},
        expected_envelope_sha256=wrapper["operator_envelope_sha256"],
        environments=wrapper["environment_registry"],
    )


def _hash_file(path, maximum=8 * 1024**3):
    before = Path(path).lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 0 <= before.st_size <= maximum
    ):
        raise OperatorError("material_file_integrity")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        digest, size = hashlib.sha256(), 0
        while True:
            raw = os.read(fd, 1024**2)
            if not raw:
                break
            size += len(raw)
            if size > before.st_size:
                raise OperatorError("material_file_changed")
            digest.update(raw)
        after = os.fstat(fd)
        current = Path(path).lstat()

        def stamp(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_nlink,
                info.st_size,
                info.st_uid,
                info.st_gid,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        if (
            size != before.st_size
            or stamp(before) != stamp(after)
            or stamp(before) != stamp(current)
        ):
            raise OperatorError("material_file_changed")
        return digest.hexdigest()
    finally:
        os.close(fd)


def verify_rootfs_normalization(rootfs, receipt_path, receipt_sha256):
    """Require explicit provenance for the separate hardlink-normalized copy.

    The OCI digest still names the original image; this operator transformation
    changes hardlink topology and is independently bound to its copied bytes.
    Trusted build/unpack provenance remains an operator responsibility.
    """
    from sandbox.experiment.gcp.normalize_rootfs import verify_normalization_receipt

    destination = Path(rootfs)
    match = re.fullmatch(
        r"scientific-normalized-(quota-v[3-9][0-9]*)", destination.parent.name
    )
    if (
        match is None
        or destination.name != "rootfs"
        or destination.parent.parent != FIXED_ROOT
    ):
        raise OperatorError("operator_normalized_rootfs_path")
    label = match[1]
    source = FIXED_ROOT / ("scientific-bundle-" + label) / "rootfs"
    expected_receipt = (
        FIXED_ROOT / "evidence" / ("rootfs-normalization-" + label + ".json")
    )
    if Path(receipt_path) != expected_receipt or Path(receipt_path) != Path(
        receipt_path
    ).resolve(strict=True):
        raise OperatorError("operator_normalization_receipt_path")
    document = _immutable_document(receipt_path, receipt_sha256)
    provenance = verify_normalization_receipt(
        document, source=source, destination=destination
    )
    return {"receipt_sha256": receipt_sha256, "provenance": provenance}


def verify_materials(
    rootfs,
    oci_layout,
    image_receipt,
    runtime_manifest,
    *,
    normalization_receipt,
    normalization_sha256,
):
    """Bind actual OCI blob bytes and materialized rootfs; perform no extraction."""
    from orchestration.experiment_sandbox.profile import (
        ImagePreparation,
        RuntimePreparation,
        rootfs_inventory_sha256,
    )

    image = ImagePreparation.model_validate(image_receipt).model_dump(mode="json")
    runtime = RuntimePreparation.model_validate(runtime_manifest).model_dump(
        mode="json"
    )
    if (
        runtime["input_host_uid"] != APP_UID
        or runtime["input_host_gid"] != APP_GID
        or runtime["architecture"] != "amd64"
        or image["architecture"] != "amd64"
    ):
        raise OperatorError("operator_owner_or_architecture")
    for value in (Path(rootfs), Path(oci_layout)):
        if (
            not value.is_absolute()
            or value != value.resolve(strict=True)
            or not value.is_relative_to(FIXED_ROOT)
            or not stat.S_ISDIR(value.lstat().st_mode)
            or value.lstat().st_uid != os.geteuid()
        ):
            raise OperatorError("operator_material_path")
    if rootfs_inventory_sha256(rootfs) != image["rootfs_inventory_sha256"]:
        raise OperatorError("materialized_rootfs_hash")
    normalization = verify_rootfs_normalization(
        rootfs, normalization_receipt, normalization_sha256
    )
    if (
        normalization["provenance"]["destination_rootfs_inventory_sha256"]
        != image["rootfs_inventory_sha256"]
    ):
        raise OperatorError("operator_normalization_inventory_binding")
    layout = json.loads(_read(Path(oci_layout) / "oci-layout", 4096))
    index = json.loads(_read(Path(oci_layout) / "index.json", 1024**2))
    if layout != {"imageLayoutVersion": "1.0.0"} or not any(
        entry.get("digest") == image["image_digest"]
        for entry in index.get("manifests", [])
    ):
        raise OperatorError("oci_image_identity")

    def blob(digest, maximum):
        if type(digest) is not str or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise OperatorError("oci_blob_identity")
        path = Path(oci_layout) / "blobs" / "sha256" / digest.split(":")[1]
        if _hash_file(path, maximum) != digest.split(":")[1]:
            raise OperatorError("oci_blob_checksum")
        return path

    manifest = json.loads(_read(blob(image["image_digest"], 1024**2), 1024**2))
    if (
        manifest["config"]["digest"] != "sha256:" + image["oci_config_sha256"]
        or [entry["digest"].split(":")[-1] for entry in manifest["layers"]]
        != image["layer_sha256"]
    ):
        raise OperatorError("oci_manifest_binding")
    config = json.loads(_read(blob(manifest["config"]["digest"], 1024**2), 1024**2))
    if config.get("architecture") != "amd64" or config.get("os") != "linux":
        raise OperatorError("oci_config_platform")
    for entry in manifest["layers"]:
        blob(entry["digest"], 8 * 1024**3)
    normalization["source_oci_manifest_digest"] = image["image_digest"]
    return {
        "image_preparation": image,
        "runtime_preparation": runtime,
        "oci_layers_verified": len(manifest["layers"]),
        "materialized_rootfs_inventory_sha256": image["rootfs_inventory_sha256"],
        "rootfs_normalization": normalization,
        "materialization_qualification": "Original OCI image plus explicit content/mode/owner-preserving hardlink normalization; copied topology differs and rootfs provenance relies on trusted build/unpack observations.",
    }


def _private_directory(path, *, create=False):
    path = Path(path)
    if create:
        path.mkdir(mode=0o700)
    if (
        not path.is_absolute()
        or path != path.resolve(strict=True)
        or not stat.S_ISDIR(path.lstat().st_mode)
        or path.lstat().st_uid != os.geteuid()
        or stat.S_IMODE(path.lstat().st_mode) != 0o700
    ):
        raise OperatorError("operator_private_directory")
    return path


def check_attempt_path(path):
    path = Path(path)
    if (
        not path.is_absolute()
        or path.parent != ATTEMPTS_ROOT
        or not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", path.name)
        or len(str(path).encode()) > 95
    ):
        raise OperatorError("operator_attempt_path")
    return path


def _kernel_read(path, maximum=65536):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OperatorError("operator_cgroup_file")
        raw = bytearray()
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > maximum:
            raise OperatorError("operator_cgroup_limit")
        return bytes(raw)
    finally:
        os.close(fd)


def _kernel_write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.write(fd, raw) != len(raw):
            raise OperatorError("operator_cgroup_file")
    finally:
        os.close(fd)


def _cgroup_identity(journal, envelope):
    snapshot = journal.read(envelope.job_id, envelope.envelope_sha256)
    if snapshot is None:
        return None
    for item in reversed(snapshot.events):
        if item.kind == "create_intent" and "cgroup_identity" in item.payload:
            value = item.payload["cgroup_identity"]
            if (
                type(value) is list
                and len(value) == 2
                and all(type(number) is int and number >= 0 for number in value)
            ):
                return tuple(value)
    return None


_CGROUP_REQUIRED_COUNTERS = {
    "cpu.stat": {
        "usage_usec",
        "user_usec",
        "system_usec",
        "nr_periods",
        "nr_throttled",
        "throttled_usec",
    },
    "memory.events": {"low", "high", "max", "oom", "oom_kill"},
    "pids.events": {"max"},
    "cgroup.events": {"populated", "frozen"},
}


def _parse_cgroup_counters(raw, name):
    """Retain evolving kernel counter names without accepting malformed rows."""
    fields = {}
    for line in raw.decode("ascii").splitlines():
        parts = line.split()
        if len(parts) != 2:
            raise OperatorError("operator_cgroup_measurement")
        key, value = parts
        if (
            key in fields
            or len(fields) >= 128
            or len(key) > 128
            or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", key)
            or not re.fullmatch(r"[0-9]{1,20}", value)
            or int(value) > 2**64 - 1
        ):
            raise OperatorError("operator_cgroup_measurement")
        fields[key] = int(value)
    if not _CGROUP_REQUIRED_COUNTERS[name] <= fields.keys():
        raise OperatorError("operator_cgroup_measurement_missing_required")
    return fields


def _collect_metrics(journal, envelope, *, observation_dir=None):
    outer = Path("/sys/fs/cgroup/ocean-c23") / envelope.job_id
    identity = _cgroup_identity(journal, envelope)
    if identity is None or not outer.exists():
        return {"available": False, "reason": "no_retained_owned_cgroup"}
    info = outer.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or outer != outer.resolve(strict=True)
        or (info.st_dev, info.st_ino) != identity
    ):
        raise OperatorError("operator_cgroup_identity")
    result = {"available": True, "device": identity[0], "inode": identity[1]}
    result["raw_cgroup_files"] = {}
    for name in (*_CGROUP_REQUIRED_COUNTERS, "memory.peak"):
        raw = _kernel_read(outer / name)
        # Preserve actual readback before interpretation, including failed parses.
        if observation_dir is not None:
            _create(Path(observation_dir) / ("cgroup-" + name + ".raw.txt"), raw)
        result["raw_cgroup_files"][name] = raw.decode("ascii")
        if name == "memory.peak":
            value = raw.decode("ascii").strip()
            if not re.fullmatch(r"[0-9]{1,20}", value) or int(value) > 2**64 - 1:
                raise OperatorError("operator_cgroup_measurement")
            result[name] = int(value)
        else:
            result[name] = _parse_cgroup_counters(raw, name)
    return result


def _remove_empty_cgroups(outer):
    discovered = []

    def walk(path, depth):
        if depth > 16:
            raise OperatorError("operator_cgroup_depth")
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    if len(discovered) >= 128:
                        raise OperatorError("operator_cgroup_count")
                    child = path / entry.name
                    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", entry.name):
                        raise OperatorError("operator_cgroup_name")
                    discovered.append(str(child))
                    walk(child, depth + 1)
        path.rmdir()

    walk(outer, 0)
    return discovered + [str(outer)]


@dataclass
class MountIntent:
    source: Path
    target: Path
    source_identity: tuple[int, int] | None = None
    target_identity_before: tuple[int, int] | None = None
    prechecked_absent: bool = False
    attempted: bool = False


def _directory_identity(path):
    info = Path(path).lstat()
    if not stat.S_ISDIR(info.st_mode) or Path(path) != Path(path).resolve(strict=True):
        raise OperatorError("operator_mount_directory")
    return info.st_dev, info.st_ino


def _mount_entry(target):
    """Observe the kernel mount table, including mounts whose command ack was lost."""

    def decode(value):
        return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)

    entries = []
    for line in _kernel_read("/proc/self/mountinfo", 1024**2).decode().splitlines():
        fields = line.split()
        if len(fields) < 10 or "-" not in fields[6:]:
            raise OperatorError("operator_mountinfo_malformed")
        if decode(fields[4]) == str(target):
            entries.append({"mount_id": fields[0], "options": fields[5], "line": line})
    if len(entries) > 1:
        raise OperatorError("operator_mountinfo_stacked")
    return entries[0] if entries else None


def _mount_observation(intent):
    entry = _mount_entry(intent.target)
    return {
        "entry": entry,
        "target_identity": list(_directory_identity(intent.target)),
        "source_identity": list(_directory_identity(intent.source)),
    }


def _perform_mount(intent, attempt):
    # The caller retains this intent even if precheck, command, or log retention fails.
    before = _mount_observation(intent)
    if before["entry"] is not None:
        raise OperatorError("operator_mount_target_preexisting")
    intent.source_identity = tuple(before["source_identity"])
    intent.target_identity_before = tuple(before["target_identity"])
    intent.prechecked_absent = True
    _create(attempt / "mount-intent.json", _canonical(before))
    commands = [
        [
            "/usr/bin/mount",
            "--internal-only",
            "--bind",
            str(intent.source),
            str(intent.target),
        ],
        [
            "/usr/bin/mount",
            "--internal-only",
            "-o",
            "remount,bind,ro,nosuid,nodev",
            str(intent.target),
        ],
    ]
    for index, command in enumerate(commands):
        _create(attempt / f"mount-{index}.intent.json", _canonical({"argv": command}))
        # Uncertainty starts before invocation, not after a successful return or write.
        intent.attempted = True
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10
        )
        _create(attempt / f"mount-{index}.stdout.bin", process.stdout)
        _create(attempt / f"mount-{index}.stderr.bin", process.stderr)
        if process.returncode != 0:
            raise OperatorError("operator_rootfs_bind_failed")
        observed = _mount_observation(intent)
        _create(attempt / f"mount-{index}.observation.json", _canonical(observed))
        if (
            observed["entry"] is None
            or tuple(observed["source_identity"]) != intent.source_identity
            or tuple(observed["target_identity"]) != intent.source_identity
        ):
            raise OperatorError("operator_rootfs_mount_identity")
    if not os.statvfs(intent.target).f_flag & os.ST_RDONLY:
        raise OperatorError("operator_rootfs_not_readonly")


def _unmount_reconciled(intent, lease):
    """A command result alone never proves that a bind mount is absent."""
    if intent is None:
        return {"rootfs_unmounted": True, "reason": "no_mount_effect_attempted"}
    lease.require_current()
    before = _mount_observation(intent)
    record = {"before": before, "rootfs_unmounted": False}
    if before["entry"] is None:
        if intent.prechecked_absent and (
            tuple(before["target_identity"]) != intent.target_identity_before
            or tuple(before["source_identity"]) != intent.source_identity
        ):
            raise OperatorError("operator_rootfs_absence_identity")
        record["rootfs_unmounted"] = True
        return record
    if (
        not intent.prechecked_absent
        or not intent.attempted
        or tuple(before["source_identity"]) != intent.source_identity
        or tuple(before["target_identity"]) != intent.source_identity
    ):
        raise OperatorError("operator_rootfs_unmount_identity_unverified")
    lease.require_current()
    command = ["/usr/bin/umount", "--internal-only", "--", str(intent.target)]
    record["argv"] = command
    try:
        # subprocess.run kills/waits its direct child on TimeoutExpired. Fixed
        # internal-only commands exclude filesystem-helper delegation; this is
        # not a generic guarantee about arbitrary subprocess descendants.
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10
        )
        record["exit_code"] = process.returncode
        record["stdout_base64"] = base64.b64encode(process.stdout).decode()
        record["stderr_base64"] = base64.b64encode(process.stderr).decode()
    except (OSError, subprocess.TimeoutExpired) as error:
        record["command_ack_error"] = type(error).__name__
    lease.require_current()
    after = _mount_observation(intent)
    record["after"] = after
    if (
        after["entry"] is not None
        or tuple(after["target_identity"]) != intent.target_identity_before
        or tuple(after["source_identity"]) != intent.source_identity
    ):
        raise OperatorError("operator_rootfs_unmount_unverified")
    record["rootfs_unmounted"] = True
    return record


def _cleanup(journal, envelope, mount_intent):
    """Operator cleanup only, with a fresh physical-effect lock and no release."""
    record = {
        "reservation_released": False,
        "rootfs_unmounted": False,
        "cgroup_empty": None,
    }
    with journal.claim(envelope.job_id, envelope.envelope_sha256) as lease:
        outer = Path("/sys/fs/cgroup/ocean-c23") / envelope.job_id
        if outer.exists():
            identity = _cgroup_identity(journal, envelope)
            info = outer.lstat()
            if (
                identity is None
                or (info.st_dev, info.st_ino) != identity
                or outer != outer.resolve(strict=True)
            ):
                raise OperatorError("operator_cleanup_identity_unverified")
            lease.require_current()
            _kernel_write(outer / "cgroup.kill", b"1\n")
            deadline = time.monotonic() + 3
            while True:
                lease.require_current()
                fields = dict(
                    line.split()
                    for line in _kernel_read(outer / "cgroup.events")
                    .decode()
                    .splitlines()
                )
                if fields.get("populated") == "0":
                    break
                if fields.get("populated") != "1" or time.monotonic() >= deadline:
                    raise OperatorError("operator_cleanup_population_unverified")
                time.sleep(0.01)
            record["cgroup_empty"] = True
        else:
            record["cgroup_empty"] = "no_cgroup_exists"
        record["mount_reconciliation"] = _unmount_reconciled(mount_intent, lease)
        record["rootfs_unmounted"] = record["mount_reconciliation"]["rootfs_unmounted"]
        if outer.exists():
            lease.require_current()
            record["removed_cgroups"] = _remove_empty_cgroups(outer)
    return record


def _positive_controls(attempt):
    canary = attempt / "host-canary.txt"
    value = b"c23-synthetic-host-canary:" + uuid.uuid4().hex.encode()
    _create(canary, value)
    if _read(canary, 4096) != value:
        raise OperatorError("host_canary_positive_control")
    listener = socket.socket(socket.AF_UNIX)
    listener.settimeout(3)
    endpoint = attempt / "host.sock"
    try:
        listener.bind(str(endpoint))
        listener.listen(1)
        client = socket.socket(socket.AF_UNIX)
        try:
            client.settimeout(3)
            client.connect(str(endpoint))
            accepted, _ = listener.accept()
            accepted.close()
        finally:
            client.close()
        return listener, {
            "host_file_read": True,
            "host_socket_connect": True,
            "metadata_guard_positive_control": True,
            "canary_sha256": _sha(value),
            "canary_path": str(canary),
            "socket_path": str(endpoint),
        }
    except BaseException:
        listener.close()
        raise


def _admission(path, expected_sha, envelope):
    info = path.lstat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o222:
        raise OperatorError("operator_fixture_not_immutable")
    raw = _read(path, MAX_FIXTURE)
    if _sha(raw) != expected_sha:
        raise OperatorError("operator_fixture_changed")
    current = verify_operator_fixture(json.loads(raw))
    if (
        current.job_id != envelope.job_id
        or current.envelope_sha256 != envelope.envelope_sha256
    ):
        raise OperatorError("operator_fixture_changed")
    return current.envelope_sha256


def evaluate_case(case_name, document, metrics, cleanup, *, elapsed):
    """Interpret actual observations; pure helper tests are not execution proof."""
    case = cases()[case_name]
    proof = document.get("termination_proof") or {}
    checks = {
        "no_dispatch_or_release": document.get("dispatch_eligible") is False
        and document.get("reservation_released") is False,
        "scientific_unverified": document.get("scientific_approval")
        == "not_independently_verified",
        "execution_started": document.get("execution_started") is True,
        "whole_host_subtree_empty": proof.get("whole_host_subtree_empty") is True
        and proof.get("populated") == 0,
        "delete_acknowledged": proof.get("runtime_delete_acknowledged") is True,
        "rootfs_cleanup": cleanup.get("rootfs_unmounted") is True,
    }
    state, reason = document.get("state"), document.get("reason")
    if case.expectation in {"completed", "cpu_bound"}:
        checks["expected_terminal_state"] = (
            state == "completed" and reason == "completed"
        )
        checks["validated_outputs"] = (
            type(document.get("outputs_manifest_sha256")) is str
        )
    elif case.expectation in {"cancelled", "timed_out"}:
        checks["expected_terminal_state"] = state == case.expectation
        checks["no_outputs"] = document.get("outputs_manifest_sha256") is None
    elif case.expectation == "log_bound":
        checks["expected_log_limit"] = state == "failed" and reason == "log_limit"
        checks["no_outputs"] = document.get("outputs_manifest_sha256") is None
    elif case.expectation == "unsafe_output":
        checks["unsafe_output_rejected"] = (
            state == "failed" and reason == "adapter_failure"
        )
        checks["no_outputs"] = document.get("outputs_manifest_sha256") is None
    elif case.expectation == "memory_bound":
        events = metrics.get("memory.events", {})
        checks["actual_memory_limit_event"] = metrics.get("available") is True and any(
            events.get(key, 0) > 0 for key in ("max", "oom", "oom_kill")
        )
        checks["no_successful_result"] = (
            state in {"failed", "uncertain"}
            and document.get("outputs_manifest_sha256") is None
        )
    if case.expectation == "cpu_bound":
        cpu = metrics.get("cpu.stat", {})
        checks["actual_cpu_throttling"] = (
            cpu.get("nr_throttled", 0) > 0 and cpu.get("throttled_usec", 0) > 0
        )
    if case_name == "wall":
        checks["bounded_wall_observation"] = elapsed <= 18
    return {
        "case_assertions_passed": all(checks.values()),
        "checks": checks,
        "scope": "operator synthetic fixture observations only",
        "retained_C22_real_approval": False,
        "runtime_acceptance_complete": False,
        "C23_complete": False,
    }


def run_case(arguments):
    """Sole privileged CLI entry: guard precedes imports, paths and effects."""
    target = require_worker()
    from orchestration.experiment_sandbox.files import stage_inputs
    from orchestration.experiment_sandbox.journal import DurableExecutionJournal
    from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
    from orchestration.experiment_sandbox.profile_execution import (
        render_execution_profile,
    )
    from sandbox.experiment import trusted_init

    attempt = check_attempt_path(arguments.attempt_dir)
    _private_directory(FIXED_ROOT)
    if not ATTEMPTS_ROOT.exists():
        _private_directory(ATTEMPTS_ROOT, create=True)
    else:
        _private_directory(ATTEMPTS_ROOT)
    _private_directory(attempt, create=True)
    listener = None
    journal = envelope = None
    mount_intent = None
    receipt = {
        "version": VERSION,
        "purpose": PURPOSE,
        "retained_C22_real_approval": False,
        "real_C22_reservation_consumption_verified": False,
        "C23_complete": False,
        "case": arguments.case,
        "target": target,
        "attempt_dir": str(attempt),
        "dispatch_eligible": False,
        "reservation_released": False,
        "scientific_approval": "not_independently_verified",
    }
    _create(attempt / "attempt-start.json", _canonical(receipt))
    captures = []

    class RecordingAdapter(LinuxExecutionAdapter):
        def _spawn(self, argv, host, **kwargs):
            if len(captures) >= 64:
                raise OperatorError("operator_command_count")
            capture = super()._spawn(argv, host, **kwargs)
            captures.append((list(argv), capture))
            return capture

    try:
        if not re.fullmatch(r"[a-f0-9]{64}", arguments.blueprint_sha256):
            raise OperatorError("operator_blueprint_hash")
        if _sha(_read(arguments.blueprint, MAX_FIXTURE)) != arguments.blueprint_sha256:
            raise OperatorError("operator_blueprint_hash")
        blueprint = load_blueprint(arguments.blueprint)
        image = json.loads(_read(arguments.image_receipt, MAX_FIXTURE))
        runtime = json.loads(_read(arguments.runtime_manifest, MAX_FIXTURE))
        receipt["materials"] = verify_materials(
            arguments.rootfs,
            arguments.oci_layout,
            image,
            runtime,
            normalization_receipt=arguments.normalization_receipt,
            normalization_sha256=arguments.normalization_sha256,
        )
        host_controls = _immutable_document(
            arguments.host_controls, arguments.host_controls_sha256
        )
        network_isolation = _immutable_document(
            arguments.network_isolation, arguments.network_isolation_sha256
        )
        receipt["network_controls"] = validate_network_controls(
            host_controls,
            network_isolation,
            target,
            instance_id=_metadata("instance/id"),
            boot_id=_boot_id(),
            interfaces=_metadata("instance/network-interfaces/"),
            access_configs=_metadata("instance/network-interfaces/0/access-configs/"),
            external_ip=_metadata(METADATA_EXTERNAL_IP),
            now_ns=time.monotonic_ns(),
        )
        receipt["network_controls_source_sha256"] = {
            "host_positive": arguments.host_controls_sha256,
            "isolation": arguments.network_isolation_sha256,
        }
        listener, controls = _positive_controls(attempt)
        _create(attempt / "host-positive-controls.json", _canonical(controls))
        wrapper = make_operator_fixture(
            blueprint,
            image,
            arguments.case,
            uuid.uuid4().hex,
            host_canary=controls["canary_path"],
            host_socket=controls["socket_path"],
        )
        fixture_path = attempt / "operator-fixture.json"
        fixture_bytes = _canonical(wrapper)
        _create(fixture_path, fixture_bytes)
        receipt["operator_fixture_sha256"] = fixture_sha = _sha(fixture_bytes)
        envelope = verify_operator_fixture(wrapper)
        receipt["job_id"] = envelope.job_id
        worker = _private_directory(attempt / "worker", create=True)
        journal_root = _private_directory(attempt / "journal", create=True)
        journal = DurableExecutionJournal(journal_root)
        receipt["operator_sqlite_version"] = journal.sqlite_runtime_version
        stage_inputs(worker, envelope)
        inputs = worker / envelope.job_id / "inputs"
        for path in inputs.iterdir():
            os.chown(path, APP_UID, APP_GID, follow_symlinks=False)
        os.chown(inputs, APP_UID, APP_GID, follow_symlinks=False)
        inputs.chmod(0o500)
        rootfs_bind = worker / envelope.job_id / "rootfs"
        rootfs_bind.mkdir(mode=0o755)
        mount_intent = MountIntent(Path(arguments.rootfs), rootfs_bind)
        _perform_mount(mount_intent, attempt)
        init_sha = _hash_file(Path(trusted_init.__file__).resolve(), 65536)
        receipt["trusted_init_sha256"] = init_sha
        profile = render_execution_profile(
            envelope,
            job_root=worker / envelope.job_id,
            image_receipt=image,
            runtime_manifest=runtime,
            control_host_uid=CONTROL_UID,
            control_host_gid=CONTROL_GID,
            trusted_init_sha256=init_sha,
        )
        _create(attempt / "profile.json", _canonical(profile.document))
        receipt["comparison_configuration"] = {
            "resources": dict(envelope.resources),
            "rootfs_materialization": {
                "rootfs_inventory_sha256": image["rootfs_inventory_sha256"],
                "normalization_receipt_sha256": arguments.normalization_sha256,
            },
            "normalized_init_policy": {
                key: value
                for key, value in profile.document["trusted_init"]["policy"].items()
                if key not in {"job_id", "envelope_sha256"}
            },
        }
        adapter = RecordingAdapter(
            worker, arguments.runtime_directory, runtime, journal
        )
        cancel_after = None

        def cancelled():
            nonlocal cancel_after
            if arguments.case != "cancel":
                return False
            snapshot = journal.read(envelope.job_id, envelope.envelope_sha256)
            if snapshot and any(event.kind == "started" for event in snapshot.events):
                if cancel_after is None:
                    cancel_after = time.monotonic() + 0.5
                return time.monotonic() >= cancel_after
            return False

        _admission(fixture_path, fixture_sha, envelope)
        started = time.monotonic()
        result = adapter.run(
            envelope,
            profile,
            admission=lambda candidate: _admission(
                fixture_path, fixture_sha, candidate
            ),
            cancelled=cancelled,
        )
        receipt["elapsed_adapter_seconds"] = time.monotonic() - started
        receipt["adapter_result"] = result.document
        receipt["metrics"] = _collect_metrics(
            journal, envelope, observation_dir=attempt
        )
        if result.outputs is not None:
            receipt["validated_manifest"] = result.outputs.manifest
            if "summary.json" in result.outputs.files:
                receipt["summary_table"] = json.loads(
                    result.outputs.files["summary.json"]
                )
    except Exception as error:
        receipt["operator_error"] = {
            "type": type(error).__name__,
            "reason": getattr(error, "reason", str(error))[:512],
        }
    finally:
        try:
            for index, (argv, capture) in enumerate(captures):
                _create(
                    attempt / f"command-{index}.json",
                    _canonical({"argv": argv, "returncode": capture.process.poll()}),
                )
                _create(attempt / f"command-{index}.stdout.bin", bytes(capture.stdout))
                _create(attempt / f"command-{index}.stderr.bin", bytes(capture.stderr))
        except Exception as error:
            receipt["raw_observation_retention_error"] = type(error).__name__
        finally:
            if journal is not None and envelope is not None:
                try:
                    receipt["cleanup"] = _cleanup(journal, envelope, mount_intent)
                except Exception as error:
                    receipt["cleanup"] = {
                        "verified": False,
                        "reason": getattr(error, "reason", str(error))[:512],
                        "rootfs_unmounted": False,
                        "reservation_released": False,
                    }
                finally:
                    journal.close()
            if listener is not None:
                listener.close()
                endpoint = attempt / "host.sock"
                if endpoint.exists() and stat.S_ISSOCK(endpoint.lstat().st_mode):
                    endpoint.unlink()
        if "adapter_result" in receipt and "cleanup" in receipt:
            receipt["evaluation"] = evaluate_case(
                arguments.case,
                receipt["adapter_result"],
                receipt.get("metrics", {}),
                receipt["cleanup"],
                elapsed=receipt["elapsed_adapter_seconds"],
            )
            receipt["evaluation"]["checks"]["operator_pipeline_healthy"] = (
                "operator_error" not in receipt
                and "raw_observation_retention_error" not in receipt
            )
            receipt["evaluation"]["case_assertions_passed"] = all(
                receipt["evaluation"]["checks"].values()
            )
        else:
            receipt["evaluation"] = {
                "case_assertions_passed": False,
                "reason": "operator_setup_or_execution_failed",
            }
        receipt["evidence_files"] = {
            path.name: _hash_file(path, 100 * 1024**2)
            for path in sorted(attempt.iterdir())
            if path.is_file() and not path.is_symlink()
        }
        _create(attempt / "attempt.json", _canonical(receipt))
    print(
        json.dumps(
            {
                "attempt": str(attempt / "attempt.json"),
                "case": arguments.case,
                "case_assertions_passed": receipt["evaluation"][
                    "case_assertions_passed"
                ],
                "retained_C22_real_approval": False,
                "C23_complete": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["evaluation"]["case_assertions_passed"] else 1


def compare_numerics(first, second):
    """Compare completed operator observations; never run a numerical program."""
    for value, name in ((first, "numerics-a"), (second, "numerics-b")):
        if (
            value.get("purpose") != PURPOSE
            or value.get("retained_C22_real_approval") is not False
            or value.get("case") != name
            or value.get("evaluation", {}).get("case_assertions_passed") is not True
            or value.get("adapter_result", {}).get("state") != "completed"
            or value["adapter_result"].get("declared_seeds") != {"numpy": 20261024}
        ):
            raise OperatorError("numerical_attempt_not_accepted")
    if (
        first["adapter_result"]["image_digest"]
        != second["adapter_result"]["image_digest"]
        or first["adapter_result"]["approved_hashes"]["environment_sha256"]
        != second["adapter_result"]["approved_hashes"]["environment_sha256"]
    ):
        raise OperatorError("numerical_environment_changed")
    runtime_pins = {}
    for key in ("runtime_sha256", "trusted_init_sha256", "adapter_source_sha256"):
        left, right = (
            first["adapter_result"].get(key),
            second["adapter_result"].get(key),
        )
        if (
            type(left) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", left)
            or left != right
        ):
            raise OperatorError("numerical_runtime_changed")
        runtime_pins[key] = left
    configuration = first.get("comparison_configuration")
    if (
        type(configuration) is not dict
        or set(configuration)
        != {"resources", "normalized_init_policy", "rootfs_materialization"}
        or any(type(value) is not dict or not value for value in configuration.values())
        or configuration != second.get("comparison_configuration")
    ):
        raise OperatorError("numerical_configuration_changed")
    expected = {
        "mean",
        "t_statistic",
        "p_value",
        "ols_intercept",
        "ols_slope",
        "exact_int64",
    }
    values = []
    for attempt in (first, second):
        table = attempt["summary_table"]
        if table.get("columns") != ["probe", "value"] or len(
            table.get("rows", [])
        ) != len(expected):
            raise OperatorError("numerical_summary_shape")
        mapping = dict(table["rows"])
        if (
            set(mapping) != expected
            or type(mapping["exact_int64"]) is not int
            or mapping["exact_int64"] != 2**63 - 1
        ):
            raise OperatorError("numerical_summary_identity")
        values.append(mapping)
    matched = {}
    for key in sorted(expected - {"exact_int64"}):
        left, right = (mapping[key] for mapping in values)
        if (
            type(left) not in (int, float)
            or type(right) not in (int, float)
            or not math.isfinite(left)
            or not math.isfinite(right)
        ):
            raise OperatorError("numerical_nonfinite")
        matched[key] = math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return {
        "purpose": PURPOSE,
        "repeated_numerics_within_tolerance": all(matched.values()),
        "comparisons": matched,
        "relative_tolerance": 1e-12,
        "absolute_tolerance": 1e-12,
        "exact_int64_preserved": True,
        "declared_seeds": {"numpy": 20261024},
        "image_digest": first["adapter_result"]["image_digest"],
        "runtime_pins": runtime_pins,
        "comparison_configuration": configuration,
        "retained_C22_real_approval": False,
        "scientific_approval": "not_independently_verified",
        "C23_complete": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    prepare = commands.add_parser("prepare-blueprint")
    prepare.add_argument("--output", type=Path, required=True)
    commands.add_parser("list-cases")
    host = commands.add_parser("prepare-host-controls")
    host.add_argument("--output", type=Path, required=True)
    seal = commands.add_parser("seal-network-isolation")
    for name in (
        "instance-resource",
        "routers",
        "network-resource",
        "subnetwork-resource",
    ):
        seal.add_argument("--" + name, type=Path, required=True)
    seal.add_argument("--complete-router-inventory", action="store_true", required=True)
    seal.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--case", choices=sorted(cases()), required=True)
    run.add_argument("--attempt-dir", type=Path, required=True)
    run.add_argument("--blueprint", type=Path, required=True)
    run.add_argument("--blueprint-sha256", required=True)
    run.add_argument("--host-controls", type=Path, required=True)
    run.add_argument("--host-controls-sha256", required=True)
    run.add_argument("--network-isolation", type=Path, required=True)
    run.add_argument("--network-isolation-sha256", required=True)
    run.add_argument("--normalization-receipt", type=Path, required=True)
    run.add_argument("--normalization-sha256", required=True)
    run.add_argument(
        "--rootfs",
        type=Path,
        default=FIXED_ROOT / "scientific-normalized-quota-v3/rootfs",
    )
    run.add_argument(
        "--oci-layout", type=Path, default=FIXED_ROOT / "scientific-oci-quota-v3"
    )
    run.add_argument(
        "--image-receipt",
        type=Path,
        default=FIXED_ROOT / "evidence/image-preparation-quota-v3.json",
    )
    run.add_argument(
        "--runtime-manifest",
        type=Path,
        default=FIXED_ROOT / "evidence/runtime-preparation-quota-v3.json",
    )
    run.add_argument(
        "--runtime-directory",
        type=Path,
        default=Path("/opt/ocean-c23-runtime/release-20261019.0"),
    )
    compare = commands.add_parser("compare-numerics")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.action == "prepare-blueprint":
        print(json.dumps(prepare_blueprint(arguments.output), sort_keys=True))
        return 0
    if arguments.action == "list-cases":
        print(
            json.dumps(
                {
                    name: {
                        "expectation": case.expectation,
                        "resources": case.resources,
                        "seeds": case.seeds,
                    }
                    for name, case in cases().items()
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.action == "run":
        return run_case(arguments)
    if arguments.action == "prepare-host-controls":
        print(json.dumps(prepare_host_controls(arguments.output), sort_keys=True))
        return 0
    if arguments.action == "seal-network-isolation":
        print(json.dumps(seal_network_isolation(arguments), sort_keys=True))
        return 0
    if arguments.action == "compare-numerics":
        first, second = (
            _read(arguments.first, MAX_FIXTURE),
            _read(arguments.second, MAX_FIXTURE),
        )
        result = compare_numerics(json.loads(first), json.loads(second))
        result["input_sha256"] = {"first": _sha(first), "second": _sha(second)}
        _create(arguments.output, _canonical(result))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["repeated_numerics_within_tolerance"] else 1
    raise OperatorError("operator_action_unknown")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OperatorError, OSError, ValueError) as error:
        raise SystemExit(f"c23_operator_refused: {type(error).__name__}") from None
