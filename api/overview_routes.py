"""Aggregate Overview reads; detailed records retain their existing permissions."""
from fastapi import APIRouter

from api.overview_coverage import OverviewCoverage, overview_coverage

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/coverage", response_model=OverviewCoverage)
def coverage() -> OverviewCoverage:
    return overview_coverage()
