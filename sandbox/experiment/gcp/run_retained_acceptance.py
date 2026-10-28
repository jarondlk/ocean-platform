"""Dedicated isolated C23 retained acceptance, with authentic synthetic C22 review.

Only the pinned Linux worker may run this CLI. The root-private configuration
supplies distinct application/controller/verifier LOGINs over an operator-owned
loopback transport. No bootstrap/admin credential, public route or real dataset
is used. Analysis code is stored/approved first and executes only in gVisor.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import stat
import time

from sandbox.experiment.gcp import run_operator_acceptance as base

VERSION = "c23-retained-acceptance-v1"
CONFIG_VERSION = "c23-retained-acceptance-config-v1"
SITE = "v1:c17-synthetic"
CASES = {"scientific", "publication-revoked"}
KEYS = {
    "version",
    "case",
    "database_name",
    "schema",
    "application_dsn",
    "controller_dsn",
    "verifier_dsn",
    "roles",
    "source_root",
    "worker_source_files",
    "profile_source_files",
    "expected_worker_id",
    "issuer_id",
    "key_id",
    "issuer_public_key_hex",
    "private_key_path",
    "materials",
    "network",
}
MATERIAL_KEYS = {
    "rootfs",
    "oci_layout",
    "image_receipt",
    "image_receipt_sha256",
    "runtime_manifest",
    "runtime_manifest_sha256",
    "runtime_directory",
    "normalization_receipt",
    "normalization_sha256",
}
NETWORK_KEYS = {
    "host_controls",
    "host_controls_sha256",
    "network_isolation",
    "network_isolation_sha256",
}
ROLE_KEYS = {"serving_role", "controller_role", "verifier_role", "function_owner_role"}
FIXTURE_MODULES = (
    "tests.research_experiment_support",
    "tests.investigation_support",
    "tests.catalogue_service_support",
    "tests.test_scientific_catalogue_sources",
)
SCIENCE_CODE = """# Authentic synthetic C22 owner review; experimental, not scientific approval.
import json, math
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.stats as stats
import statsmodels.api as sm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
exact=[9223372036854775806,9223372036854775807]
frame=pd.DataFrame({"exact":np.asarray(exact,dtype=np.int64)})
pq.write_table(pa.Table.from_pandas(frame,preserve_index=False),"/scratch/exact.parquet")
restored=pq.read_table("/scratch/exact.parquet").column("exact").to_pylist()
assert restored==exact
values=np.random.default_rng(20261024).normal(size=32)
test=stats.ttest_1samp(values,0.0)
fit=sm.OLS(np.array([1.,3.,5.,7.]),sm.add_constant(np.arange(4,dtype=float))).fit()
assert math.isclose(float(fit.params[0]),1.,rel_tol=1e-10,abs_tol=1e-10)
assert math.isclose(float(fit.params[1]),2.,rel_tol=1e-10,abs_tol=1e-10)
fig,ax=plt.subplots(figsize=(2,2));ax.plot([0,1],[0,1]);fig.savefig("/scratch/probe.png");plt.close(fig)
assert open("/scratch/probe.png","rb").read(8)==b"\\x89PNG\\r\\n\\x1a\\n"
rows=[["mean",float(values.mean())],["t_statistic",float(test.statistic)],["p_value",float(test.pvalue)],
      ["ols_intercept",float(fit.params[0])],["ols_slope",float(fit.params[1])],["exact_int64",restored[-1]]]
assert all(math.isfinite(value) for name,value in rows)
with open("summary.json","w",encoding="utf-8") as stream:
    json.dump({"columns":["probe","value"],"rows":rows},stream,allow_nan=False,separators=(",",":"))
