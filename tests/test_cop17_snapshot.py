import pytest
from scripts.prepare_cop17_snapshot import validate_endpoints, SOURCE_INSTANCE, TARGET_INSTANCE

SOURCE = "postgresql+psycopg2://reader:secret@/ocean_platform?host=/cloudsql/" + SOURCE_INSTANCE
TARGET = "postgresql+psycopg2://owner:secret@/ocean_cop17?host=/cloudsql/" + TARGET_INSTANCE


def test_only_explicit_empty_demo_destination_is_supported():
    validate_endpoints(SOURCE, TARGET, TARGET_INSTANCE)


@pytest.mark.parametrize("source,target,confirmation", [
    (SOURCE, SOURCE, TARGET_INSTANCE),
    (TARGET, SOURCE, SOURCE_INSTANCE),
    (SOURCE, TARGET.replace("ocean-cop17-postgres", "ocean-postgres"), TARGET_INSTANCE),
    (SOURCE, TARGET.replace("ocean-cop17-postgres", "ocean-cop17-postgres-other"), TARGET_INSTANCE),
    (SOURCE, TARGET.replace("ocean_cop17?", "ocean_platform?"), TARGET_INSTANCE),
    (SOURCE, TARGET, None),
    (SOURCE.replace("@/", "@external/"), TARGET, TARGET_INSTANCE),
])
def test_live_or_ambiguous_destination_is_rejected(source, target, confirmation):
    with pytest.raises(ValueError):
        validate_endpoints(source, target, confirmation)
