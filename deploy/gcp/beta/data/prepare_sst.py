"""Qualified local MUR regional-preview conversion; no cloud or science approval.

This source-specific converter preserves the exact retained operational preview.
It never treats historical embedded user instructions as fresh authorization,
fetches missing dependencies, promotes analyses, fills gaps or relabels JCOPE.
The CLI audits a checksum-pinned private source after a committed-source guard;
coordinator-owned snapshot publication remains separate.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
SOURCE_ID = 'beta:existing-regional-sst'
PERIOD_SHA256 = 'a02e205a70cc43532631b10ec170a3500052e01e9f75d9f050bac202236bdc33'
PUBLICATION_SHA256 = 'd34da58bbb39bb3675d0d0654d56ab13de46b078605df0fe52cb8f8ade698952'
REGISTRY_SHA256 = '80feba7f166cfa573e980b8e456353b44fb96b24b104fff4b79773706ca3e3de'
SOURCE_FILES = {
    '0-current.json': (188, '485f2e0a0e5ac9b50bf24afa6efc9b706859230223f1544c7925bc010ac7efbe'),
    '1-index.json': (199, 'b42f41c83bc6061f8212b18494f5ff8500d1a5020374f38730f79e3bc099b21c'),
    '2-period.json': (2616967, PERIOD_SHA256),
    '3-publication.json': (1998, PUBLICATION_SHA256),
    '4-' + PUBLICATION_SHA256 + '.json': (428, REGISTRY_SHA256),
}
MAX_PERIOD_BYTES = 4 * 1024 * 1024
MAX_OBSERVATIONS = 36_600
QUALIFICATIONS = (
    'Existing operational MUR regional-context preview, explicitly authorized for descriptive beta access; scientific approval and scientific publication remain false.',
    'The provisional Miyagi demonstration rectangle is not reviewed and is not a confirmed sampling footprint or native sample-area SST.',
    'MUR final version04.1 daily satellite/in-situ foundation analysis; retain source UTC instants, Celsius values and six known final-series gaps without interpolation or interim replacement.',
    'Spatial resolution0.05degree describes retained grid-point subsampling, not native product resolution or station/CTD measurements.',
    'Source proposed quality policy uses cosine-latitude weighting, analysis error at most1K, at least80percent valid ocean support and5points. This policy has no independent scientific approval.',
    'Every retained row warns that missing sea-ice fractions used the open-sea mask. Unknown per-row uncertainty and total ocean-point counts remain null.',
    'The C11 valid_ocean_pixels field retains the producer valid_ocean_points count of subsampled grid points; it does not assert a native-pixel population or infer a total denominator.',
    'Per-row raw SHA256 values are retained provenance declarations from the verified period; underlying granule bodies are not independently reverified by this conversion.',
    'Publication analysis dependencies and eDNA comparisons are excluded; no fish abundance, causal inference or cross-source physical pairing is introduced.',
)
SOURCE_PATHS = (
    'deploy/gcp/beta/data/prepare_sst.py', 'ingestion/sst_catalogue_inputs.py',
    'schema/sst_catalogue.py', 'schema/context_catalogue.py',
    'ingestion/catalogue_snapshot_capture.py', 'ingestion/immutable_bundle.py',
)


class SSTPreparationError(ValueError):
    """Fixed safe diagnostics; raw data and source text are not echoed."""


def require(condition, message):
    if not condition:
        raise SSTPreparationError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
        allow_nan=False) + '\n').encode()


def _unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'Duplicate SST source metadata key')
        value[key] = item
    return value


def parsed(data):
    require(type(data) is bytes and 0 < len(data) <= MAX_PERIOD_BYTES,
        'Bounded original SST period bytes required')
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=_unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(SSTPreparationError('Nonfinite SST source metadata')))
    except (UnicodeError, json.JSONDecodeError):
        raise SSTPreparationError('Valid original SST source JSON required') from None
    require(type(value) is dict, 'SST source metadata must be an object')
    return value


def _finite_number(value, message):
    require(type(value) in {int, float} and math.isfinite(value), message)
    return float(value)


def source_guard(revision):
    """No private preparation through an uncommitted or mismatched converter."""
    require(type(revision) is str and re.fullmatch('[a-f0-9]{40}', revision),
        'Explicit full source revision required')
    def git(*args):
        result = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True,
            timeout=20, check=False)
        require(result.returncode == 0, 'Committed SST preparation source required')
        return result.stdout
    require(git('rev-parse', 'HEAD^{commit}').decode().strip() == revision,
        'Explicit SST source must be current committed HEAD')
    names = set(SOURCE_PATHS)
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename)
            if path.is_absolute() and path.is_relative_to(ROOT) and path.suffix == '.py':
                relative = path.relative_to(ROOT)
                if relative.parts[0] in {'schema', 'ingestion', 'retrieval', 'db', 'orchestration', 'preprocessing'}:
                    names.add(relative.as_posix())
    pins = {}
    for name in sorted(names):
        path = ROOT / name
        require(path.is_file() and not path.is_symlink(), 'Regular committed SST source required')
        data = path.read_bytes()
        require(git('show', revision + ':' + name) == data,
            'SST preparation source differs from selected commit')
        pins[name] = hashlib.sha256(data).hexdigest()
    return pins


def verified_publication_bytes(directory):
    """Read only the five exact generation-pinned private staging objects."""
    directory = Path(directory)
    require(directory.is_absolute() and '..' not in directory.parts and not directory.is_relative_to(ROOT),
        'SST publication must remain in private staging outside the checkout')
    for path in (directory, *directory.parents):
        require(not path.is_symlink(), 'SST staging ancestors cannot be symbolic links')
    values = {}
    for name, (length, digest) in SOURCE_FILES.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink(), 'Pinned regular SST publication file required')
        before = path.stat()
        require(before.st_size == length and length <= MAX_PERIOD_BYTES,
            'Pinned SST source length mismatch')
        data = path.read_bytes()
        after = path.stat()
        def signature(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(signature(before) == signature(after) and hashlib.sha256(data).hexdigest() == digest,
            'Pinned SST source checksum or stable identity mismatch')
        values[name] = data
    current = parsed(values['0-current.json'])
    index = parsed(values['1-index.json'])
    registry = parsed(values['4-' + PUBLICATION_SHA256 + '.json'])
    publication = parsed(values['3-publication.json'])
    require(current.get('publication_id') == PUBLICATION_SHA256
        and current.get('receipt_sha256') == REGISTRY_SHA256
        and index.get('entries', {}).get(PUBLICATION_SHA256, {}).get('receipt_sha256') == REGISTRY_SHA256,
        'Current SST source publication bindings differ')
    require(registry.get('id') == PUBLICATION_SHA256
        and registry.get('files', {}).get('period.json', {}).get('sha256') == PERIOD_SHA256
        and registry.get('files', {}).get('period.json', {}).get('size') == SOURCE_FILES['2-period.json'][0]
        and registry.get('files', {}).get('publication.json', {}).get('sha256') == PUBLICATION_SHA256
        and publication.get('period_sha256') == PERIOD_SHA256,
        'SST source registry/period bindings differ')
    decision = publication.get('decision', {})
    require(decision.get('approval_basis') == 'explicit_user_accepted_operational_publication'
        and decision.get('independent_researcher_approval') is False
        and decision.get('provider_endorsement') is False,
        'SST source operational approval qualifications differ')
    return values['2-period.json']


def regional_dataset(data, *, source_sha256=PERIOD_SHA256):
    """Convert exact source values into C11; synthetic callers provide their hash."""
    import pandas as pd
    from ingestion.sst_catalogue_inputs import dataset_exports
    from schema.sst_catalogue import SSTDataset, TABLE_COLUMNS, sst_product_node_id
    require(type(data) is bytes and type(source_sha256) is str
        and re.fullmatch('[a-f0-9]{64}', source_sha256)
        and hashlib.sha256(data).hexdigest() == source_sha256,
        'Exact original SST period bytes and checksum required')
    source = parsed(data)
    require(type(source.get('schema_version')) is int and source.get('schema_version') == 1
        and source.get('area_id') == 'miyagi-regional-demo'
        and source.get('algorithm') == 'historical-regional-context-period-preview-v1'
        and source.get('status') == 'complete_unpublished_regional_context_preview'
        and source.get('scientific_approval') is False
        and source.get('scientific_publication') is False,
        'Explicit unapproved operational SST preview required')
    definition = source.get('definition', {})
    quality = definition.get('proposed_quality', {})
    require(all(type(quality.get(name)) in {int, float} for name in
        ('max_analysis_error_k', 'max_sea_ice_fraction', 'min_valid_ocean_fraction'))
        and quality.get('scientific_approval') is False and quality.get('status') == 'proposed'
        and quality.get('weighting') == 'cosine_latitude_grid_point_approximation'
        and quality.get('max_analysis_error_k') == 1.0
        and quality.get('max_sea_ice_fraction') == 0.15
        and quality.get('min_valid_ocean_fraction') == 0.8
        and type(quality.get('min_valid_ocean_points')) is int
        and quality.get('min_valid_ocean_points') == 5
        and quality.get('missing_ice_policy') == 'use_open_sea_mask_with_warning',
        'Declared provisional source quality policy required')
    step = _finite_number(definition.get('grid_step_degrees'), 'Retained SST grid-point spacing required')
    require(step == 0.05 and definition.get('diagnostic_rectangle') == {
        'south':38.0, 'north':39.0, 'west':141.0, 'east':142.0},
        'Exact provisional source subsampling rectangle required')
    period = source.get('period', {})
    require(type(period.get('first_year')) is int and type(period.get('last_year')) is int
        and period['first_year'] == 2020 and period['last_year'] == 2023,
        'Explicit representable source period years required')
    first = date(period['first_year'], 1, 1)
    last = date(period['last_year'], 12, 31)
    days = (last - first).days + 1
    require(days <= MAX_OBSERVATIONS, 'SST source period exceeds bounded daily contract')
    observations = source.get('observations')
    require(type(observations) is list and 0 < len(observations) <= MAX_OBSERVATIONS,
        'Bounded retained SST observation population required')
    records = []
    observed_days = set()
    ids = set()
    for row in observations:
        require(type(row) is dict and row.get('area_id') == source.get('area_id')
            and row.get('area_is_reviewed') is False and row.get('native_sample_area_evidence') is False
            and row.get('scientific_publication') is False
            and row.get('measurement_type') == 'satellite_in_situ_analysis'
            and row.get('processing_generation') == 'final'
            and row.get('product_version') == '04.1'
            and row.get('temporal_statistic') == 'daily_foundation_analysis'
            and row.get('status') == 'valid', 'Unmodified final/provisional SST row qualifiers required')
        identity, raw_hash, stamp = row.get('observation_id'), row.get('raw_sha256'), row.get('time_utc')
        require(type(identity) is str and re.fullmatch('[a-f0-9]{64}', identity)
            and identity not in ids and type(raw_hash) is str and re.fullmatch('[a-f0-9]{64}', raw_hash),
            'Distinct retained SST observation identity and raw-source checksum required')
        require(type(stamp) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T09:00:00\+00:00', stamp),
            'Exact source foundation-analysis UTC instant required')
        try:
            instant = datetime.fromisoformat(stamp)
        except ValueError:
            raise SSTPreparationError('Real source SST observation calendar required') from None
        day = instant.astimezone(timezone.utc).date()
        require(first <= day <= last and day not in observed_days,
            'SST source days must be unique and within their explicit period')
        value = _finite_number(row.get('sst_celsius'), 'Finite retained source Celsius value required')
        fraction = _finite_number(row.get('valid_fraction'), 'Finite retained source support fraction required')
        points = row.get('valid_ocean_points')
        require(0.8 <= fraction <= 1 and type(points) is int and 5 <= points <= 2**63 - 1,
            'Retained SST support must satisfy the source proposed thresholds')
        warnings = row.get('warnings')
        require(warnings == ['missing_ice_fraction_open_sea_mask_used'],
            'Explicit missing-sea-ice source warning must be retained')
        records.append({'observation_id':identity, 'time':stamp, 'value':value,
            'status':'valid', 'lat':None, 'lon':None,
            'quality_flag':'source_warning:missing_ice_fraction_open_sea_mask_used;policy_proposed_unreviewed',
            'uncertainty':None, 'valid_fraction':fraction, 'valid_ocean_pixels':points,
            'ocean_pixels':None, 'source_sha256':raw_hash, 'exclusion_reason':None})
        observed_days.add(day)
        ids.add(identity)
    gaps = source.get('final_series_gaps')
    require(type(gaps) is list, 'Explicit source final-series gap population required')
    gap_days = set()
    for gap in gaps:
        require(type(gap) is dict and gap.get('reason') in {'known_acquisition_exclusion', 'interim_generation'}
            and type(gap.get('day')) is str, 'Explicit source final-series gap reason required')
        try:
            day = date.fromisoformat(gap['day'])
        except ValueError:
            raise SSTPreparationError('Real source SST gap calendar required') from None
        require(day.isoformat() == gap['day'] and first <= day <= last and day not in gap_days,
            'Unique source gap day in declared period required')
        gap_days.add(day)
    expected_days = {first + timedelta(days=index) for index in range(days)}
    require(not gap_days.intersection(observed_days) and observed_days | gap_days == expected_days,
        'Retained SST observations and explicit gaps must reconcile the complete period')
    dataset_id = 'beta:sst:regional-preview:' + source_sha256
    dataset = SSTDataset.model_validate({'dataset_id':dataset_id, 'source_id':SOURCE_ID,
        'product_node_id':sst_product_node_id(SOURCE_ID, 'mur', '04.1', 'final'),
        'collection_id':'beta:sst:regional-period:' + source_sha256,
        'title':{'en':'MUR Miyagi 2020–2023 — provisional regional preview',
            'ja':'MUR宮城2020–2023 — 暫定的な地域プレビュー'},
        'purpose':{'en':'Descriptive access to retained operational regional foundation SST, preserving unreviewed area and quality limits',
            'ja':'未審査の地域・品質制約を保持する、保存済み地域海面水温の記述的参照'},
        'descriptor':{'family':'remote_sensing', 'product_id':'mur', 'product_version':'04.1',
            'spatial_resolution':step, 'spatial_resolution_unit':'degree',
            'temporal_resolution':'daily foundation analysis; source09:00UTC instant retained',
            'measurement':'sea_surface_temperature', 'unit':'degC', 'spatial_role':'regional_summary'},
        'processing_generation':'final', 'measurement_type':'satellite_in_situ_analysis',
        'temporal_statistic':'daily_foundation_analysis', 'calendar':'UTC',
        'observation_precision':'datetime', 'support':definition['diagnostic_rectangle'],
        'observation_entity':'regional_daily_summary', 'sampling':{'frequency':'daily',
            'start':first.isoformat(), 'end':last.isoformat(), 'calendar':'UTC'},
        'spatial_resolution_basis':'Retained source0.05degree grid-point subsampling; not native resolution or confirmed coastal/sample-area coverage',
        'aggregation_method':'Retained producer cosine-latitude grid-point weighted regional summary; no reaggregation by beta',
        'quality_policy':'Retained source valid status under explicitly proposed/unreviewed1K analysis-error,0.8valid-fraction,5point and0.15ice thresholds; missing ice uses open-sea mask warning',
        'uncertainty_policy':'Per-observation uncertainty is absent in this retained preview and remains null; a policy threshold is not a measured uncertainty',
        'qualification':' '.join(QUALIFICATIONS),
        'methods':['Preserve exact original Celsius values and09:00UTC source instants; no new product retrieval',
            'Keep final04.1 and interim04.1nrt distinct; known source gaps are unfilled',
            'Operational descriptive access only; unreviewed regional area and proposed quality remain explicit'],
        'table':{'name':'observations', 'object_id':dataset_id + ':table:observations',
            'row_count':len(records), 'availability':{'status':'available'}, 'completeness':'complete'},
        'related_ids':[]})
    frame = pd.DataFrame(records, columns=TABLE_COLUMNS, dtype=object)
    captured = dataset_exports(dataset, {'observations':frame}, generation=source_sha256)
    return dataset, {'observations':frame}, captured


def summary(data, *, source_sha256=PERIOD_SHA256):
    dataset, frames, captured = regional_dataset(data, source_sha256=source_sha256)
    source = parsed(data)
    return {'state':'qualified_regional_sst_plan_only', 'source_period_sha256':source_sha256,
        'dataset_id':dataset.dataset_id, 'observations':len(frames['observations']),
        'retained_final_series_gaps':len(source['final_series_gaps']),
        'source_utc_instants_preserved':True, 'source_warning_rows':len(frames['observations']),
        'c11_export_bytes':sum(len(value) for value in captured.contents.values()),
        'scientific_approval':False, 'scientific_publication':False, 'area_is_reviewed':False,
        'derived_analyses_excluded':True, 'raw_granule_bodies_reverified':False,
        'cloud_calls':False, 'sealed_or_registered':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--private-publication', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        source_guard(args.revision)
        data = verified_publication_bytes(args.private_publication)
        result = summary(data)
        pins = source_guard(args.revision)
        result['source_revision'] = args.revision
        result['source_pins_sha256'] = hashlib.sha256(canonical(pins)).hexdigest()
    except Exception:
        print(json.dumps({'state':'refused', 'error':'Qualified regional SST preparation failed; inspect private sources',
            'cloud_calls':False, 'scientific_approval':False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