"""


def parse_config(document):
    """Pure strict shape/target checks; neither connects nor discovers a DSN."""
    from sqlalchemy.engine import make_url

    if (
        type(document) is not dict
        or set(document) != KEYS
        or document.get("version") != CONFIG_VERSION
        or document.get("case") not in CASES
        or not re.fullmatch(r"ocean_c23_[a-z0-9_]+", document.get("database_name", ""))
        or not re.fullmatch(r"c23_[a-z0-9_]+", document.get("schema", ""))
        or type(document["roles"]) is not dict
        or set(document["roles"]) != ROLE_KEYS
        or type(document["materials"]) is not dict
        or set(document["materials"]) != MATERIAL_KEYS
        or type(document["network"]) is not dict
        or set(document["network"]) != NETWORK_KEYS
    ):
        raise base.OperatorError("retained_operator_config")
    names = list(document["roles"].values())
    if len(set(names)) != 4 or any(
        type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name)
        for name in names
    ):
        raise base.OperatorError("retained_operator_roles")
    for field, role in (
        ("application_dsn", "serving_role"),
        ("controller_dsn", "controller_role"),
        ("verifier_dsn", "verifier_role"),
    ):
        try:
            url = make_url(document[field])
            valid = (
                url.drivername == "postgresql+psycopg2"
                and url.host == "127.0.0.1"
                and type(url.port) is int
                and 1024 <= url.port <= 65535
                and not url.query
                and url.database == document["database_name"]
                and url.username == document["roles"][role]
                and type(url.password) is str
                and 24 <= len(url.password) <= 256
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise base.OperatorError("retained_operator_dsn")
    for name in ("expected_worker_id", "issuer_public_key_hex"):
        if type(document[name]) is not str or not re.fullmatch(
            r"[a-f0-9]{64}", document[name]
        ):
            raise base.OperatorError("retained_operator_pin")
    for name in ("issuer_id", "key_id"):
        if type(document[name]) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", document[name]
        ):
            raise base.OperatorError("retained_operator_pin")
    paths = [document["source_root"], document["private_key_path"]]
    for group in ("materials", "network"):
        for name, value in document[group].items():
            if name.endswith("sha256"):
                if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
                    raise base.OperatorError("retained_operator_pin")
            else:
                paths.append(value)
    if any(
        type(value) is not str
        or not Path(value).is_absolute()
        or ".." in Path(value).parts
        for value in paths
    ):
        raise base.OperatorError("retained_operator_path")
    # Validate the exact configured map before any DB or runtime side effect.
    from orchestration.experiment_sandbox import physical_termination as physical

    required = physical.WORKER_FILES | {
        "orchestration/experiment_sandbox/retained_admission.py",
        "sandbox/experiment/gcp/run_retained_acceptance.py",
        "sandbox/experiment/gcp/run_operator_acceptance.py",
        "tests/research_experiment_support.py",
        "tests/investigation_support.py",
        "tests/catalogue_service_support.py",
        "tests/test_scientific_catalogue_sources.py",
    }
    physical._manifest(
        document["worker_source_files"],
        required=required,
        version=physical.WORKER_POLICY_VERSION,
    )
    profile, _ = physical._manifest(
        document["profile_source_files"],
        required=physical.PROFILE_FILES,
        version=physical.PROFILE_POLICY_VERSION,
    )
    if set(profile) != physical.PROFILE_FILES or any(
        document["worker_source_files"].get(name) != value
        for name, value in profile.items()
    ):
        raise base.OperatorError("retained_operator_pin")
    return json.loads(json.dumps(document, allow_nan=False))


def private_bytes(path, maximum, *, exact_mode=0o400):
    path = Path(path)
    base._private_directory(path.parent)
    info = path.lstat()
    if (
        path != path.resolve(strict=True)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != exact_mode
        or not stat.S_ISREG(info.st_mode)
    ):
        raise base.OperatorError("retained_operator_private_file")
    return base._read(path, maximum)


def _secret_boundary(config, config_path, attempt):
    """Control credentials must be outside source, material and job trees."""
    roots = [Path(config["source_root"]), Path(attempt)]
    roots.extend(
        Path(config["materials"][name])
        for name in ("rootfs", "oci_layout", "runtime_directory")
    )
    for secret in (Path(config_path), Path(config["private_key_path"])):
        if any(secret == root or root in secret.parents for root in roots):
            raise base.OperatorError("retained_operator_secret_mount_boundary")


def _prepare_source_imports(config):
    """Pin trusted fixture imports before the first application DB access."""
    from orchestration.experiment_sandbox import physical_termination as physical

    root = Path(config["source_root"])
    physical._protected_sources(root, config["worker_source_files"])
    if (
        Path(__file__).resolve()
        != root / "sandbox/experiment/gcp/run_retained_acceptance.py"
    ):
        raise base.OperatorError("retained_operator_source_origin")
    for relative in sorted(
        physical.WORKER_FILES - {"sandbox/experiment/trusted_init.py"}
    ):
        importlib.import_module(relative[:-3].replace("/", "."))
    for name in FIXTURE_MODULES:
        importlib.import_module(name)
    physical.require_loaded_source_provenance(
        root, config["worker_source_files"], check=lambda: None
    )


def _engine(config, field):
    from sqlalchemy import create_engine

    return create_engine(
        config[field],
        pool_pre_ping=True,
        connect_args={
            "options": "-csearch_path="
            + config["schema"]
            + " -clock_timeout=8000 -cstatement_timeout=20000",
            "connect_timeout": 5,
        },
        hide_parameters=True,
    )


def _application_boundary(engine, config, *, require_empty=True):
    from sqlalchemy import text
    from db.experiment_execution_models import EXECUTION_MODELS

    with engine.connect() as connection:
        actual = connection.execute(
            text(
                "SELECT current_database(),current_user,session_user,current_schema(),"
                "(SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user)"
            )
        ).one()
        if tuple(actual) != (
            config["database_name"],
            config["roles"]["serving_role"],
            config["roles"]["serving_role"],
            config["schema"],
            False,
        ):
            raise base.OperatorError("retained_application_role_boundary")
        for model in EXECUTION_MODELS:
            if (
                connection.scalar(
                    text(
                        "SELECT has_table_privilege(current_user,CAST(:name AS regclass),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR has_any_column_privilege(current_user,CAST(:name AS regclass),'INSERT,UPDATE,REFERENCES')"
                    ),
                    {"name": config["schema"] + "." + model.__tablename__},
                )
                is not False
            ):
                raise base.OperatorError("retained_application_role_boundary")
        if (
            require_empty
            and connection.scalar(text("SELECT count(*) FROM app_user")) != 0
        ):
            raise base.OperatorError("retained_fixture_store_not_empty")
    return {
        "database": config["database_name"],
        "schema": config["schema"],
        "application_role": config["roles"]["serving_role"],
        "C23_write_privilege": False,
    }


def _make_fixture(application, attempt, image):
    from tests.research_experiment_support import make_experiment_fixture
    from schema.research_experiments import EnvironmentDescriptor, ExperimentResources

    fixture = make_experiment_fixture(application, attempt / "synthetic-sources")
    fixture.environment = EnvironmentDescriptor(
        kind="linux-gvisor",
        test_only=False,
        python_version=image["python_version"],
        image_digest=image["image_digest"],
        lockfile_sha256=image["lockfile_sha256"],
        packages=image["packages"],
        description="Pinned C23 retained synthetic acceptance image; scientific approval unverified",
    )
    fixture.service.environments[fixture.environment.identity_sha256] = (
        fixture.environment.model_dump(mode="json")
    )
    request = fixture.request()
    request["proposal"].update(
        python_code=SCIENCE_CODE,
        seeds={"numpy": 20261024},
        question="Authenticated synthetic C22 scientific-package compatibility acceptance",
        limitations=[
            "Synthetic operator acceptance only; no independent scientific approval"
        ],
    )
    request["proposal"]["resources"] = ExperimentResources().model_dump(mode="json")
    # Existing approve checks its unchanged fake-capable gate. No dispatch is
    # invoked; the stored environment is the real pinned Linux descriptor.
    created = fixture.service.invoke("create", request, fixture.user)["experiment"]
    approved = fixture.service.invoke(
        "approve", fixture.decision(created), fixture.user
    )["experiment"]
    fixture.state["dispatch_enabled"] = False
    if fixture.executor.deliveries:
        raise base.OperatorError("retained_unexpected_fake_dispatch")
    return fixture, fixture.decision(approved)


def _reader(fixture, factory):
    from orchestration.investigations import InvestigationService
    from orchestration.research_experiments import ResearchExperimentService

    investigations = InvestigationService(
        session_factory=factory,
        site_id=SITE,
        catalogue_service=fixture.investigations.catalogue,
        snapshot_store=fixture.retained.store,
        registrations=fixture.retained.registrations,
    )
    return ResearchExperimentService(
        session_factory=factory,
        site_id=SITE,
        investigations=investigations,
        exporter=fixture.exporter,
        environments={fixture.environment.identity_sha256: fixture.environment},
        enabled=lambda: fixture.state["enabled"],
        dispatch_enabled=lambda: False,
    )


def _policy(config, environment, runtime, journal):
    from orchestration.experiment_sandbox import physical_termination as physical
    from orchestration.experiment_sandbox.retained_admission import (
        RetainedAdmissionSourcePolicy,
    )
    from schema.research_experiments import content_sha256

    if journal.host_id != config["expected_worker_id"]:
        raise base.OperatorError("retained_worker_identity")
    worker, worker_hash = physical._manifest(
        config["worker_source_files"],
        required=physical.WORKER_FILES,
        version=physical.WORKER_POLICY_VERSION,
    )
    profile, profile_hash = physical._manifest(
        config["profile_source_files"],
        required=physical.PROFILE_FILES,
        version=physical.PROFILE_POLICY_VERSION,
    )
    fields = {
        "worker_id": journal.host_id,
        "worker_source_sha256": worker_hash,
        "environment_sha256": environment.identity_sha256,
        "image_digest": environment.image_digest,
        "runtime_sha256": content_sha256(runtime),
        "profile_policy_sha256": profile_hash,
        "trusted_init_sha256": profile["sandbox/experiment/trusted_init.py"],
        "adapter_source_sha256": worker[
            "orchestration/experiment_sandbox/linux_runtime.py"
        ],
    }
    raw = physical._canonical(
        {
            "version": physical.SOURCE_POLICY_VERSION,
            "trust_scope": "retained-operator",
            **fields,
        }
    )
    return RetainedAdmissionSourcePolicy(
        config["source_root"], dict(worker), dict(profile), raw, "retained-operator"
    )


def _database_snapshot(store, identity):
    from sqlalchemy import text

    result = {}
    execution = identity.document["execution_id"]
    with store.controller_transaction(cleanup=True) as session:
        for table in (
            "research_experiment_execution",
            "research_experiment_execution_state",
            "research_experiment_execution_event",
            "research_experiment_termination_proof",
            "research_experiment_release",
        ):
            rows = (
                session.execute(
                    text(
                        "SELECT to_jsonb(t) FROM "
                        + store.config.schema
                        + "."
                        + table
                        + " t WHERE execution_id=CAST(:id AS uuid)"
                    ),
                    {"id": execution},
                )
                .scalars()
                .all()
            )
            if len(rows) > 16:
                raise base.OperatorError("retained_database_observation_limit")
            result[table] = rows
    if len(base._canonical(result)) > 4 * 1024**2:
        raise base.OperatorError("retained_database_observation_limit")
    return result


def _c22_observation(config, identity):
    """Separate authenticated application SELECT after runtime; no new grants."""
    from sqlalchemy import text

    observer = _engine(config, "application_dsn")
    try:
        boundary = _application_boundary(observer, config, require_empty=False)
        with observer.begin() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            actual = connection.execute(
                text("SELECT current_user,session_user,current_schema()")
            ).one()
            if tuple(actual) != (
                config["roles"]["serving_role"],
                config["roles"]["serving_role"],
                config["schema"],
            ):
                raise base.OperatorError("retained_application_role_boundary")
            return {
                "C22_observer_boundary": boundary,
                "fake_outbox_count": connection.scalar(
                    text("SELECT count(*) FROM research_experiment_outbox")
                ),
                "reservation": connection.scalar(
                    text(
                        "SELECT to_jsonb(r) FROM research_experiment_reservation r WHERE id=CAST(:id AS uuid)"
                    ),
                    {"id": identity.document["reservation_id"]},
                ),
            }
    finally:
        observer.dispose()


def _revoke_owner(config, owner_id):
    """Short authenticated C22 owner write, called only AFTER durable terminal."""
    from sqlalchemy import text

    writer = _engine(config, "application_dsn")
    try:
        boundary = _application_boundary(writer, config, require_empty=False)
        with writer.begin() as connection:
            observation = connection.scalar(
                text(
                    "UPDATE app_user SET status='suspended',updated_at=clock_timestamp() "
                    "WHERE id=CAST(:id AS uuid) AND status='active' RETURNING "
                    "jsonb_build_object('owner_user_id',id,'status',status,'database_observed_at',clock_timestamp(),"
                    "'database',current_database(),'application_role',current_user)"
                ),
                {"id": str(owner_id)},
            )
            if (
                type(observation) is not dict
                or observation.get("status") != "suspended"
            ):
                raise base.OperatorError("retained_owner_revocation_unknown")
        # The accepted receipt requires acknowledged commit plus fresh readback.
        with writer.begin() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            status = connection.scalar(
                text("SELECT status FROM app_user WHERE id=CAST(:id AS uuid)"),
                {"id": str(owner_id)},
            )
            if status != "suspended":
                raise base.OperatorError("retained_owner_revocation_unknown")
        return {
            "boundary": boundary,
            "observation": observation,
            "readback_status": status,
            "feature_flag_enabled": True,
            "performed_after_durable_terminal": True,
        }
    finally:
        writer.dispose()


def evaluate(case, report, database, cleanup):
    publication = "acknowledged" if case == "scientific" else "denied_or_uncertain"
    checks = {
        "actual_analysis_success": report.get("state") == "completed"
        and report.get("analysis_exit_code") == 0
        and report.get("host_runtime_exit_status") == 0
        and report.get("execution_started") is True,
        "actual_cleanup_retained": report.get("native_cleanup_recorded") is True,
        "durable_terminal": type(report.get("durable_terminal")) is dict,
        "publication_expected": report.get("publication_status") == publication,
        "release_acknowledged": report.get("capacity_release_status") == "acknowledged"
        and report.get("reservation_released") is True,
        "one_actual_start": len(
            [
                e
                for e in database.get("research_experiment_execution_event", [])
                if e["kind"] == "start_consumed"
            ]
        )
        == 1,
        "publication_ledger_expected": len(
            [
                e
                for e in database.get("research_experiment_execution_event", [])
                if e["kind"] == "publication_retained"
            ]
        )
        == (1 if case == "scientific" else 0),
        "one_proof": len(database.get("research_experiment_termination_proof", []))
        == 1,
        "one_release": len(database.get("research_experiment_release", [])) == 1,
        "no_fake_outbox": database.get("fake_outbox_count") == 0,
        "C22_reservation_released": (database.get("reservation") or {}).get("state")
        == "released",
        "rootfs_unmounted": cleanup.get("rootfs_unmounted") is True,
        "whole_cgroup_empty": cleanup.get("cgroup_empty") is True,
        "scientific_unverified": report.get("scientific_approval")
        == "not_independently_verified",
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "C23_complete": False,
        "scientific_approval": "not_independently_verified",
        "scope": "one authentic synthetic C22 retained execution on isolated operator worker",
    }


def run(arguments):
    # This must precede config reads, DB imports/connections, filesystem effects
    # and every possible Linux effect. There is no Mac/ordinary-container path.
    target = base.require_worker()
    raw = private_bytes(arguments.config, 2 * 1024**2)
    if base._sha(raw) != arguments.config_sha256:
        raise base.OperatorError("retained_operator_config_hash")
    config = parse_config(json.loads(raw))
    attempt = base.check_attempt_path(arguments.attempt_dir)
    _secret_boundary(config, arguments.config, attempt)
    base._private_directory(base.FIXED_ROOT, allow_search=True)
    base._private_directory(
        base.ATTEMPTS_ROOT, create=not base.ATTEMPTS_ROOT.exists(), allow_search=True
    )
    base._private_directory(attempt, create=True, allow_search=True)
    if (
        Path(config["source_root"]) == attempt
        or Path(config["source_root"]) in attempt.parents
    ):
        raise base.OperatorError("retained_separate_source_root")
    receipt = {
        "version": VERSION,
        "case": config["case"],
        "target": target,
        "config_sha256": arguments.config_sha256,
        "retained_C22_application_approval": False,
        "C23_complete": False,
        "scientific_approval": "not_independently_verified",
        "attempt_dir": str(attempt),
    }
    base._create(attempt / "attempt-start.json", base._canonical(receipt))
    engines = []
    journal = envelope = mount_intent = identity = store = None
    fixture = None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text
        from orchestration.experiment_sandbox import physical_termination as physical
        from orchestration.experiment_sandbox.contracts import verify_execution_envelope
        from orchestration.experiment_sandbox.execution_store import (
            C23ExecutionStore,
            ExecutionStoreConfig,
            ExecutionRolePolicy,
        )
        from orchestration.experiment_sandbox.files import stage_inputs
        from orchestration.experiment_sandbox.journal import DurableExecutionJournal
        from orchestration.experiment_sandbox.linux_runtime import LinuxExecutionAdapter
        from orchestration.experiment_sandbox.operator_inspection import (
            C23OperatorInspection,
            OperatorInspectionConfig,
        )
        from orchestration.experiment_sandbox.profile_execution import (
            render_execution_profile,
        )
        from orchestration.experiment_sandbox.proofs import (
            PinnedTerminationIssuer,
            TerminationVerifierRegistry,
        )
        from orchestration.experiment_sandbox.retained_admission import (
            RetainedRuntimeHooks,
        )
        from orchestration.experiment_sandbox.retained_bridge import (
            C23RetainedBridge,
            RetainedMaterialPolicy,
        )
        from orchestration.experiment_sandbox.retained_runner import run_retained
        from schema.experiment_execution import TerminationIssuerScope

        _prepare_source_imports(config)
        materials = config["materials"]
        image = base._immutable_document(
            materials["image_receipt"], materials["image_receipt_sha256"]
        )
        runtime = base._immutable_document(
            materials["runtime_manifest"], materials["runtime_manifest_sha256"]
        )
        receipt["materials"] = base.verify_materials(
            materials["rootfs"],
            materials["oci_layout"],
            image,
            runtime,
            normalization_receipt=materials["normalization_receipt"],
            normalization_sha256=materials["normalization_sha256"],
        )
        net = config["network"]
        receipt["network_controls"] = base.validate_network_controls(
            base._immutable_document(net["host_controls"], net["host_controls_sha256"]),
            base._immutable_document(
                net["network_isolation"], net["network_isolation_sha256"]
            ),
            target,
            instance_id=base._metadata("instance/id"),
            boot_id=base._boot_id(),
            interfaces=base._metadata("instance/network-interfaces/"),
            access_configs=base._metadata(
                "instance/network-interfaces/0/access-configs/"
            ),
            external_ip=base._metadata(base.METADATA_EXTERNAL_IP),
            now_ns=time.monotonic_ns(),
        )
        worker = base._private_directory(attempt / "worker", create=True)
        journal = DurableExecutionJournal(
            base._private_directory(attempt / "journal", create=True)
        )
        application = _engine(config, "application_dsn")
        engines.append(application)
        receipt["application_boundary"] = _application_boundary(application, config)
        os.environ.update(ENABLE_V1_CATALOGUE="true", ENABLE_V1_INVESTIGATIONS="true")
        try:
            fixture, request = _make_fixture(application, attempt, image)
        finally:
            application.dispose()  # No writer connection is retained into runtime.
        receipt["retained_C22_application_approval"] = True
        controller = _engine(config, "controller_dsn")
        engines.append(controller)
        verifier = _engine(config, "verifier_dsn")
        engines.append(verifier)
        controller_factory = sessionmaker(bind=controller, expire_on_commit=False)
        verifier_factory = sessionmaker(bind=verifier, expire_on_commit=False)
        service = _reader(fixture, controller_factory)
        policy = _policy(config, fixture.environment, runtime, journal)
        scope = TerminationIssuerScope.model_validate(
            {"site_id": SITE, **json.loads(policy._binding_json)}
        )
        secret = private_bytes(config["private_key_path"], 32)
        if len(secret) != 32:
            raise base.OperatorError("retained_operator_key")
        key = Ed25519PrivateKey.from_private_bytes(secret)
        if key.public_key().public_bytes_raw().hex() != config["issuer_public_key_hex"]:
            raise base.OperatorError("retained_operator_key")
        registry = TerminationVerifierRegistry(
            issuers=[
                PinnedTerminationIssuer(
                    issuer_id=config["issuer_id"],
                    key_id=config["key_id"],
                    trust_scope="retained-operator",
                    public_key=bytes.fromhex(config["issuer_public_key_hex"]),
                    scope=scope,
                )
            ],
            trust_scope="retained-operator",
            enabled=True,
        )
        store = C23ExecutionStore(
            config=ExecutionStoreConfig(
                site_id=SITE,
                database_name=config["database_name"],
                schema=config["schema"],
                controller_session_factory=controller_factory,
                recorder_session_factory=verifier_factory,
                roles=ExecutionRolePolicy(**config["roles"]),
                verifier_registry=registry,
                store_scope="isolated-unmounted-operator",
                enabled=lambda: fixture.state["enabled"],
            )
        )
        inspection = C23OperatorInspection(
            service=service,
            config=OperatorInspectionConfig(
                site_id=SITE,
                session_factory=controller_factory,
                environments={fixture.environment.identity_sha256: fixture.environment},
                store_scope="isolated-unmounted-operator",
                enabled=lambda: fixture.state["enabled"],
            ),
        )

        def enabled():
            if config["case"] == "publication-revoked" and envelope is not None:
                snapshot = journal.read(envelope.job_id, envelope.envelope_sha256)
                if snapshot is not None and snapshot.terminal:
                    if "publication_revocation" not in receipt:
                        receipt["publication_revocation"] = {
                            "version": "c23-retained-owner-revocation-v1",
                            "job_id": envelope.job_id,
                            "envelope_sha256": envelope.envelope_sha256,
                            "terminal_journal_sha256": snapshot.events[-1].sha256,
                            "revocation": "C22_owner_status",
                            **_revoke_owner(config, fixture.user.id),
                        }
                        base._create(
                            attempt / "publication-revocation.json",
                            base._canonical(receipt["publication_revocation"]),
                        )
            return fixture.state["enabled"]

        bridge = C23RetainedBridge(
            inspection=inspection,
            store=store,
            material_policy=RetainedMaterialPolicy(**scope.model_dump(mode="json")),
            enabled=enabled,
        )
        address = {
            name: value for name, value in request.items() if name != "idempotency_key"
        }
        candidate = inspection.inspect_approved(address, current_owner=fixture.user)
        identity = bridge.reserve(request, current_owner=fixture.user)
        with store.controller_transaction() as session:
            metadata = json.loads(
                session.scalar(
                    text(
                        "SELECT envelope_json FROM "
                        + config["schema"]
                        + ".research_experiment_execution WHERE execution_id=CAST(:id AS uuid)"
                    ),
                    {"id": identity.document["execution_id"]},
                )
            )
        envelope = verify_execution_envelope(
            {"metadata": metadata, "files": dict(candidate.files)},
            expected_envelope_sha256=identity.document["envelope_sha256"],
            environments={
                fixture.environment.identity_sha256: fixture.environment.model_dump(
                    mode="json"
                )
            },
        )
        base._create(
            attempt / "retained-reservation.json", base._canonical(identity.document)
        )
        receipt.update(
            job_id=envelope.job_id,
            execution_id=identity.document["execution_id"],
            source_policy=json.loads(policy._policy_bytes),
            verifier_policy_sha256=registry.policy_sha256,
        )
        stage_inputs(worker, envelope)
        inputs = worker / envelope.job_id / "inputs"
        for path in inputs.iterdir():
            os.chown(path, base.APP_UID, base.APP_GID, follow_symlinks=False)
        os.chown(inputs, base.APP_UID, base.APP_GID, follow_symlinks=False)
        inputs.chmod(0o500)
        rootfs = worker / envelope.job_id / "rootfs"
        rootfs.mkdir(mode=0o755)
        mount_intent = base.MountIntent(Path(materials["rootfs"]), rootfs)
        base._perform_mount(mount_intent, attempt)
        receipt["gofer_traversal"] = base._grant_gofer_traversal(
            attempt, worker, worker / envelope.job_id
        )
        profile = render_execution_profile(
            envelope,
            job_root=worker / envelope.job_id,
            image_receipt=image,
            runtime_manifest=runtime,
            control_host_uid=base.CONTROL_UID,
            control_host_gid=base.CONTROL_GID,
            trusted_init_sha256=scope.trusted_init_sha256,
        )
        base._create(attempt / "profile.json", base._canonical(profile.document))
        adapter = LinuxExecutionAdapter(
            worker, materials["runtime_directory"], runtime, journal
        )
        hooks = RetainedRuntimeHooks(bridge, fixture.user, policy)
        evidence = base._private_directory(attempt / "issuer", create=True)
        # Every required trusted host module is imported from the protected
        # archive before actual origin checks. Guest init is never run here.
        for relative in sorted(
            physical.WORKER_FILES - {"sandbox/experiment/trusted_init.py"}
        ):
            importlib.import_module(relative[:-3].replace("/", "."))
        issuer = physical.LinuxTerminationIssuer(
            config=physical.PhysicalIssuerConfig(
                store=store,
                registry=registry,
                scope=scope,
                issuer_id=config["issuer_id"],
                key_id=config["key_id"],
                private_key=key,
                source_root=config["source_root"],
                evidence_root=evidence,
                worker_source_files=config["worker_source_files"],
                profile_source_files=config["profile_source_files"],
                source_policy_bytes=policy._policy_bytes,
                enabled=True,
            )
        )
        if private_bytes(arguments.config, 2 * 1024**2) != raw:
            raise base.OperatorError("retained_operator_config_changed")
        physical.require_loaded_source_provenance(
            Path(config["source_root"]),
            config["worker_source_files"],
            check=lambda: None,
        )
        started = time.monotonic()
        result = run_retained(
            adapter, identity, envelope, profile, hooks=hooks, issuer=issuer
        )
        receipt["elapsed_runtime_seconds"] = time.monotonic() - started
        receipt["report"] = result.document
        receipt["metrics"] = base._collect_metrics(
            journal, envelope, observation_dir=attempt
        )
    except Exception as error:
        reason = getattr(error, "reason", None)
        receipt["error"] = {
            "type": type(error).__name__,
            "reason": reason
            if type(reason) is str and re.fullmatch(r"sandbox_[a-z0-9_]{1,96}", reason)
            else "retained_operator_failure",
        }
    finally:
        if store is not None and identity is not None:
            try:
                receipt["database"] = _database_snapshot(store, identity)
                receipt["database"].update(_c22_observation(config, identity))
                base._create(
                    attempt / "database-observation.json",
                    base._canonical(receipt["database"]),
                )
            except Exception as error:
                receipt["database_observation_error"] = type(error).__name__
        if journal is not None and envelope is not None:
            try:
                receipt["cleanup"] = base._cleanup(journal, envelope, mount_intent)
            except Exception as error:
                receipt["cleanup"] = {
                    "verified": False,
                    "rootfs_unmounted": False,
                    "cgroup_empty": False,
                    "exception_type": type(error).__name__,
                    "reservation_release_authorized": False,
                }
        if journal is not None:
            journal.close()
        for engine in engines:
            engine.dispose()
        receipt["evaluation"] = evaluate(
            config["case"],
            receipt.get("report", {}),
            receipt.get("database", {}),
            receipt.get("cleanup", {}),
        )
        receipt["evaluation"]["checks"]["revocation_observed"] = (
            config["case"] == "scientific" or "publication_revocation" in receipt
        )
        receipt["evaluation"]["checks"]["operator_pipeline_healthy"] = not any(
            name in receipt for name in ("error", "database_observation_error")
        )
        receipt["evaluation"]["passed"] = all(receipt["evaluation"]["checks"].values())
        base._create(attempt / "observations.json", base._canonical(receipt))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--attempt-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-f0-9]{64}", args.config_sha256):
        parser.error("Canonical config SHA256 required")
    result = run(args)
    print(
        json.dumps(
            {
                "version": VERSION,
                "case": result["case"],
                "attempt_dir": str(args.attempt_dir),
                "passed": result["evaluation"]["passed"],
                "C23_complete": False,
            },
            sort_keys=True,
        )
    )
    return 0 if result["evaluation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
