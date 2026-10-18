"""C19 host-only projections of validated C14 observations and retained bytes."""

from __future__ import annotations

import json
import re

from schema.context_catalogue import CatalogueListing, CatalogueNode, canonical_json
from schema.research_controller import (
    ControllerBinding,
    ObjectWitness,
    Observation,
    SemanticCount,
    canonical_hash,
    canonical_scope_json,
    scientific_parameters_hash,
)
from schema.scientific_catalogue import INDEX_OBJECT_ID, ScientificResponse


class ObservationInvalid(ValueError):
    pass


def _preview(value, limit=20):
    """Preview strings may be shortened; scientific qualifications live separately."""

    def bounded(item, depth=0):
        if depth > 8:
            return "[preview depth omitted]"
        if isinstance(item, str):
            return item if len(item) <= 1000 else item[:1000] + "[preview text omitted]"
        if isinstance(item, list):
            return [bounded(v, depth + 1) for v in item[:20]]
        if isinstance(item, dict):
            return {k: bounded(v, depth + 1) for k, v in list(item.items())[:64]}
        return item

    rows = [bounded(v) for v in value[:limit]]
    while len(canonical_json(rows).encode("utf-8")) > 32000:
        rows.pop()
    return canonical_json(rows)


def _object(node):
    return ObjectWitness(
        object_id=node.id,
        exact_names=tuple(dict.fromkeys((node.title.en, node.title.ja))),
    )


def _known(row):
    if not isinstance(row, dict):
        return ()

    def known(value):
        if value is None:
            return False
        if isinstance(value, str):
            return value.casefold() not in {
                "unknown",
                "unavailable",
                "partial",
                "not_measured",
                "not_reported",
                "unresolved",
            }
        if isinstance(value, dict):
            return all(known(item) for item in value.values())
        if isinstance(value, list):
            return all(known(item) for item in value)
        return True

    return tuple(key for key, value in row.items() if known(value))


