"""Strict, reproducible validation for raw scientific source files."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

import config
from preprocessing.common import SAMPLE_ID_RE


CONTRACT_PATH = config.PROJECT_ROOT / "data_contracts" / "raw_sources.json"
LATEST_REPORT_NAME = "raw_validation_latest.json"
SST_TIMESTAMP_RE = re.compile(r"(\d{8})_(\d{4})")


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    source: str
    message: str


@dataclass
class SourceValidation:
    source: str
    path: str
    exists: bool
    size_bytes: int = 0
    rows: int = 0
    columns: Optional[int] = None
    sha256: Optional[str] = None
    sample_columns: Optional[int] = None
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class RawValidationReport:
    schema_version: int
    generated_at: str
    ok: bool
    errors: int
    warnings: int
    contract_path: str
    sources: list[SourceValidation]
    sst_files: int
    sst_collection_hash: Optional[str]
    issues: list[ValidationIssue]
    previous_report: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Raw source contract is unreadable: {path}: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported raw source contract schema: {path}")
    return payload


def _file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _issue(
    source: SourceValidation,
    *,
    severity: str,
    code: str,
    message: str,
) -> None:
    source.issues.append(
        ValidationIssue(
            severity=severity,
            code=code,
            source=source.source,
            message=message,
        )
    )


def _validate_minimums(
    source: SourceValidation,
    source_contract: dict[str, Any],
) -> None:
    minimum_rows = int(source_contract.get("minimum_rows") or 0)
    if source.rows < minimum_rows:
        _issue(
            source,
            severity="error",
            code="row_count_below_contract",
            message=f"Expected at least {minimum_rows} rows, observed {source.rows}.",
        )
    expected_columns = source_contract.get("columns")
    if expected_columns is not None and source.columns != int(expected_columns):
        _issue(
            source,
            severity="error",
            code="column_count_mismatch",
            message=(
                f"Expected {expected_columns} columns, observed {source.columns}."
            ),
        )
    minimum_sample_columns = int(
        source_contract.get("minimum_sample_columns") or 0
    )
    if (
        minimum_sample_columns
        and source.sample_columns is not None
        and source.sample_columns < minimum_sample_columns
    ):
        _issue(
            source,
            severity="error",
            code="sample_columns_below_contract",
            message=(
                f"Expected at least {minimum_sample_columns} sample columns, "
                f"observed {source.sample_columns or 0}."
            ),
        )


def _scan_tsv(
    source_name: str,
    path: Path,
    source_contract: dict[str, Any],
    *,
    allow_short_header: bool = False,
) -> tuple[SourceValidation, list[list[str]]]:
    result = SourceValidation(
        source=source_name,
        path=str(path),
        exists=path.is_file(),
    )
    preview: list[list[str]] = []
    if not result.exists:
        _issue(
            result,
            severity="error",
            code="missing_file",
            message=f"Required source file is missing: {path}",
        )
        return result, preview

    result.size_bytes = path.stat().st_size
    if result.size_bytes == 0:
        _issue(
            result,
            severity="error",
            code="empty_file",
            message="Required source file is empty.",
        )
        return result, preview

    field_counts: dict[int, int] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            result.rows += 1
            field_counts[len(row)] = field_counts.get(len(row), 0) + 1
            if row_number <= 5:
                preview.append(row)
    result.columns = (
        next(iter(field_counts))
        if len(field_counts) == 1
        else max(field_counts, key=field_counts.get)
    )
    expected_short_header = (
        allow_short_header
        and len(field_counts) == 2
        and preview
        and field_counts.get(len(preview[0])) == 1
        and max(field_counts) - len(preview[0]) == 1
    )
    if len(field_counts) > 1 and not expected_short_header:
        summary = ", ".join(
            f"{columns} columns: {rows} rows"
            for columns, rows in sorted(field_counts.items())
        )
        _issue(
            result,
            severity="error",
            code="ragged_rows",
            message=f"Inconsistent tabular width ({summary}).",
        )
    result.sha256 = _file_sha256(path)
    _validate_minimums(result, source_contract)
    return result, preview


def _valid_sample_ids(values: Iterable[Any]) -> tuple[int, list[str]]:
    invalid: list[str] = []
    total = 0
    for value in values:
        total += 1
        text = str(value).strip()
        if not SAMPLE_ID_RE.fullmatch(text):
            invalid.append(text)
    return total, invalid[:5]


def _validate_ctd(
    path: Path,
    source_contract: dict[str, Any],
    *,
    earliest: pd.Timestamp,
    latest: pd.Timestamp,
) -> SourceValidation:
    result, _ = _scan_tsv("ctd", path, source_contract)
    if not result.exists or result.issues:
        return result
    frame = pd.read_csv(path, sep="\t")
    lowered = {str(column).strip().lower(): column for column in frame.columns}
    required = {"date", "label", "depth"}
    missing = sorted(required - set(lowered))
    if missing:
        _issue(
            result,
            severity="error",
            code="missing_required_columns",
            message=f"Missing CTD columns: {', '.join(missing)}.",
        )
        return result

    dates = pd.to_datetime(frame[lowered["date"]], errors="coerce")
    invalid_dates = int(dates.isna().sum())
    if invalid_dates:
        _issue(
            result,
            severity="error",
            code="invalid_dates",
            message=f"{invalid_dates} CTD rows have invalid dates.",
        )
    out_of_range = int(((dates < earliest) | (dates > latest)).fillna(False).sum())
    if out_of_range:
        _issue(
            result,
            severity="error",
            code="dates_out_of_range",
            message=f"{out_of_range} CTD rows fall outside the allowed date range.",
        )
    _, invalid_samples = _valid_sample_ids(frame[lowered["label"]].unique())
    if invalid_samples:
        _issue(
            result,
            severity="error",
            code="invalid_sample_ids",
            message=f"Invalid CTD sample identifiers: {invalid_samples}.",
        )
    depths = pd.to_numeric(frame[lowered["depth"]], errors="coerce")
    invalid_depths = int((depths.isna() | (depths < 0)).sum())
    if invalid_depths:
        _issue(
            result,
            severity="error",
            code="invalid_depths",
            message=f"{invalid_depths} CTD rows have invalid or negative depths.",
        )
    duplicate_rows = int(
        frame.duplicated(
            [lowered["label"], lowered["date"], lowered["depth"]],
            keep=False,
        ).sum()
    )
    if duplicate_rows:
        _issue(
            result,
            severity="error",
            code="duplicate_profile_keys",
            message=f"{duplicate_rows} CTD rows duplicate sample/date/depth keys.",
        )
    return result


def _read_headerless(path: Path, columns: list[str]) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", header=None, names=columns)


def _validate_run_sources(
    results: dict[str, SourceValidation],
    *,
    earliest: pd.Timestamp,
    latest: pd.Timestamp,
) -> None:
    run_result = results["runid"]
    read_result = results["read_summary"]
    if run_result.issues or read_result.issues:
        return
    run_frame = _read_headerless(
        Path(run_result.path),
        ["run_id", "sample_replicate", "run_date"],
    )
    read_frame = _read_headerless(
        Path(read_result.path),
        [
            "sample_replicate",
            "n_reads_gt1kb",
            "bases_gt1kb",
            "n_reads_gt10kb",
            "bases_gt10kb",
        ],
    )
    for column in ("run_id", "sample_replicate"):
        duplicate_count = int(run_frame[column].duplicated(keep=False).sum())
        if duplicate_count:
            _issue(
                run_result,
                severity="error",
                code=f"duplicate_{column}",
                message=f"{duplicate_count} rows duplicate {column}.",
            )
    duplicate_reads = int(
        read_frame["sample_replicate"].duplicated(keep=False).sum()
    )
    if duplicate_reads:
        _issue(
            read_result,
            severity="error",
            code="duplicate_sample_replicate",
            message=f"{duplicate_reads} read-summary rows duplicate sample keys.",
        )
    for result, values in (
        (run_result, run_frame["sample_replicate"]),
        (read_result, read_frame["sample_replicate"]),
    ):
        _, invalid = _valid_sample_ids(values)
        if invalid:
            _issue(
                result,
                severity="error",
                code="invalid_sample_ids",
                message=f"Invalid sample identifiers: {invalid}.",
            )
    dates = pd.to_datetime(run_frame["run_date"], errors="coerce")
    invalid_dates = int(
        (dates.isna() | (dates < earliest) | (dates > latest)).sum()
    )
    if invalid_dates:
        _issue(
            run_result,
            severity="error",
            code="invalid_run_dates",
            message=f"{invalid_dates} run rows have invalid or out-of-range dates.",
        )
    numeric_columns = [
        "n_reads_gt1kb",
        "bases_gt1kb",
        "n_reads_gt10kb",
        "bases_gt10kb",
    ]
    invalid_numeric = 0
    for column in numeric_columns:
        values = pd.to_numeric(read_frame[column], errors="coerce")
        invalid_numeric += int((values.isna() | (values < 0)).sum())
    if invalid_numeric:
        _issue(
            read_result,
            severity="error",
            code="invalid_read_counts",
            message=f"{invalid_numeric} read-summary values are invalid or negative.",
        )
    run_samples = set(run_frame["sample_replicate"].astype(str))
    read_samples = set(read_frame["sample_replicate"].astype(str))
    if run_samples != read_samples:
        _issue(
            read_result,
            severity="error",
            code="run_read_sample_mismatch",
            message=(
                f"Run/read sample sets differ: "
                f"{len(run_samples - read_samples)} missing from reads, "
                f"{len(read_samples - run_samples)} missing from run mapping."
            ),
        )


def _validate_abundance_matrix(
    source_name: str,
    result: SourceValidation,
    *,
    upper_group: bool = False,
) -> set[str]:
    if result.issues:
        return set()
    frame = pd.read_csv(result.path, sep="\t", index_col=0)
    sample_columns = list(frame.columns[1:] if upper_group else frame.columns)
    result.sample_columns = len(sample_columns)
    _, invalid = _valid_sample_ids(sample_columns)
    if invalid:
        _issue(
            result,
            severity="error",
            code="invalid_sample_columns",
            message=f"Invalid abundance sample columns: {invalid}.",
        )
    if len(sample_columns) != len(set(map(str, sample_columns))):
        _issue(
            result,
            severity="error",
            code="duplicate_sample_columns",
            message="Abundance matrix contains duplicate sample columns.",
        )
    numeric = frame[sample_columns].apply(pd.to_numeric, errors="coerce")
    invalid_values = int((numeric.isna() | (numeric < 0)).sum().sum())
    if invalid_values:
        _issue(
            result,
            severity="error",
            code="invalid_abundance_values",
            message=f"{invalid_values} abundance cells are invalid or negative.",
        )
    if (frame.index.astype("string").str.strip() == "").any():
        _issue(
            result,
            severity="error",
            code="blank_taxa",
            message="Abundance matrix contains blank taxon identifiers.",
        )
    return set(map(str, sample_columns))


def _validate_consistency_sources(results: dict[str, SourceValidation]) -> None:
    gn = results["gn_consistency"]
    if not gn.issues:
        frame = _read_headerless(
            Path(gn.path),
            ["genus_taxid", "consistency_level", "genus"],
        )
        levels = pd.to_numeric(frame["consistency_level"], errors="coerce")
        invalid = int((levels.isna() | (levels < 0)).sum())
        blank_genera = int(frame["genus"].astype("string").str.strip().eq("").sum())
        if invalid or blank_genera:
            _issue(
                gn,
                severity="error",
                code="invalid_genus_consistency",
                message=(
                    f"{invalid} invalid consistency levels and "
                    f"{blank_genera} blank genera."
                ),
            )

    km = results["km_consistency"]
    if not km.issues:
        invalid = 0
        with Path(km.path).open(encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle, delimiter="\t"):
                if len(row) < 3:
                    invalid += 1
                    continue
                try:
                    level = float(row[2])
                except ValueError:
                    invalid += 1
                    continue
                if level < 0:
                    invalid += 1
        if invalid:
            _issue(
                km,
                severity="error",
                code="invalid_contig_consistency",
                message=f"{invalid} contig-consistency rows are invalid.",
            )


def _validate_sst(
    contract: dict[str, Any],
    *,
    earliest: pd.Timestamp,
    latest: pd.Timestamp,
) -> tuple[int, Optional[str], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    files = (
        sorted(config.SST_NETCDF_DIR.rglob("*.nc"))
        if config.SST_NETCDF_DIR.exists()
        else []
    )
    minimum = int(contract.get("sst", {}).get("minimum_files") or 0)
    if len(files) < minimum:
        issues.append(
            ValidationIssue(
                severity="error",
                code="sst_file_count_below_contract",
                source="sst_netcdf",
                message=f"Expected at least {minimum} SST files, observed {len(files)}.",
            )
        )
    manifest_rows: list[dict[str, Any]] = []
    timestamps: set[str] = set()
    for path in files:
        match = SST_TIMESTAMP_RE.search(path.name)
        if not match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_sst_filename",
                    source="sst_netcdf",
                    message=f"Cannot parse timestamp from {path.name}.",
                )
            )
            continue
        timestamp_text = f"{match.group(1)}{match.group(2)}"
        try:
            timestamp = pd.to_datetime(timestamp_text, format="%Y%m%d%H%M")
        except ValueError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_sst_timestamp",
                    source="sst_netcdf",
                    message=f"Invalid timestamp in {path.name}.",
                )
            )
            continue
        if timestamp < earliest or timestamp > latest:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="sst_timestamp_out_of_range",
                    source="sst_netcdf",
                    message=f"Out-of-range timestamp in {path.name}.",
                )
            )
        timestamp_key = timestamp.isoformat()
        if timestamp_key in timestamps:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="duplicate_sst_timestamp",
                    source="sst_netcdf",
                    message=f"Duplicate SST timestamp: {timestamp_key}.",
                )
            )
        timestamps.add(timestamp_key)
        stat = path.stat()
        manifest_rows.append(
            {
                "path": str(path.relative_to(config.SST_NETCDF_DIR)),
                "size_bytes": stat.st_size,
                "timestamp": timestamp_key,
            }
        )
    collection_hash = (
        hashlib.sha256(
            json.dumps(
                manifest_rows,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if manifest_rows
        else None
    )
    return len(files), collection_hash, issues


def _previous_row_count_issues(
    results: list[SourceValidation],
    *,
    report_path: Path,
    maximum_drop_ratio: float,
) -> tuple[list[ValidationIssue], Optional[str]]:
    if not report_path.exists():
        return [], None
    try:
        previous = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], None
    previous_rows = {
        str(source.get("source")): int(source.get("rows") or 0)
        for source in previous.get("sources", [])
        if isinstance(source, dict)
    }
    issues: list[ValidationIssue] = []
    for result in results:
        before = previous_rows.get(result.source, 0)
        if before <= 0 or result.rows >= before:
            continue
        drop_ratio = (before - result.rows) / before
        if drop_ratio > maximum_drop_ratio:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="unexpected_row_count_drop",
                    source=result.source,
                    message=(
                        f"Row count dropped {drop_ratio:.1%}, from "
                        f"{before} to {result.rows}."
                    ),
                )
            )
    return issues, str(report_path)


def validate_raw_sources(
    *,
    contract_path: Path = CONTRACT_PATH,
    report_path: Optional[Path] = None,
    write_report: bool = True,
) -> RawValidationReport:
    contract = _load_contract(contract_path)
    earliest = pd.Timestamp(contract["allowed_date_start"])
    latest = pd.Timestamp.now(tz=None) + timedelta(
        days=int(contract["allowed_future_days"])
    )
    source_contracts = dict(contract.get("sources") or {})
    results: dict[str, SourceValidation] = {}

    for source_name, path in config.RAW_FILES.items():
        source_contract = dict(source_contracts.get(source_name) or {})
        if source_name == "ctd":
            result = _validate_ctd(
                path,
                source_contract,
                earliest=earliest,
                latest=latest,
            )
        else:
            result, _ = _scan_tsv(
                source_name,
                path,
                source_contract,
                allow_short_header=source_name
                in {
                    "kraken_genus_sample_tsv",
                    "kraken_genus_sample_txt",
                    "kraken_upper_group_sample",
                    "metaeuk_genus_sample",
                },
            )
        results[source_name] = result

    _validate_run_sources(results, earliest=earliest, latest=latest)
    sample_sets = {
        "kraken": _validate_abundance_matrix(
            "kraken_genus_sample_tsv",
            results["kraken_genus_sample_tsv"],
        ),
        "kraken_text": _validate_abundance_matrix(
            "kraken_genus_sample_txt",
            results["kraken_genus_sample_txt"],
        ),
        "metaeuk": _validate_abundance_matrix(
            "metaeuk_genus_sample",
            results["metaeuk_genus_sample"],
        ),
        "upper_group": _validate_abundance_matrix(
            "kraken_upper_group_sample",
            results["kraken_upper_group_sample"],
            upper_group=True,
        ),
    }
    for name, sample_set in sample_sets.items():
        result = results[
            {
                "kraken": "kraken_genus_sample_tsv",
                "kraken_text": "kraken_genus_sample_txt",
                "metaeuk": "metaeuk_genus_sample",
                "upper_group": "kraken_upper_group_sample",
            }[name]
        ]
        _validate_minimums(
            result,
            source_contracts.get(result.source, {}),
        )
    nonempty_sample_sets = {
        name: values for name, values in sample_sets.items() if values
    }
    if nonempty_sample_sets:
        baseline_name, baseline = next(iter(nonempty_sample_sets.items()))
        for name, values in list(nonempty_sample_sets.items())[1:]:
            if values != baseline:
                target_source = {
                    "kraken_text": "kraken_genus_sample_txt",
                    "metaeuk": "metaeuk_genus_sample",
                    "upper_group": "kraken_upper_group_sample",
                }[name]
                _issue(
                    results[target_source],
                    severity="error",
                    code="abundance_sample_set_mismatch",
                    message=(
                        f"Sample columns differ from {baseline_name}: "
                        f"{len(baseline - values)} missing and "
                        f"{len(values - baseline)} unexpected."
                    ),
                )
    kraken_tsv = results["kraken_genus_sample_tsv"].sha256
    kraken_text = results["kraken_genus_sample_txt"].sha256
    if kraken_tsv and kraken_text and kraken_tsv != kraken_text:
        _issue(
            results["kraken_genus_sample_txt"],
            severity="error",
            code="kraken_duplicate_source_mismatch",
            message="Kraken .tsv and .txt source copies are not identical.",
        )
    _validate_consistency_sources(results)

    sst_files, sst_hash, sst_issues = _validate_sst(
        contract,
        earliest=earliest,
        latest=latest,
    )
    actual_report_path = report_path or (
        config.PROVENANCE_DIR / LATEST_REPORT_NAME
    )
    row_count_issues, previous_report = _previous_row_count_issues(
        list(results.values()),
        report_path=actual_report_path,
        maximum_drop_ratio=float(contract["maximum_row_drop_ratio"]),
    )
    issues = [
        issue
        for source in results.values()
        for issue in source.issues
    ]
    issues.extend(sst_issues)
    issues.extend(row_count_issues)
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    report = RawValidationReport(
        schema_version=1,
        generated_at=datetime.now(timezone.utc).isoformat(),
        ok=errors == 0,
        errors=errors,
        warnings=warnings,
        contract_path=str(contract_path),
        sources=list(results.values()),
        sst_files=sst_files,
        sst_collection_hash=sst_hash,
        issues=issues,
        previous_report=previous_report,
    )
    if write_report:
        actual_report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = actual_report_path.with_suffix(
            actual_report_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        temporary_path.replace(actual_report_path)
    return report
