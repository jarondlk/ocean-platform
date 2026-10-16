"""C13 scientific identity, authority and source-binding contract acceptance."""

import copy
import json
from pathlib import Path

import pytest

from schema.scientific_catalogue import ScientificRegistry
from schema.scientific_catalogue_fixtures import scientific_fixture
from scripts.export_scientific_catalogue import generated_files


def logical():
    registry, _ = scientific_fixture(3)
    return registry.model_dump(mode="json")


def test_generated_contract_and_examples_match_runtime():
    for path, expected in generated_files().items():
        assert path.read_text() == expected
    schema = json.loads(Path("schema/scientific_catalogue.v1.schema.json").read_text())
    assert schema["$defs"]["ScientificRegistry"]["additionalProperties"] is False
    assert (
        ScientificRegistry.model_validate(logical()).analyses[0].publication_status
        == "published"
    )


@pytest.mark.parametrize(
    "field", ["independent_researcher_approval", "provider_endorsement"]
)
def test_operational_publication_never_promotes_independent_authority(field):
    raw = logical()
    raw["analyses"][0][field] = True
    with pytest.raises(ValueError, match="Operational"):
        ScientificRegistry.model_validate(raw)


@pytest.mark.parametrize(
    "field", ["independent_researcher_approval", "provider_endorsement"]
)
@pytest.mark.parametrize("value", [True, 1, 0, "false", "approved"])
def test_unverified_authority_cannot_be_reintroduced_under_another_basis(field, value):
    raw = logical()
    raw["analyses"][0]["approval_basis"] = "unverified claimed independent approval"
    raw["analyses"][0][field] = value
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)


def test_analysis_scope_cannot_claim_an_enabled_source_without_a_frozen_input():
    raw = logical()
    raw["analyses"][0]["scope"]["sources"]["remote_sensing"]["enabled"] = True
    with pytest.raises(ValueError, match="exactly"):
        ScientificRegistry.model_validate(raw)


@pytest.mark.parametrize(
    "kind", ["published", "unpublished", "historical", "experimental"]
)
def test_retained_statuses_remain_distinct(kind):
    raw = logical()
    raw["analyses"][0]["publication_status"] = kind
    assert ScientificRegistry.model_validate(raw).analyses[0].publication_status == kind


@pytest.mark.parametrize(
    "identity",
    ["root:analyses", "c13:reference:x", "scientific:index", "scientific:registry"],
)
def test_canonical_ids_cannot_shadow_generated_or_transport_nodes(identity):
    raw = logical()
    raw["analyses"][0]["id"] = identity
    raw["workflows"][0]["analysis_ids"] = [identity]
    with pytest.raises(ValueError, match="unique and nonreserved"):
        ScientificRegistry.model_validate(raw)


@pytest.mark.parametrize(
    "mutation", ["dataset", "analysis", "table", "workflow", "tombstone"]
)
def test_global_ids_and_tombstones_are_unique(mutation):
    raw = logical()
    if mutation == "dataset":
        raw["datasets"].append(copy.deepcopy(raw["datasets"][0]))
    elif mutation == "analysis":
        raw["analyses"].append(copy.deepcopy(raw["analyses"][0]))
    elif mutation == "table":
        table = copy.deepcopy(raw["analyses"][0]["tables"][0])
        table["name"] = "other"
        raw["analyses"][0]["tables"].append(table)
    elif mutation == "workflow":
        raw["workflows"].append(copy.deepcopy(raw["workflows"][0]))
    else:
        raw["superseded_generations"] = ["a" * 64, "a" * 64]
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "unbound_dataset",
        "unbound_analysis",
        "disabled_source",
        "missing_required_source",
        "scope_option",
    ],
)
def test_cross_root_links_cannot_create_missing_inputs_or_override_scope(mutation):
    raw = logical()
    if mutation == "unbound_dataset":
        raw["analyses"][0]["input_dataset_ids"] = ["not:bound"]
    elif mutation == "unbound_analysis":
        raw["workflows"][0]["analysis_ids"] = ["not:bound"]
    elif mutation == "disabled_source":
        raw["analyses"][0]["scope"]["sources"]["ctd"]["enabled"] = False
    elif mutation == "missing_required_source":
        raw["workflows"][0]["required_sources"] = ["metagenome"]
    else:
        raw["analyses"][0]["scope_option"] = {"analysis_id": "not:bound"}
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)


@pytest.mark.parametrize("status", ["unknown", "unavailable"])
def test_absent_full_table_has_no_known_empty_count(status):
    raw = logical()
    table = raw["analyses"][0]["tables"][0]
    table.update(
        object_id=None,
        row_count=None,
        availability={"status": status, "reason": "Missing retained table"},
        completeness=status,
    )
    assert (
        ScientificRegistry.model_validate(raw).analyses[0].tables[0].row_count is None
    )
    table["row_count"] = 0
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)


@pytest.mark.parametrize("value", [True, "3", -1, 1.5])
def test_counts_require_exact_nonnegative_integers(value):
    raw = logical()
    raw["analyses"][0]["tables"][0]["row_count"] = value
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)


def test_complete_empty_table_is_explicitly_available():
    registry, tables = scientific_fixture(0)
    assert registry.analyses[0].tables[0].row_count == 0
    assert registry.analyses[0].tables[0].availability.status == "available"
    assert next(iter(tables.values())) == []


def test_raw_transport_qualification_cannot_be_replaced_by_scientific_claim():
    raw = logical()
    raw["qualification"] = "Reviewed CTD observations"
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)


def test_contract_does_not_mutate_inputs_and_forbids_extra_approval_fields():
    raw = logical()
    original = copy.deepcopy(raw)
    ScientificRegistry.model_validate(raw)
    assert raw == original
    raw["analyses"][0]["scientific_approval"] = True
    with pytest.raises(ValueError):
        ScientificRegistry.model_validate(raw)