def _scientific_qualifications(payload):
    retained = []
    text_keys = {
        "limitations",
        "qualification",
        "qualifications",
        "approval_basis",
        "scientific_qualification",
        "scientific_approval",
        "scope_compatibility",
        "columns",
        "source_operations",
    }

    def retain(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                retain(item, path + "." + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                retain(item, path + "." + str(index))
        else:
            retained.append(canonical_json({path: value}))

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in text_keys:
                    if isinstance(item, str):
                        retained.append(item)
                    elif isinstance(item, list) and all(
                        isinstance(text, str) for text in item
                    ):
                        retained.extend(item)
                    else:
                        retain(item, key)
                if {"id", "kind", "authority"} <= set(value) and key in {
                    "purpose",
                    "descriptor",
                    "lifecycle",
                    "authority",
                }:
                    retain(item, "node." + key)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return tuple(dict.fromkeys(retained))


def inventory_inputs(payload):
    """C13 carries a registry hash beside hashed canonical dataset witnesses."""
    count = payload["rows"][0]["count"]
    inputs = payload["receipt"]["inputs"]
    datasets = [
        item
        for item in inputs
        if re.fullmatch(r"c13:input:[a-f0-9]{64}", item["object_id"])
    ]
    dataset_ids = {item["object_id"] for item in datasets}
    if len(datasets) == count and all(
        item["object_id"] in dataset_ids or item["object_id"] == INDEX_OBJECT_ID
        for item in inputs
    ):
        return datasets
    # Explicit C14 fixture backends expose canonical dataset IDs directly.
    if len(inputs) == count and all(
        item["object_id"] != INDEX_OBJECT_ID for item in inputs
    ):
        return inputs
    raise ObservationInvalid("inventory_semantics")


class ObservationCollector:
    """Each execution owns its collector; callbacks receive detached JSON only."""

    def __init__(self, binding: ControllerBinding, preview_rows=20):
        self.binding = binding
        self.preview_rows = preview_rows
        self.observations: list[Observation] = []
        self.payloads: dict[str, str] = {}

    def payload(self, observation):
        return json.loads(self.payloads[observation.full_payload_ref])

    def add(self, tool, arguments, payload, *, question_compatibility_sha256=None):
        if not isinstance(payload, dict) or "error" in payload:
            raise ObservationInvalid("tool_failed")
        scope_json = canonical_scope_json(arguments["scope"])
        kwargs = {
            "binding": self.binding,
            "tool": tool,
            "scope_json": scope_json,
            "input_sha256": canonical_hash([]),
            "availability": "available",
            "source_completeness": "unknown",
            "query_completion": "complete",
        }
        if tool in {"catalogue.query", "catalogue.coverage", "analysis.get_published"}:
            result = ScientificResponse.model_validate(payload)
            if (
                result.snapshot_id != self.binding.snapshot_id
                or canonical_scope_json(result.scope) != scope_json
            ):
                raise ObservationInvalid("observation_binding")
            receipt = result.receipt
            actual_target = (
                tuple(arguments["input_ids"])
                if tool == "catalogue.query"
                else (arguments["object_id"],)
                if tool == "catalogue.coverage"
                else (arguments["analysis_id"],)
            )
            kwargs.update(
                operation_id=receipt.operation_id,
                operation_version=receipt.operation_version,
                parameters_sha256=scientific_parameters_hash(receipt.parameters),
                target_ids=actual_target,
                input_count=len(receipt.inputs),
                input_sha256=canonical_hash(
                    [v.model_dump(mode="json") for v in receipt.inputs]
                ),
                availability=receipt.availability.status,
                source_completeness=receipt.source_completeness,
                query_completion=receipt.query_completion,
                authority=receipt.authority,
                qualifications=tuple(
                    dict.fromkeys(
                        [
                            *result.qualifications,
                            *(
                                [receipt.availability.reason]
                                if receipt.availability.reason
                                else []
                            ),
                        ]
                    )
                ),
                output_fields=tuple(c.key for c in result.columns),
                known_fields=tuple(
                    sorted(set.intersection(*[set(_known(row)) for row in result.rows]))
                )
                if result.rows
                else (),
                preview_json=_preview(result.rows, self.preview_rows),
                result_content_sha256=receipt.content_sha256,
                page_offset=result.offset,
                page_returned_count=receipt.returned_count,
                page_total_rows=receipt.total_rows.value,
                next_offset=result.next_offset,
                preview_truncated=receipt.preview_truncated,
            )

            def coverage_known(row):
                # Native SST has an explicit sampling denominator and an optional
                # null reason for known coverage. C12 explicitly stays unknown.
                if "coverage_state" in row:
                    return (
                        row["coverage_state"] == "known"
                        and row.get("expected_days") is not None
                        and row.get("missing_days") is not None
                        and row.get("observed_days") is not None
                        and row.get("observation_entity") is not None
                        and row.get("calendar") is not None
                    )
                # C10 collection labels carry exact observed casts/libraries,
                # not an invented expected sampling calendar or percentage.
                return (
                    set(row) == {"collection_period", "precision", "count", "entity"}
                    and row["entity"] in {"casts", "libraries"}
                    and row["collection_period"] is not None
                    and row["precision"] not in {"unknown", None}
                    and type(row["count"]) is int
                )

            if (
                receipt.operation_id == "c13.coverage"
                and result.rows
                and receipt.source_completeness
                == receipt.query_completion
                == "complete"
                and not receipt.preview_truncated
                and all(coverage_known(row) for row in result.rows)
            ):
                kwargs["known_fields"] = (*kwargs["known_fields"], "coverage_known")
            if (
                receipt.operation_id == "c13.inventory"
                and receipt.availability.status == "available"
                and receipt.query_completion == "complete"
            ):
                if (
                    len(result.rows) != 1
                    or type(result.rows[0].get("count")) is not int
                ):
                    raise ObservationInvalid("inventory_semantics")
                row = result.rows[0]
                inventory_inputs(payload)
                if row.get("entity", "datasets") != "datasets":
                    raise ObservationInvalid("inventory_semantics")
                kwargs["counts"] = (
                    SemanticCount(
                        state="known",
                        entity="datasets",
                        value=row["count"],
                        denominator=row.get(
                            "denominator",
                            "Distinct permitted canonical input datasets in the executed complete scope",
                        ),
                    ),
                )
            if receipt.operation_id == "c13.table":
                parameters = (
                    arguments
                    if tool == "analysis.get_published"
                    else arguments["parameters"]
                )
                kwargs.update(
                    analysis_id=arguments.get(
                        "analysis_id", arguments.get("input_ids", [None])[0]
                    ),
                    workflow_kind=parameters.get("workflow_kind"),
                    protocol_id=parameters.get("protocol_id"),
                    table_names=(parameters["table"],)
                    if parameters.get("table")
                    else (),
                    question_compatibility_sha256=question_compatibility_sha256,
                )
        elif tool in {
            "catalogue.overview",
            "catalogue.list",
            "catalogue.relationships",
        }:
            listing = CatalogueListing.model_validate(payload)
            if (
                listing.request.snapshot_id != self.binding.snapshot_id
                or canonical_scope_json(listing.request.scope) != scope_json
            ):
                raise ObservationInvalid("observation_binding")
            kwargs.update(
                objects=tuple(_object(node) for node in listing.items),
                availability=listing.availability.status,
                source_completeness=listing.source_completeness,
                query_completion=listing.query_completion,
                preview_json=canonical_json(
                    [
                        {
                            "listing_page": {
                                "next_cursor": listing.next_cursor,
                                "total": listing.total.model_dump(mode="json"),
                                "returned_count": listing.returned_count,
                                "limit": listing.request.limit,
                            }
                        },
                        *json.loads(
                            _preview(
                                [
                                    node.model_dump(mode="json")
                                    for node in listing.items
                                ],
                                max(0, self.preview_rows - 1),
                            )
                        ),
                    ]
                ),
            )
        elif tool == "catalogue.open":
            node = CatalogueNode.model_validate(payload.get("node", payload))
            if (
                node.snapshot_id != self.binding.snapshot_id
                or canonical_scope_json(node.scope) != scope_json
                or node.id != arguments["object_id"]
            ):
                raise ObservationInvalid("observation_binding")
            kwargs.update(
                objects=(_object(node),),
                availability=node.availability.status,
                target_ids=(node.id,),
                qualifications=(node.availability.reason,)
                if node.availability.reason
                else (),
                preview_json=_preview(
                    [node.model_dump(mode="json")], self.preview_rows
                ),
            )
        else:
            raise ObservationInvalid("unknown_tool")
        kwargs["qualifications"] = tuple(
            dict.fromkeys(
                [
                    *kwargs.get("qualifications", ()),
                    *_scientific_qualifications(payload),
                ]
            )
        )
        encoded = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        reference = "c19:evidence:" + payload_hash
        observation = Observation(
            observation_id=f"c19:observation:{len(self.observations) + 1}:{payload_hash[:16]}",
            full_payload_ref=reference,
            full_payload_sha256=payload_hash,
            **kwargs,
        )
        self.payloads[reference] = encoded
        self.observations.append(observation)
        return observation

    def inventory_union(self, observations, roots, scope):
        """Derived union retains actual child receipt refs and deduplicated hashes."""
        inputs = {}
        for observation in observations:
            if not observation.counts or observation.query_completion != "complete":
                raise ObservationInvalid("inventory_incomplete")
            for item in inventory_inputs(self.payload(observation)):
                if item["object_id"] in inputs and inputs[item["object_id"]] != item:
                    raise ObservationInvalid("inventory_input_conflict")
                inputs[item["object_id"]] = item
        identities = [inputs[key] for key in sorted(inputs)]
        value = {
            "operation": "c19.inventory_union",
            "snapshot_id": self.binding.snapshot_id,
            "scope": json.loads(canonical_scope_json(scope)),
            "roots": list(roots),
            "inputs": identities,
            "count": len(inputs),
            "derived_from": [obs.full_payload_ref for obs in observations],
        }
        hashed = canonical_hash(value)
        reference = "c19:evidence:" + hashed
        result = Observation(
            observation_id=f"c19:observation:{len(self.observations) + 1}:{hashed[:16]}",
            binding=self.binding,
            tool="catalogue.query",
            scope_json=canonical_scope_json(scope),
            full_payload_ref=reference,
            full_payload_sha256=hashed,
            operation_id="c19.inventory_union",
            operation_version="c19-v1",
            target_ids=tuple(roots),
            input_count=len(inputs),
            input_sha256=canonical_hash(identities),
            availability="available",
            source_completeness="complete"
            if all(obs.source_completeness == "complete" for obs in observations)
            else "unknown",
            query_completion="complete",
            qualifications=tuple(
                dict.fromkeys(
                    [
                        "Controller-derived union of the referenced complete inventory receipts; not a new scientific operation.",
                        *[text for obs in observations for text in obs.qualifications],
                    ]
                )
            ),
            counts=(
                SemanticCount(
                    state="known",
                    entity="datasets",
                    value=len(inputs),
                    denominator="Distinct permitted canonical input datasets across the executed inventory roots",
                ),
            ),
            preview_json=canonical_json([{"entity": "datasets", "count": len(inputs)}]),
        )
        self.payloads[reference] = canonical_json(value)
        self.observations.append(result)
        return result
