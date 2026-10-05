"""Small explicitly specified research cohort, independent of production data."""

from ingestion.immutable_bundle import digest
from preprocessing.edna_analysis import taxon_key
from preprocessing.edna_detection_frequency import registry_versions
from preprocessing.research_recipe import (
    DetectionFrequencyRecipe,
    PhysicalMembership,
    ReviewedArea,
)


def h(value):
    return digest(value)


def research_fixture():
    evidence = dict(
        reviewer="fixture reviewer",
        rationale="Synthetic hand-calculated test evidence",
        references=["fixture://physical-original-and-area"],
        evidence_sha256=h("evidence"),
    )
    areas = [
        ReviewedArea(
            area_id=label,
            region_id="fixture-region",
            label=label,
            west=140 + i,
            east=141 + i,
            south=38,
            north=39,
            coordinate_uncertainty_km=1,
            decision=evidence,
        )
        for i, label in enumerate("ABC")
    ]
    source = {
        "edna_sample": [],
        "edna_assay": [],
        "edna_detection": [],
        "generations": {
            "canonical_generation": h("canonical"),
            "classification_generation": h("classification"),
        },
    }
    memberships, links = [], []
    species = ("Sardinops melanostictus", "Engraulis japonicus", "Trachurus japonicus")
    taxon_keys = {
        name: h(
            taxon_key(
                {"class": "Actinopterygii", "genus": name.split()[0], "species": name},
                "species",
            )
        )
        for name in species
    }
    # Endpoints: A and B each have 3 samples. Sardine: 2020 A=2/B=1,
    # 2023 A=0/B=3. Anchovy: 2020 A=0/B=0, 2023 A=2/B=0.
    # Jack mackerel: 100% both years/areas. Intermediate A2021=1, B2022=2.
    for year, area, n in [
        (2020, "A", 3),
        (2020, "B", 3),
        (2023, "A", 3),
        (2023, "B", 3),
        (2021, "A", 1),
        (2022, "B", 2),
    ]:
        for index in range(n):
            name = f"{year}-{area}-{index}"
            sid, aid, pid = h("s" + name), h("a" + name), h("p" + name)
            sample = dict(
                sample_id=sid,
                scientific_content_sha256=h("sc" + name),
                sample_kind="environmental",
                is_control=False,
                active=True,
                temporal_precision="datetime",
                collection_date_utc=f"{year}-05-15T01:00:00Z",
            )
            assay = dict(
                assay_id=aid,
                sample_id=sid,
                scientific_content_sha256=h("ac" + name),
                active=True,
                target_gene="12S",
                primer_set="fixture-MiFish",
                sequencing_method="fixture",
                library_layout="paired",
                community_availability_json={
                    "qcauto_target": {"status": "available", "row_count": 3},
                    "qcauto_95pct_3nn_target": {"status": "available", "row_count": 3},
                },
            )
            source["edna_sample"].append(sample)
            source["edna_assay"].append(assay)
            positive = [
                (
                    (year == 2020 and index < (2 if area == "A" else 1))
                    or (year == 2023 and area == "B")
                    or year == 2021
                ),
                year == 2023 and area == "A" and index < 2,
                True,
            ]
            for method in ("qcauto_target", "qcauto_95pct_3nn_target"):
                for taxon, present in zip(species, positive):
                    source["edna_detection"].append(
                        dict(
                            detection_id=h(name + method + taxon),
                            assay_id=aid,
                            assignment_method=method,
                            read_count=int(present),
                            **{"class": "Actinopterygii"},
                            genus=taxon.split()[0],
                            species=taxon,
                        )
                    )
            memberships.append(
                PhysicalMembership(
                    physical_sample_id=pid,
                    occurrences=[
                        dict(
                            sample_id=sid,
                            scientific_content_sha256=sample[
                                "scientific_content_sha256"
                            ],
                        )
                    ],
                    representative_assay_id=aid,
                    representative_assay_sha256=assay["scientific_content_sha256"],
                    area_id=area,
                    area_version=h(areas["ABC".index(area)].model_dump(mode="json")),
                    decision=evidence,
                )
            )
            if year in (2020, 2023):
                links.append(
                    dict(
                        physical_sample_id=pid,
                        panel_id=h("sst"),
                        status="matched",
                        sst_celsius=10 if year == 2020 else 20,
                        source_granule_ids=[h("granule" + name)],
                        observation_ids=[h("obs" + name)],
                    )
                )
    recipe = DetectionFrequencyRecipe(
        **source["generations"],
        **registry_versions(areas, memberships),
        region_id="fixture-region",
        time_from="2020-01-01",
        time_to="2023-12-31",
        assignment_method="qcauto_target",
        fish_classes=["Actinopterygii"],
        taxonomy_policy_reference="fixture://fish-lineage",
        spatial_taxon_key=taxon_keys[species[0]],
        endpoint_from=2020,
        endpoint_to=2023,
        spatial_year=2023,
        temperature_partition={"kind": "fixed_celsius", "low_max": 10, "high_min": 20},
        sst_panel_id=h("sst"),
    )
    return recipe, source, areas, memberships, links, taxon_keys
