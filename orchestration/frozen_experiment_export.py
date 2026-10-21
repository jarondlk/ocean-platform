"""C22 deterministic private machine inputs from explicit sealed scientific sources.

No execution, discovery, acquisition, promotion or scientific approval occurs here.
The caller owns current C17 owner checks and durable dependency protection.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import math
import re
from types import MappingProxyType

import pyarrow.parquet as pq

from api.auth import CurrentUser
from ingestion.edna_catalogue_inputs import KEYS as EDNA_KEYS, parse_community_availability
from ingestion.immutable_bundle import canonical_bytes
from orchestration.catalogue_service import CatalogueService, FrozenCatalogueResolver, catalogue_access_binding
from orchestration.frozen_catalogue import _scoped
from orchestration.frozen_edna_catalogue import Parameters as EDNAParameters, SCIENTIFIC_METHODS, _select as edna_select
from orchestration.frozen_scientific_catalogue import FrozenScientificCatalogueAdapter
from orchestration.frozen_sst_catalogue import _select as sst_select
from orchestration.publication_scope import publication_compatibility, resolve_protocol
from orchestration.research_controller_scope import project_pin, resolve_scope
from preprocessing.edna_eligibility import evaluate_analysis_eligibility
from retrieval.source_scope import EvidenceScope
from schema.catalogue_adapter import KEYS, REQUIRED_COLUMNS
from schema.context_catalogue import ListingRequest, _finite_json, canonical_json
from schema.research_experiments import ExperimentProposal, MAX_INPUT_BYTES
from schema.scientific_catalogue import INDEX_OBJECT_ID

VERSION = "c22-frozen-experiment-export-v1"
MACHINE_VERSION = "c22-lossless-machine-table-v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_SHA = re.compile(r"^[a-f0-9]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class FrozenExperimentExportError(ValueError):
    """Safe refusal; never disclose source contents in errors."""
    def __init__(self, reason="export_unavailable"):
        self.reason = self.code = reason
        super().__init__(reason)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return canonical_bytes(value)


def _machine_value(value):
    # Do not use browser JSON validation: scientific int64 is exact in these
    # private bytes, including values outside JavaScript's safe integer range.
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int and -(2**63) <= value < 2**63:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_machine_value(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _machine_value(item) for key, item in value.items()}
    raise FrozenExperimentExportError("export_non_lossless_value")


def machine_table_bytes(*, columns, rows, scientific_support=None):
    """Versioned canonical machine JSON, with no CSV or browser normalization."""
    if (type(columns) is not list or not columns or len(set(columns)) != len(columns)
            or any(type(item) is not str for item in columns)
            or type(rows) is not list
            or any(type(row) is not dict or set(row) != set(columns) for row in rows)):
        raise FrozenExperimentExportError("export_invalid_table")
    value = {"version": MACHINE_VERSION, "columns": columns, "rows": rows}
    if scientific_support is not None:
        value["scientific_support"] = scientific_support
    return _canonical(_machine_value(value))


@dataclass(frozen=True)
class SourcePublicationDecision:
    """Trusted explicit host decision; a source generation label is insufficient."""
    child_snapshot_id: str
    dataset_id: str
    source_id: str
    publication_generation: str
    object_sha256: Mapping[str, str]
    decision_reference: str
    eligible: bool = True
    test_only: bool = False

    def __post_init__(self):
        if (not _SHA.fullmatch(self.child_snapshot_id) or not self.dataset_id or not self.source_id
                or not self.publication_generation or not self.decision_reference
                or type(self.eligible) is not bool or type(self.test_only) is not bool
                or not isinstance(self.object_sha256, Mapping) or not self.object_sha256
                or any(not isinstance(key, str) or not _SHA.fullmatch(value)
                       for key, value in self.object_sha256.items())):
            raise ValueError("Explicit publication decision and object identities required")
        object.__setattr__(self, "object_sha256", MappingProxyType(dict(self.object_sha256)))


class PinnedSourcePublicationPolicy:
    """Concrete fail-closed adapter over configured decisions and real C09 bytes.

    Replace the configured policy to withdraw a decision or change its revision.
    No C09 seal/promote audit is interpreted as scientific publication approval.
    """
    def __init__(self, *, policy_id, revision, decisions):
        if not isinstance(policy_id, str) or not policy_id or not isinstance(revision, str) or not revision:
            raise ValueError("Explicit publication policy identity required")
        values = tuple(decisions)
        if any(not isinstance(item, SourcePublicationDecision) for item in values):
            raise ValueError("Typed trusted publication decisions required")
        self.policy_id, self.revision = policy_id, revision
        self.decisions = {self._key(item): item for item in values}
        if len(self.decisions) != len(values):
            raise ValueError("Duplicate publication decision")

    @staticmethod
    def _key(item):
        return (item.child_snapshot_id, item.dataset_id, item.source_id, item.publication_generation)

    def evaluate(self, *, actor, source_manifest, binding, required_objects):
        if not isinstance(actor, CurrentUser):
            raise FrozenExperimentExportError("export_publication_unavailable")
        captures = [item for item in source_manifest.source_captures
                    if item.source_id == binding.source_id and item.source_family == binding.source_family]
        if len(captures) != 1:
            raise FrozenExperimentExportError("export_publication_unavailable")
        capture = captures[0]
        decision = self.decisions.get((binding.snapshot_id, binding.dataset_id,
                                      binding.source_id, capture.publication_generation))
        actual = {item.object_id: item for item in source_manifest.objects}
        if (decision is None or not decision.eligible or not required_objects
                or any(item.object_id not in actual or actual[item.object_id] != item
                       or item.dataset_id != binding.dataset_id or item.source_id != binding.source_id
                       or decision.object_sha256.get(item.object_id) != item.sha256
                       for item in required_objects)):
            raise FrozenExperimentExportError("export_publication_unavailable")
        return {"policy_id": self.policy_id, "policy_revision": self.revision,
                "decision_reference": decision.decision_reference, "test_only": decision.test_only,
                "eligible": True, "child_snapshot_id": binding.snapshot_id,
                "dataset_id": binding.dataset_id, "source_id": binding.source_id,
                "publication_generation": capture.publication_generation,
                "objects": [{"object_id": item.object_id, "sha256": item.sha256,
                             "size_bytes": item.size_bytes} for item in sorted(required_objects, key=lambda item: item.object_id)],
                "independent_scientific_approval": False}


@dataclass(frozen=True, init=False)
class FrozenExperimentExport:
    """Reconstructible exact immutable bytes, defensively detached at boundaries."""
    _manifest_json: str
    _files: Mapping
    input_manifest_sha256: str
    source_sha256: str
    size_bytes: int
    snapshot_ids: tuple[str, ...]

    def __init__(self, *, manifest_json, files):
        try:
            if not isinstance(manifest_json, str) or len(manifest_json.encode()) > MAX_MANIFEST_BYTES:
                raise ValueError
            manifest = json.loads(manifest_json)
            _finite_json(manifest)  # public metadata only; no scientific row values
            if manifest_json != canonical_json(manifest) or manifest["version"] != VERSION:
                raise ValueError
            copied = dict(files)
            descriptors = manifest["files"]
            if (not isinstance(files, Mapping) or not copied or len(copied) > 40
                    or len(descriptors) != len(copied)
                    or {item["name"] for item in descriptors} != set(copied)
                    or any(not _NAME.fullmatch(name) or type(raw) is not bytes for name, raw in copied.items())):
                raise ValueError
            for item in descriptors:
                if set(item) != {"name", "sha256", "size_bytes", "kind"}:
                    raise ValueError
                raw = copied[item["name"]]
                if type(item["size_bytes"]) is not int or item["size_bytes"] != len(raw) or item["sha256"] != _hash(raw):
                    raise ValueError
            limit = manifest["max_input_bytes"]
            if type(limit) is not int or not 1 <= limit <= MAX_INPUT_BYTES:
                raise ValueError
            size = len(manifest_json.encode()) + sum(map(len, copied.values()))
            if size > limit:
                raise FrozenExperimentExportError("export_input_size_exceeded")
            snapshots = manifest["snapshot_ids"]
            if (not isinstance(snapshots, list) or snapshots != sorted(set(snapshots))
                    or any(not _SHA.fullmatch(item) for item in snapshots)
                    or manifest["binding"]["snapshot_id"] not in snapshots
                    or not _SHA.fullmatch(manifest["source_sha256"])):
                raise ValueError
            if (manifest["source_sha256"] != _hash(_canonical(manifest["sources"]))
                    or snapshots != sorted({manifest["binding"]["snapshot_id"],
                        *(item["child_snapshot_id"] for item in manifest["sources"]["datasets"])})):
                raise ValueError
        except FrozenExperimentExportError:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
            raise FrozenExperimentExportError("export_integrity") from None
        for name, value in {"_manifest_json": manifest_json, "_files": MappingProxyType(copied),
                "input_manifest_sha256": _hash(manifest_json.encode()), "source_sha256": manifest["source_sha256"],
                "size_bytes": size, "snapshot_ids": tuple(snapshots)}.items():
            object.__setattr__(self, name, value)

    @property
    def manifest_json(self):
        return self._manifest_json

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def files(self):
        return self._files


class FrozenExperimentExporter:
    def __init__(self, *, store, catalogue, registrations, publication_policy=None):
        if (not isinstance(catalogue, CatalogueService)
                or not isinstance(catalogue.resolver, FrozenCatalogueResolver)
                or catalogue.resolver.store is not store or not isinstance(registrations, Mapping)
                or dict(registrations) != catalogue.resolver.registrations
                or publication_policy is not None and not callable(getattr(publication_policy, "evaluate", None))):
            raise ValueError("Explicit same-store C13/C14 dependencies required")
        self.store, self.catalogue, self.registrations = store, catalogue, dict(registrations)
        self.publication_policy = publication_policy

    def _load(self, frozen, user):
        if not isinstance(user, CurrentUser):
            raise FrozenExperimentExportError("export_access_changed")
        sid = frozen["snapshot_id"]
        registered = self.registrations.get(sid)
        if registered is None:
            raise FrozenExperimentExportError("export_unavailable")
        registered.require_current(self.store)
        resolved = self.catalogue.resolver.resolve(user, sid)
        adapter = getattr(resolved.backend, "adapter", None)
        if not isinstance(adapter, FrozenScientificCatalogueAdapter) or adapter.store is not self.store:
            raise FrozenExperimentExportError("export_unavailable")
        scope = EvidenceScope.model_validate(frozen["context"]["scope"])
        request = ListingRequest(snapshot_id=sid, scope=scope,
            access_binding=catalogue_access_binding(user), access_revision=resolved.revision)
        witnesses = []
        for reference in frozen["context"]["pins"]:
            if reference["kind"] == "artifact":
                witnesses.append(project_pin(reference, None))
            else:
                details = self.catalogue.open({"snapshot_id": sid, "scope": scope.model_dump(mode="json"),
                                               "object_id": reference["id"], "include_details": True}, user)
                witnesses.append(project_pin(reference, details))
        # This neutral question exercises ONLY existing pin intersection rules.
        # It does not interpret or validate the experimental proposal question.
        resolution = resolve_scope(frozen, "Count all datasets", witnesses)
        if resolution.status != "ready":
            raise FrozenExperimentExportError("export_unsupported_pin")
        request = request.model_copy(update={"scope": EvidenceScope.model_validate(resolution.effective_scope)})
        context = adapter._load(request)
        return resolved.revision, context, resolution

    def _publication(self, binding, objects, user):
        if self.publication_policy is None:
            raise FrozenExperimentExportError("export_publication_unavailable")
        manifest, _ = self.store.read(binding.snapshot_id)
        captures = [item for item in manifest.source_captures if item.source_id == binding.source_id
                    and item.source_family == binding.source_family]
        if len(captures) != 1:
            raise FrozenExperimentExportError("export_publication_unavailable")
        witness = self.publication_policy.evaluate(actor=user, source_manifest=manifest,
            binding=binding, required_objects=tuple(objects))
        # A trusted callback must still return the exact scientific identity.
        expected = {"child_snapshot_id": binding.snapshot_id, "dataset_id": binding.dataset_id,
                    "source_id": binding.source_id, "objects": [{"object_id": item.object_id,
                    "sha256": item.sha256, "size_bytes": item.size_bytes}
                    for item in sorted(objects, key=lambda item: item.object_id)]}
        if (not isinstance(witness, dict) or witness.get("eligible") is not True
                or witness.get("independent_scientific_approval") is not False
                or witness.get("publication_generation") != captures[0].publication_generation
                or any(witness.get(key) != value for key, value in expected.items())
                or any(not isinstance(witness.get(key), str) or not witness[key]
                       for key in ("policy_id", "policy_revision", "decision_reference", "publication_generation"))
                or type(witness.get("test_only")) is not bool):
            raise FrozenExperimentExportError("export_publication_unavailable")
        _finite_json(witness)
        return witness

    def freeze(self, *, frozen, proposal, user):
        try:
            return self._freeze(frozen=frozen, proposal=proposal, user=user)
        except FrozenExperimentExportError:
            raise
        except Exception:
            raise FrozenExperimentExportError() from None

    def _freeze(self, *, frozen, proposal, user):
        proposal = ExperimentProposal.model_validate(proposal.model_dump(mode="json")
            if isinstance(proposal, ExperimentProposal) else proposal)
        revision, context, resolution = self._load(frozen, user)
        scope = EvidenceScope.model_validate(resolution.effective_scope)
        files, table_descriptors, sources, selected_rows, exclusion_ledger = {}, [], {}, {}, []
        selected_datasets, selected_analyses = set(), set()
        exclusions = {}
        for item in proposal.cohort.exclusions:
            exclusions.setdefault(item.dataset_id, []).append(item)
        publication_pins = {item.constraints["analysis"]["id"] for item in resolution.pins
                            if item.constraints.get("kind") == "publication"}
        for ordinal, selection in enumerate(proposal.cohort.selections):
            if selection.kind == "dataset":
                if publication_pins:
                    raise FrozenExperimentExportError("export_publication_pin_requires_exact_table")
                if scope.sources.edna_metabarcoding.analysis_id is not None:
                    raise FrozenExperimentExportError("export_analysis_selection_requires_exact_table")
                identity = selection.target_id
                if identity not in context.data or (resolution.allowed_dataset_ids is not None
                        and identity not in resolution.allowed_dataset_ids):
                    raise FrozenExperimentExportError("export_target_unavailable")
                data, binding = context.data[identity], context.bindings[identity]
                method = resolution.restrictions.get("metagenome", {}).get("method")
                if data.metadata.family == "metagenome" and method and selection.table != {
                        "Kraken": "kraken_abundance", "MetaEuk": "metaeuk_abundance"}.get(method):
                    raise FrozenExperimentExportError("export_unsupported_pin")
                frames, native_ledger = _native_frames(data, scope, resolution.restrictions)
                if identity not in selected_datasets:
                    exclusion_ledger.extend({"dataset_id": identity, **item} for item in native_ledger)
                    _exclude(data.metadata.family, frames, exclusions.get(identity, ()), exclusion_ledger)
                else:
                    _exclude(data.metadata.family, frames, exclusions.get(identity, ()), [])
                selected_datasets.add(identity)
                if selection.table not in frames:
                    raise FrozenExperimentExportError("export_table_unavailable")
                spec = _table_spec(data.metadata, selection.table)
                _complete(spec)
                frame = frames[selection.table]
                key = _row_key(data.metadata.family, selection.table)
                ids = frame[key].tolist()
                objects = _required_objects(data, selection.table)
                source = self._source(binding, objects, user)
                previous = sources.get(identity)
                if previous:
                    all_objects = {item["object_id"] for item in previous["objects"]} | {item.object_id for item in objects}
                    objects = tuple(item for item in data.objects if item.object_id in all_objects)
                    source = self._source(binding, objects, user)
                sources[identity] = source
                source_rows, source_schema = self._source_rows(binding, spec.object_id, key, ids)
                declared = list(source_rows[0]) if source_rows else list(data.tables[selection.table].columns)
                mandatory = _mandatory(data.metadata.family, selection.table, declared)
                columns = _columns(selection.columns, mandatory, declared)
                rows = [{name: row[name] for name in columns} for row in source_rows]
                column_schema = [item for item in source_schema if item["name"] in columns]
                support = self._support(binding, data, frames, selection.table)
                selected_rows.setdefault(identity, set()).update(ids)
                metadata = _metadata(data.metadata, spec, columns)
                descriptor = {"kind": "dataset", "target_id": identity, "table": selection.table,
                    "source_snapshot_id": binding.snapshot_id, "source_object_id": spec.object_id,
                    "entity": metadata["entity"], "scientific_metadata": metadata,
                    "scope": scope.canonical(), "restrictions": resolution.restrictions.get(data.metadata.family, {})}
            else:
                analysis = context.analyses.get(selection.target_id)
                if (analysis is None or publication_pins and publication_pins != {analysis.id}
                        or resolution.allowed_dataset_ids is not None
                        and not set(analysis.input_dataset_ids) <= resolution.allowed_dataset_ids):
                    raise FrozenExperimentExportError("export_target_unavailable")
                if proposal.cohort.exclusions:
                    raise FrozenExperimentExportError("export_published_rows_cannot_be_recomputed")
                compatibility = _compatible(context, analysis, proposal.question, scope)
                spec = next((item for item in analysis.tables if item.name == selection.table), None)
                _complete(spec)
                source_rows = context.registry.tables[spec.object_id]
                declared = [item.key for item in spec.columns]
                columns = _columns(selection.columns, (), declared)
                rows = [{name: row[name] for name in columns} for row in source_rows]
                column_schema = [{"name": name, "encoding": "canonical_json_value",
                    "types_seen": sorted({_primitive_type(row[name]) for row in source_rows}),
                    "nullable": any(row[name] is None for row in source_rows)} for name in columns]
                support = None
                selected_analyses.add(analysis.id)
                for identity in analysis.input_dataset_ids:
                    data, binding = context.data[identity], context.bindings[identity]
                    sources[identity] = self._source(binding, data.objects, user)
                    selected_datasets.add(identity)
                descriptor = {"kind": "published_analysis", "target_id": analysis.id,
                    "table": selection.table, "source_snapshot_id": frozen["snapshot_id"],
                    "source_object_id": spec.object_id, "entity": "published_result_rows",
                    "scientific_metadata": {"analysis": analysis.model_dump(mode="json"),
                        "table": spec.model_dump(mode="json"), "scope_compatibility": compatibility},
                    "scope": scope.canonical(), "restrictions": {}}
            filename = f"table-{ordinal + 1:02d}.json"
            files[filename] = machine_table_bytes(columns=columns, rows=rows, scientific_support=support)
            descriptor.update(file=filename, row_count=len(rows), requested_columns=list(selection.columns),
                effective_columns=columns, column_schema=column_schema, machine_encoding=MACHINE_VERSION)
            table_descriptors.append(descriptor)
            if sum(map(len, files.values())) > proposal.resources.max_input_bytes:
                raise FrozenExperimentExportError("export_input_size_exceeded")
        if set(exclusions) - selected_datasets:
            raise FrozenExperimentExportError("export_exclusion_target_unavailable")
        pairing = _pairing(context, proposal.cohort.pairing, selected_rows)
        files["exclusions.json"] = _canonical({"version": VERSION, "rows": exclusion_ledger})
        files["pairing.json"] = _canonical(pairing)
        index_manifest, _ = self.store.read(frozen["snapshot_id"])
        index_objects = {item.object_id: item for item in index_manifest.objects}
        selected_index = [index_objects[INDEX_OBJECT_ID]]
        for descriptor in table_descriptors:
            if descriptor["kind"] == "published_analysis":
                selected_index.append(index_objects[descriptor["source_object_id"]])
        index_sources = [{"object_id": item.object_id, "sha256": item.sha256, "size_bytes": item.size_bytes}
                         for item in sorted({item.object_id: item for item in selected_index}.values(), key=lambda item: item.object_id)]
        source_domain = {"index_snapshot_id": frozen["snapshot_id"], "index_objects": index_sources,
                         "datasets": [sources[key] for key in sorted(sources)]}
        binding = {key: frozen[key] for key in ("investigation_id", "conversation_id", "revision_id", "snapshot_id", "payload_sha256")}
        manifest = {"version": VERSION, "binding": binding, "question": proposal.question,
            "question_interpretation": "explicit_typed_cohort; published_tables_require_C01_exact_question",
            "proposal_sha256": _hash(_canonical(proposal.model_dump(mode="json"))),
            "catalogue_policy_revision": revision, "actor_binding": catalogue_access_binding(user),
            "scope": scope.canonical(), "pins": [item.reference for item in resolution.pins],
            "pin_witnesses": [{"sha256": item.sha256, "constraints": item.constraints} for item in resolution.pins],
            "pin_limitations": list(resolution.limitations),
            "attachments": frozen["context"]["attachments"],
            "attachment_use": "supplementary_only; no implicit scientific inputs",
            "cohort": proposal.cohort.model_dump(mode="json"), "tables": table_descriptors,
            "sources": source_domain, "source_sha256": _hash(_canonical(source_domain)),
            "snapshot_ids": sorted({frozen["snapshot_id"], *(item["child_snapshot_id"] for item in sources.values())}),
            "max_input_bytes": proposal.resources.max_input_bytes,
            "files": [{"name": name, "sha256": _hash(raw), "size_bytes": len(raw),
                       "kind": "machine_table" if name.startswith("table-") else "scientific_sidecar"}
                      for name, raw in sorted(files.items())],
            "authority": "experimental", "independent_scientific_approval": False,
            "execution_performed": False}
        _finite_json(manifest)
        exported = FrozenExperimentExport(manifest_json=canonical_json(manifest), files=files)
        if exported.size_bytes + len(proposal.python_code.encode()) > proposal.resources.max_input_bytes:
            raise FrozenExperimentExportError("export_input_size_exceeded")
        self.verify_access(frozen=frozen, proposal=proposal, user=user, exported=exported)
        return exported

    def _source(self, binding, objects, user):
        witness = self._publication(binding, objects, user)
        manifest, _ = self.store.read(binding.snapshot_id)
        capture = next(item for item in manifest.source_captures if item.source_id == binding.source_id)
        return {"dataset_id": binding.dataset_id, "source_id": binding.source_id,
            "source_family": binding.source_family, "child_snapshot_id": binding.snapshot_id,
            "objects": witness["objects"], "publication": witness,
            "source_capture": capture.model_dump(mode="json"),
            "object_provenance": [item.model_dump(mode="json") for item in sorted(objects, key=lambda item: item.object_id)]}

    def _source_rows(self, binding, object_id, key, ids):
        _, payloads = self.store.read(binding.snapshot_id)
        arrow = pq.read_table(BytesIO(payloads[object_id]))
        rows = arrow.to_pylist()
        lookup = {item[key]: item for item in rows}
        if len(lookup) != len(rows) or len(set(ids)) != len(ids) or any(identity not in lookup for identity in ids):
            raise FrozenExperimentExportError("export_integrity")
        schema = [{"name": field.name, "arrow_type": str(field.type), "nullable": field.nullable}
                  for field in arrow.schema]
        return [lookup[identity] for identity in ids], schema

    def _support(self, binding, data, frames, table):
        """Exact required FK metadata, not extra measurements or implicit joins."""
        family = data.metadata.family
        dependencies = {}
        if family in {"ctd", "metagenome"}:
            anchor = "casts" if family == "ctd" else "collections"
            key = "cast_id" if family == "ctd" else "library_id"
            if table != anchor:
                dependencies[anchor] = frames[anchor].loc[frames[anchor][key].isin(frames[table][key])]
        elif family == "edna_metabarcoding":
            assays, occurrences = frames["assays"], frames["occurrences"]
            if table == "detections":
                assays = assays.loc[assays.assay_id.isin(frames[table].assay_id)]
                occurrences = occurrences.loc[occurrences.sample_id.isin(assays.sample_id)]
            elif table == "assays":
                occurrences = occurrences.loc[occurrences.sample_id.isin(assays.sample_id)]
            dependencies = {"occurrences": occurrences,
                "classifications": frames["classifications"].loc[frames["classifications"].sample_id.isin(occurrences.sample_id)],
                "assays": assays.loc[assays.sample_id.isin(occurrences.sample_id)]}
            dependencies.pop(table, None)
        result = []
        for name, frame in dependencies.items():
            spec = _table_spec(data.metadata, name)
            _complete(spec)
            rows, schema = self._source_rows(binding, spec.object_id, _row_key(family, name),
                                            frame[_row_key(family, name)].tolist())
            result.append({"table": name, "purpose": "source-owned identity/date/classification/protocol qualification",
                "columns": [item["name"] for item in schema], "column_schema": schema, "rows": rows})
        return result

    def verify_access(self, *, frozen, proposal, user, exported):
        """Fresh visibility/pin/publication check without rematerializing row files."""
        try:
            proposal = ExperimentProposal.model_validate(proposal.model_dump(mode="json")
                if isinstance(proposal, ExperimentProposal) else proposal)
            retained = FrozenExperimentExport(manifest_json=exported.manifest_json, files=exported.files)
            manifest = retained.manifest
            revision, context, resolution = self._load(frozen, user)
            if (manifest["binding"] != {key: frozen[key] for key in manifest["binding"]}
                    or manifest["proposal_sha256"] != _hash(_canonical(proposal.model_dump(mode="json")))
                    or manifest["catalogue_policy_revision"] != revision
                    or manifest["actor_binding"] != catalogue_access_binding(user)
                    or manifest["scope"] != resolution.effective_scope):
                raise FrozenExperimentExportError("export_access_changed")
            for source in manifest["sources"]["datasets"]:
                identity = source["dataset_id"]
                if identity not in context.data:
                    raise FrozenExperimentExportError("export_access_changed")
                data = context.data[identity]
                objects = {item.object_id: item for item in data.objects}
                requested = [objects[item["object_id"]] for item in source["objects"]]
                if self._source(context.bindings[identity], requested, user) != source:
                    raise FrozenExperimentExportError("export_publication_changed")
            for table in manifest["tables"]:
                if table["kind"] == "published_analysis" and table["target_id"] not in context.analyses:
                    raise FrozenExperimentExportError("export_access_changed")
            return None
        except FrozenExperimentExportError:
            raise
        except Exception:
            raise FrozenExperimentExportError("export_access_changed") from None

    def verify(self, *, frozen, proposal, user, exported):
        """Recompute the complete deterministic export under current authority."""
        actual = self.freeze(frozen=frozen, proposal=proposal, user=user)
        if actual.manifest_json != exported.manifest_json or actual.files != exported.files:
            raise FrozenExperimentExportError("export_integrity")


def _table_spec(metadata, table):
    return metadata.table if metadata.family == "remote_sensing" and table == "observations" else next(
        (item for item in getattr(metadata, "tables", ()) if item.name == table), None)


def _complete(spec):
    if (spec is None or spec.object_id is None or spec.completeness != "complete"
            or spec.availability.status != "available"):
        raise FrozenExperimentExportError("export_complete_table_required")


def _row_key(family, table):
    return "observation_id" if family == "remote_sensing" else EDNA_KEYS[table] if family == "edna_metabarcoding" else KEYS[table]


def _required_objects(data, table):
    # Selector dependencies are retained identities even when only one numeric
    # table is exported. They do not leak the bytes of unrequested columns.
    family = data.metadata.family
    roles = {table}
    if family in {"ctd", "metagenome"}:
        roles.add("casts" if family == "ctd" else "collections")
    elif family == "edna_metabarcoding":
        roles.update(EDNA_KEYS)
    ids = {_table_spec(data.metadata, name).object_id for name in roles}
    table_ids = {item.object_id for item in getattr(data.metadata, "tables", ())}
    if family == "remote_sensing":
        table_ids = {data.metadata.table.object_id}
    return tuple(item for item in data.objects if item.object_id in ids or item.object_id not in table_ids)


def _native_frames(data, scope, restrictions):
    metadata, family = data.metadata, data.metadata.family
    fixed = restrictions.get(family, {})
    if family in {"ctd", "metagenome"}:
        frames = {item.name: _scoped(data, scope, item.name) for item in metadata.tables
                  if item.object_id is not None}
        return frames, []
    if family == "remote_sensing":
        if any(getattr(metadata.descriptor, name, None) != value for name, value in fixed.items()):
            raise FrozenExperimentExportError("export_unsupported_pin")
        return {"observations": sst_select(data, scope)}, []
    if fixed.get("protocol_id") or fixed.get("raw_assignment_method"):
        raise FrozenExperimentExportError("export_unsupported_pin")
    for spec in metadata.tables:
        _complete(spec)
    raw = edna_select(data, scope, EDNAParameters(population="raw"))
    frames = edna_select(data, scope, EDNAParameters(population="eligible"))
    methods = scope.sources.edna_metabarcoding.filters.assignment_method
    methods = (methods,) if methods else SCIENTIFIC_METHODS
    observed = {}
    for row in data.tables["detections"].loc[data.tables["detections"].active.eq(True)].itertuples():
        observed.setdefault(row.assay_id, set()).add(row.assignment_method)
    ledger = []
    for row in raw["occurrences"].to_dict("records"):
        assays = raw["assays"].loc[raw["assays"].sample_id.eq(row["sample_id"])].to_dict("records")
        availability = {item["assay_id"]: set(parse_community_availability(item["community_availability_json"]))
                        | observed.get(item["assay_id"], set()) for item in assays}
        eligibility = evaluate_analysis_eligibility(row, assays, availability, methods)
        ledger.append({"origin": "C01_scientific_eligibility", "entity": "source_occurrence",
                       "id": row["sample_id"], **eligibility})
    return frames, ledger


def _exclude(family, frames, exclusions, ledger):
    expected, anchor, key = {"ctd": ("cast", "casts", "cast_id"),
        "metagenome": ("library", "collections", "library_id"),
        "remote_sensing": ("sst_observation", "observations", "observation_id"),
        "edna_metabarcoding": ("source_occurrence", "occurrences", "sample_id")}[family]
    ids = set()
    for item in exclusions:
        if item.entity != expected or not set(item.ids) <= set(frames[anchor][key]):
            raise FrozenExperimentExportError("export_exclusion_outside_cohort")
        ids.update(item.ids)
        ledger.extend({"dataset_id": item.dataset_id, "origin": "explicit_user_exclusion",
                       "entity": expected, "id": identity, "reason": item.reason} for identity in item.ids)
    if not ids:
        return
    frames[anchor] = frames[anchor].loc[~frames[anchor][key].isin(ids)]
    if family in {"ctd", "metagenome"}:
        for name in frames:
            if name != anchor:
                frames[name] = frames[name].loc[~frames[name][key].isin(ids)]
    elif family == "edna_metabarcoding":
        frames["classifications"] = frames["classifications"].loc[~frames["classifications"].sample_id.isin(ids)]
        frames["assays"] = frames["assays"].loc[~frames["assays"].sample_id.isin(ids)]
        frames["detections"] = frames["detections"].loc[frames["detections"].assay_id.isin(frames["assays"].assay_id)]


def _mandatory(family, table, columns):
    if family in {"ctd", "metagenome"}:
        return list(REQUIRED_COLUMNS[table])
    # SST status/support/quality and canonical eDNA provenance/classification/
    # protocol/method columns are scientific qualifiers, not optional labels.
    return columns


def _columns(requested, mandatory, declared):
    if not set(requested) <= set(declared):
        raise FrozenExperimentExportError("export_unknown_column")
    wanted = set(requested) | set(mandatory)
    return [name for name in declared if name in wanted]


def _primitive_type(value):
    return "null" if value is None else {str: "string", bool: "boolean", int: "integer",
        float: "number", list: "array", dict: "object"}.get(type(value), "unsupported")


def _metadata(metadata, spec, columns):
    value = metadata.model_dump(mode="json")
    # Tables not selected are not exported. Dataset-level scientific metadata
    # remains exact, including precision, depth sign, product and qualifications.
    value.pop("tables", None)
    value.pop("table", None)
    value.pop("related_ids", None)
    table = spec.model_dump(mode="json")
    if "columns" in table:
        table["columns"] = [item for item in table["columns"] if item["name"] in columns]
    family = metadata.family
    entity = getattr(spec, "entity", None) or (
        metadata.observation_entity if family == "remote_sensing" else
        {"occurrences": "source_occurrences", "classifications": "source_occurrence_classifications",
         "assays": "assays", "detections": "assignment_rows"}[spec.name])
    value.update(table=table, entity=entity)
    if family == "edna_metabarcoding":
        value.update(population="eligible", counting_entities={"sample_id": "source_occurrence",
            "assay_id": "assay", "detection_id": "assignment_row"},
            units={"read_count": "sequence_reads; not organism abundance", "copies_per_ml": "copies/mL",
                   "lat": "degrees_north", "lon": "degrees_east"},
            eligibility_policy="C01 evaluate_analysis_eligibility; active complete environmental target assays")
    elif family == "remote_sensing":
        value["units"] = {"value": metadata.descriptor.unit, "uncertainty": metadata.descriptor.unit,
            "lat": "degrees_north", "lon": "degrees_east", "valid_fraction": "fraction",
            "valid_ocean_pixels": "pixels", "ocean_pixels": "pixels"}
    return value


def _compatible(context, analysis, question, scope):
    if analysis.scope_option is None or analysis.scope.canonical() != scope.canonical():
        raise FrozenExperimentExportError("export_publication_question_unsupported")
    protocol_id, automatic = resolve_protocol(analysis.scope_option, question)
    if automatic and len(analysis.scope_option.get("protocol_ids", [])) != 1:
        protocol_id = None
    candidates = []
    for workflow in context.registry.metadata.workflows:
        if analysis.id in workflow.analysis_ids and workflow.id in context.records and workflow.availability.status == "available":
            result = publication_compatibility(question, workflow.workflow_kind, analysis.scope_option,
                                               protocol_id=protocol_id, scope=scope.canonical())
            if result.outcome == "compatible":
                candidates.append(result.as_dict())
    distinct = {canonical_json(item): item for item in candidates}
    if len(distinct) != 1:
        raise FrozenExperimentExportError("export_publication_question_unsupported")
    return next(iter(distinct.values()))


def _pairing(context, pairing, selected_rows):
    result = {"version": VERSION, "mode": pairing.mode, "relationships": [], "comparison_authorized": False}
    for identity in pairing.relationship_ids:
        record, proof = context.records.get(identity), context.relationships.get(identity)
        if (record is None or proof is None or record.category != "verified_physical_identity"
                or record.comparison_authorized is not False
                or any(endpoint.entity_id not in selected_rows.get(endpoint.dataset_id, ()) for endpoint in record.endpoints)):
            raise FrozenExperimentExportError("export_physical_pairing_unavailable")
        result["relationships"].append({"record": record.model_dump(mode="json"), "validated_proof": proof})
    return result
