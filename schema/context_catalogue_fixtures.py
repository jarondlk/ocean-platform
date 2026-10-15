"""Synthetic, local-only catalogue acceptance fixtures for C08 and later components.

This in-memory oracle is not a catalogue service, source adapter, access service,
or snapshot store. Callers supply a trusted fixture access context. No data,
network, credentials or application configuration is read. Documentary ranks are
only fixture annotations and never participate in catalogue membership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Iterator

from retrieval.source_scope import EvidenceScope, FAMILIES, document_matches
from schema.context_catalogue import CatalogueNode, canonical_json, ordered_nodes


@dataclass(frozen=True)
class FixtureAccess:
    subject_id: str = "researcher-a"
    revision: str = "permissions-1"
    denied_ids: frozenset[str] = frozenset()

    @property
    def binding(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {"subject": self.subject_id, "denied": sorted(self.denied_ids)}
            ).encode()
        ).hexdigest()


@dataclass(frozen=True)
class FixtureRecord:
    node: CatalogueNode
    observation: dict = field(default_factory=dict)
    subjects: frozenset[str] | None = None
    withdrawn: bool = False
    documentary_rank: int | None = None


def fixture_scope(source_family: str | None = None, **filters) -> EvidenceScope:
    """Reuse the source-owned scope rather than invent a fixture query dialect."""
    return EvidenceScope.model_validate(
        {
            "version": 1,
            "sources": {
                family: {
                    "enabled": source_family is None or family == source_family,
                    "filters": filters if family == source_family else {},
                }
                for family in FAMILIES
            },
        }
    )


@dataclass
class SyntheticCatalogue:
    snapshot_id: str
    records: dict[str, FixtureRecord]
    edges: dict[str, tuple[str, ...]]
    private_experiments: tuple[str, ...] = ("synthetic:private-experiment",)

    def permitted(self, node_id: str, access: FixtureAccess) -> bool:
        """Re-evaluate current access, including ancestors, before metadata/counts."""
        seen = set()
        while node_id:
            if node_id in seen:
                raise ValueError("Fixture ancestry cycle")
            seen.add(node_id)
            record = self.records.get(node_id)
            if (
                record is None
                or record.withdrawn
                or node_id in access.denied_ids
                or record.node.membership == "private"
                or record.subjects is not None
                and access.subject_id not in record.subjects
            ):
                return False
            node_id = record.node.parent_id
        return True

    def open(self, node_id: str, access: FixtureAccess):
        if not self.permitted(node_id, access):
            return None
        node = self.records[node_id].node
        return node.model_copy(
            update={
                "related_ids": [
                    key for key in node.related_ids if self.permitted(key, access)
                ]
            }
        )

    def descendants(self, node_id: str | None, access: FixtureAccess) -> set[str]:
        if node_id is None:
            return {key for key in self.records if self.permitted(key, access)}
        if not self.permitted(node_id, access):
            return set()
        result, pending = set(), list(self.edges.get(node_id, ()))
        while pending:
            key = pending.pop()
            if key in result or key == node_id or not self.permitted(key, access):
                continue
            result.add(key)
            pending.extend(self.edges.get(key, ()))
        return result

    def matching_ids(
        self, request, access: FixtureAccess, *, recursive=False
    ) -> list[str]:
        """Exhaustive fixture inventory; no top-k or page slice enters selection."""
        self._check_context(request, access)
        candidates = (
            self.descendants(request.parent_id, access)
            if recursive or request.parent_id is None
            else {
                key
                for key in self.edges.get(request.parent_id, ())
                if self.permitted(request.parent_id, access)
                and self.permitted(key, access)
            }
        )
        filters = request.filters
        matches = []
        scope = request.scope.canonical()
        for key in candidates:
            record = self.records[key]
            node = record.node
            if filters.roots and node.root not in filters.roots:
                continue
            if filters.kinds and node.kind not in filters.kinds:
                continue
            if (
                filters.source_families
                and node.source_family not in filters.source_families
            ):
                continue
            if filters.authorities and node.authority not in filters.authorities:
                continue
            if (
                filters.search
                and filters.search.casefold()
                not in (key + " " + node.title.en + " " + node.title.ja).casefold()
            ):
                continue
            if node.source_family is not None and not document_matches(
                record.observation, scope
            ):
                continue
            matches.append(key)
        return [
            node.id
            for node in ordered_nodes(
                [self.records[key].node for key in matches], request.ordering
            )
        ]

    def _check_context(self, request, access: FixtureAccess):
        if request.snapshot_id != self.snapshot_id:
            raise ValueError("Fixture snapshot mismatch")
        if (
            request.access_binding != access.binding
            or request.access_revision != access.revision
        ):
            raise ValueError("Current access context mismatch")

    def dataset_count(self, request, access: FixtureAccess):
        from schema.context_catalogue import CatalogueCount

        identities = self.matching_ids(request, access, recursive=True)
        return CatalogueCount(
            state="known",
            entity="datasets",
            denominator="all matching permitted canonical datasets",
            value=sum(self.records[key].node.kind == "dataset" for key in identities),
        )

    def list(self, request, access: FixtureAccess):
        matches = self.matching_ids(request, access)
        return self._page(request, matches, access)

    def _page(self, request, matches, access):
        from schema.context_catalogue import (
            CatalogueCount,
            CatalogueListing,
            make_cursor,
            validate_cursor,
        )

        offset = validate_cursor(request) if request.cursor is not None else 0
        selected = matches[offset : offset + request.limit]
        following = offset + len(selected)
        next_cursor = (
            make_cursor(request, following) if following < len(matches) else None
        )
        return CatalogueListing(
            request=request,
            items=[self.open(key, access) for key in selected],
            total=CatalogueCount(
                state="known",
                entity="canonical_objects",
                denominator="all matching permitted canonical descendants",
                value=len(matches),
            ),
            returned_count=len(selected),
            next_cursor=next_cursor,
            preview_truncated=next_cursor is not None,
            source_completeness="complete",
            query_completion="complete",
            availability={"status": "available"},
        )

    def pages(self, request, access: FixtureAccess) -> Iterator:
        """Traverse an immutable fixture view using actual request/page envelopes.

        Resolve one reference inventory, then slice it for scale acceptance. This
        measures neither a service implementation nor production authorization.
        Each new call obtains current FixtureAccess before membership/counts.
        """
        matches = self.matching_ids(request, access)
        while True:
            self._check_context(request, access)
            page = self._page(request, matches, access)
            yield page
            if page.next_cursor is None:
                return
            request = request.model_copy(update={"cursor": page.next_cursor})

    def dataset_result(self, request, access: FixtureAccess, *, preview_limit=100):
        """Synthetic reference query receipt; preview never defines full membership."""
        from schema.context_catalogue import QueryResult

        if type(preview_limit) is not int or not 1 <= preview_limit <= 500:
            raise ValueError("Preview limit must be an integer from 1 to 500")
        keys = [
            key
            for key in self.matching_ids(request, access, recursive=True)
            if self.records[key].node.kind == "dataset"
        ]
        rows = [
            {"dataset_id": key, "source_family": self.records[key].node.source_family}
            for key in keys
        ]
        content_hash = hashlib.sha256(canonical_json(rows).encode()).hexdigest()
        return QueryResult.model_validate(
            {
                "snapshot_id": self.snapshot_id,
                "scope": request.scope,
                "columns": [
                    {
                        "key": "dataset_id",
                        "title": {"en": "Dataset", "ja": "データセット"},
                    },
                    {"key": "source_family", "title": {"en": "Source", "ja": "ソース"}},
                ],
                "rows": rows[:preview_limit],
                "receipt": {
                    "snapshot_id": self.snapshot_id,
                    "scope": request.scope,
                    "receipt_id": "synthetic:receipt:" + content_hash,
                    "operation_id": "catalogue.dataset_inventory",
                    "operation_version": "v1",
                    "inputs": [
                        {
                            "object_id": key,
                            "content_sha256": self.records[
                                key
                            ].node.provenance.content_sha256,
                        }
                        for key in keys
                    ],
                    "parameters": {"entity": "datasets"},
                    "authority": "descriptive",
                    "availability": {"status": "available"},
                    "provenance": {"source_generation": "synthetic-generation-1"},
                    "total_rows": {
                        "state": "known",
                        "entity": "datasets",
                        "denominator": "all matching permitted canonical datasets",
                        "value": len(keys),
                    },
                    "returned_count": min(preview_limit, len(keys)),
                    "preview_truncated": len(keys) > preview_limit,
                    "source_completeness": "complete",
                    "query_completion": "complete",
                    "content_sha256": content_hash,
                },
            }
        )


def _node(
    snapshot_id: str,
    node_id: str,
    kind: str,
    root: str,
    parent_id: str | None,
    *,
    family: str | None = None,
    title: str | None = None,
    descriptor=None,
    **overrides,
):
    """Every fixture passes the same public validation used by future producers."""
    from schema.context_catalogue import DATASET_SECTIONS

    payload = dict(
        snapshot_id=snapshot_id,
        id=node_id,
        kind=kind,
        root=root,
        parent_id=parent_id,
        title={"en": title or node_id, "ja": title or "合成データ"},
        purpose={
            "en": "Synthetic catalogue acceptance fixture",
            "ja": "合成カタログ検証用",
        },
        scope=fixture_scope(family),
        availability={"status": "available"},
        authority="descriptive",
        lifecycle={
            "ingestion": "complete",
            "publication": "published",
            "scientific_approval": "not_reviewed",
            "query_readiness": "ready",
            "embedding_readiness": "not_ready",
        },
        provenance={
            "source_generation": "synthetic-generation-1",
            "content_sha256": hashlib.sha256(node_id.encode()).hexdigest(),
        },
        source_family=family,
        descriptor=descriptor,
        sections=list(DATASET_SECTIONS) if kind == "dataset" else [],
        operations=[
            {
                "id": "catalogue.count",
                "version": "v1",
                "kind": "inventory",
                "required_permission": "catalogue.read",
                "availability": {"status": "available"},
            }
        ],
    )
    payload.update(overrides)
    return CatalogueNode.model_validate(payload)


def _descriptor(family: str) -> dict:
    return {
        "ctd": {
            "family": "ctd",
            "sampling_contract": "One cast has multiple distinct depth observations",
            "observation_entity": "cast",
            "measurement": "water_temperature",
            "unit": "degC",
            "depth_unit": "m",
        },
        "remote_sensing": {
            "family": "remote_sensing",
            "product_id": "synthetic-mur",
            "product_version": "v1",
            "spatial_resolution": 0.01,
            "spatial_resolution_unit": "degree",
            "temporal_resolution": "daily",
            "measurement": "sea_surface_temperature",
            "unit": "degC",
            "spatial_role": "regional_summary",
        },
        "metagenome": {
            "family": "metagenome",
            "measurement": "relative_abundance",
            "abundance_unit": "fraction",
            "abundance_denominator": "classified reads in one library",
            "method": "MetaEuk",
            "taxonomic_rank": "genus",
            "omitted_taxa": "retained_elsewhere",
        },
        "edna_metabarcoding": {
            "family": "edna_metabarcoding",
            "protocol_id": "synthetic-mifish",
            "protocol": "MiFish synthetic assay",
            "assignment_method": "qcauto_target",
            "sample_kind": "environmental",
            "is_control": False,
            "measurement": "detection_frequency",
            "unit": "detected per eligible assay",
        },
    }[family]


def make_catalogue(
    dataset_count: int = 12,
    *,
    snapshot_id="synthetic-snapshot-1",
    include_edge_cases=True,
) -> SyntheticCatalogue:
    """Generate exactly N public datasets plus roots/directories/reference objects.

    IDs depend only on ordinal, never path/title/rank/snapshot. This is a
    deterministic contract fixture, not a service scalability benchmark.
    """
    from schema.context_catalogue import ROOTS

    if type(dataset_count) is not int or dataset_count < 0:
        raise ValueError("Dataset count must be a nonnegative integer")
    records, edge_lists = {}, {}

    def add(node, *, observation=None, subjects=None, withdrawn=False, rank=None):
        if node.id in records:
            raise ValueError("Duplicate fixture canonical identity")
        records[node.id] = FixtureRecord(
            node, observation or {}, subjects, withdrawn, rank
        )
        if node.parent_id:
            edge_lists.setdefault(node.parent_id, []).append(node.id)
        return node.id

    for root in ROOTS:
        add(_node(snapshot_id, f"root:{root}", "root", root, None))
    for family in FAMILIES:
        add(
            _node(
                snapshot_id,
                f"synthetic:source:{family}",
                "directory",
                "data",
                "root:data",
                family=family,
            ),
            observation={"source_type": family},
        )
    for index in range(dataset_count):
        family = FAMILIES[index % len(FAMILIES)]
        node_id = f"synthetic:dataset:{index:06d}"
        observation = {
            "source_type": family,
            "sample_id": f"sample-{index:06d}",
            "time": "2024-01-15",
            "bay": "O",
            "station": "s1",
            "lat": 38.4,
            "lon": 141.4,
            "dataset_id": "synthetic-mur",
            "provider": "synthetic-provider",
            "provider_project_id": "synthetic-project",
            "assignment_method": "qcauto_target",
            "sample_kind": "environmental",
            "is_control": False,
        }
        add(
            _node(
                snapshot_id,
                node_id,
                "dataset",
                "data",
                f"synthetic:source:{family}",
                family=family,
                title=f"Synthetic dataset {index:06d}",
                descriptor=_descriptor(family),
            ),
            observation=observation,
            rank=index + 1,
        )
    if include_edge_cases:
        # These are local ACL annotations, deliberately outside the public wire node.
        add(
            _node(
                snapshot_id,
                "synthetic:hidden",
                "dataset",
                "data",
                "synthetic:source:ctd",
                family="ctd",
                descriptor=_descriptor("ctd"),
            ),
            subjects=frozenset({"curator"}),
            observation={"source_type": "ctd"},
        )
        add(
            _node(
                snapshot_id,
                "synthetic:revoked",
                "dataset",
                "data",
                "synthetic:source:ctd",
                family="ctd",
                descriptor=_descriptor("ctd"),
            ),
            withdrawn=True,
            observation={"source_type": "ctd"},
        )
        add(
            _node(
                snapshot_id,
                "synthetic:private-experiment",
                "analysis",
                "analyses",
                "root:analyses",
                authority="experimental",
                membership="private",
                owner_id="researcher-a",
                lifecycle={
                    "ingestion": "complete",
                    "publication": "unpublished",
                    "scientific_approval": "not_reviewed",
                    "query_readiness": "ready",
                    "embedding_readiness": "unsupported",
                },
            )
        )
        add(
            _node(
                snapshot_id,
                "synthetic:analysis",
                "analysis",
                "analyses",
                "root:analyses",
                authority="published",
            )
        )
        add(
            _node(
                snapshot_id,
                "synthetic:workflow",
                "workflow",
                "analyses",
                "root:analyses",
            )
        )
        add(
            _node(
                snapshot_id,
                "synthetic:coverage",
                "statistic",
                "statistics",
                "root:statistics",
                availability={
                    "status": "unknown",
                    "reason": "Expected coverage is not yet known",
                },
            )
        )
        add(
            _node(
                snapshot_id, "synthetic:method", "metadata", "metadata", "root:metadata"
            )
        )
        add(
            _node(
                snapshot_id,
                "synthetic:candidate-link",
                "relationship",
                "relationships",
                "root:relationships",
                purpose={
                    "en": "Candidate proximity only; physical identity unverified",
                    "ja": "近接候補。物理的同一性は未確認。",
                },
            )
        )
        add(
            _node(
                snapshot_id,
                "synthetic:unavailable",
                "reference",
                "metadata",
                "root:metadata",
                availability={
                    "status": "unavailable",
                    "reason": "Source has not been ingested",
                },
                lifecycle={
                    "ingestion": "not_ingested",
                    "publication": "unpublished",
                    "scientific_approval": "unknown",
                    "query_readiness": "not_ready",
                    "embedding_readiness": "not_ready",
                },
            )
        )
        if dataset_count:
            target = "synthetic:dataset:000000"
            # Facets and cross-links are edges to the same identity, not cloned nodes.
            edge_lists.setdefault("root:metadata", []).extend([target, target])
            edge_lists.setdefault("synthetic:candidate-link", []).append(target)
            node = records["synthetic:candidate-link"].node
            records[node.id] = FixtureRecord(
                node.model_copy(update={"related_ids": [target]})
            )
    return SyntheticCatalogue(
        snapshot_id,
        records,
        {parent: tuple(children) for parent, children in edge_lists.items()},
    )
