"""Qualified environmental context. No legacy bay-centroid/time-only links."""
from datetime import timedelta
import math
from typing import Literal

from pydantic import Field, model_validator
from scipy.stats import spearmanr

from ingestion.immutable_bundle import digest
from preprocessing.edna_recipe import StrictModel
from schema.time_range import utc_time


class EnvironmentObservation(StrictModel):
    observation_id: str = Field(min_length=1, max_length=128)
    source_type: Literal['ctd', 'remote_sensing']
    measurement_type: Literal['ctd_bulk', 'sst_skin', 'sst_regional']
    variable: Literal['temperature', 'salinity']
    value: float
    unit: Literal['degC', 'PSU']
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    depth_m: float = Field(ge=0, le=12000)
    time_start: str
    time_end: str | None = None
    domain_id: str = Field(min_length=1, max_length=128)
    coordinate_basis: Literal['measured', 'reviewed_registry', 'footprint_reference']
    coordinate_uncertainty_km: float = Field(ge=0, le=100)
    source_file_id: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_row_locator: str = Field(min_length=1, max_length=500)
    source_reference: str = Field(min_length=1, max_length=1000)
    footprint: tuple[float, float, float, float] | None = None
    valid_fraction: float | None = Field(None, ge=0, le=1)
    quality_status: Literal['valid', 'invalid', 'unknown'] = 'unknown'

    @model_validator(mode='after')
    def valid(self):
        start, end = observation_interval(self.time_start, self.time_end)
        if start > end:
            raise ValueError('Reversed observation interval')
        if self.unit != ('degC' if self.variable == 'temperature' else 'PSU'):
            raise ValueError('Invalid environmental units')
        if (self.source_type == 'ctd') != (self.measurement_type == 'ctd_bulk'):
            raise ValueError('Incompatible source/measurement type')
        if self.source_type == 'remote_sensing' and self.variable != 'temperature':
            raise ValueError('SST observations must measure temperature')
        if self.footprint:
            a,b,c,d = self.footprint
            if not (-90 <= a <= b <= 90 and -180 <= c <= d <= 180):
                raise ValueError('Invalid SST footprint')
        return self


def observation_interval(start, end=None):
    lower = utc_time(start)
    upper = utc_time(end) if end else lower + timedelta(days=1) if len(start) == 10 else lower
    return lower, upper


def distance_km(a, b):
    if any(r.get(k) is None for r in (a, b) for k in ('lat', 'lon')):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a['lat'], a['lon'], b['lat'], b['lon']))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


def metadata_report(recipe, inputs):
    from preprocessing.edna_analysis import metadata
    rows = []
    for sample in inputs['edna_sample']:
        raw = metadata(sample)
        for field in recipe.metadata_fields:
            value = None
            status = 'unknown_unit'
            if raw.get(field.unit_key) == field.unit:
                try:
                    value = float(raw[field.value_key])
                    if not math.isfinite(value) or (field.variable != 'temperature' and value < 0):
                        raise ValueError('invalid value')
                    status = 'available'
                except (KeyError, ValueError, TypeError):
                    value, status = None, 'missing_or_invalid_value'
            rows.append(dict(sample_id=sample['sample_id'], variable=field.variable, value=value, unit=field.unit,
                status=status, raw_value=raw.get(field.value_key), raw_unit=raw.get(field.unit_key),
                value_key=field.value_key, unit_key=field.unit_key, mapping_reference=field.reference,
                source_file_id=sample.get('source_file_id'), source_snapshot_id=sample.get('source_snapshot_id'),
                source_row_locator=sample.get('source_row_numbers_json'), source_row_hash=sample.get('source_row_hash')))
    return rows


def qualified_links(recipe, samples, measurements, observations):
    output = []
    sites = {s.sample_id: s for s in recipe.sites}
    depths = {m['sample_id']: m['value'] for m in measurements if m['variable'] == 'depth' and m['status'] == 'available'}
    profile = recipe.linkage_profile
    if not profile:
        return [dict(sample_id=s['sample_id'], status='linkage_disabled') for s in samples]
    if len(samples)*len(observations) > recipe.max_comparisons:
        raise ValueError('Environmental comparison resource limit exceeded')
    for sample in samples:
        sid = sample['sample_id']
        site = sites.get(sid)
        if not observations:
            output.append(dict(sample_id=sid, status='no_environmental_observations'))
        for target in observations:
            t = target.model_dump()
            distance = distance_km(sample, t)
            reason = None
            lower = upper = None
            try:
                a,b = observation_interval(sample['collection_date_utc'])
                c,d = observation_interval(t['time_start'], t['time_end'])
                upper = max(abs((a-d).total_seconds()), abs((b-c).total_seconds()))/3600
                lower = max(0, (c-b).total_seconds(), (a-d).total_seconds())/3600
            except (TypeError, ValueError, KeyError):
                reason = 'time_unavailable'
            if not site or site.domain_id != profile.domain_id or t['domain_id'] != profile.domain_id:
                reason = 'domain_unverified'
            elif any(r.get('lat') is None or r.get('lon') is None or not (profile.lat_min <= r['lat'] <= profile.lat_max and profile.lon_min <= r['lon'] <= profile.lon_max) for r in (sample, t)):
                reason = 'outside_reviewed_domain'
            elif max(site.coordinate_uncertainty_km, t['coordinate_uncertainty_km']) > profile.max_coordinate_uncertainty_km:
                reason = 'coordinate_uncertainty'
            elif distance is None or distance + site.coordinate_uncertainty_km + t['coordinate_uncertainty_km'] > profile.max_distance_km:
                reason = 'distance_exceeded'
            elif upper is not None and upper > profile.max_time_hours:
                reason = 'time_window_exceeded'
            elif sid not in depths or abs(depths[sid]-t['depth_m']) > profile.max_depth_difference_m:
                reason = 'depth_unavailable_or_incompatible'
            elif t['quality_status'] != 'valid':
                reason = 'quality_not_validated'
            elif t['coordinate_basis'] == 'footprint_reference' and t['measurement_type'] != 'sst_regional':
                reason = 'coordinate_basis_incompatible'
            if target.source_type == 'remote_sensing' and reason is None:
                f = t['footprint']
                if not f or not (f[0] <= sample['lat'] <= f[1] and f[2] <= sample['lon'] <= f[3]) or not (f[0] <= t['lat'] <= f[1] and f[2] <= t['lon'] <= f[3]):
                    reason = 'outside_sst_footprint'
                elif t['valid_fraction'] is None or t['valid_fraction'] < profile.min_valid_fraction:
                    reason = 'insufficient_sst_coverage'
                elif target.measurement_type == 'sst_regional' and not profile.allow_regional_sst:
                    reason = 'regional_context_disabled'
            output.append(dict(sample_id=sid, observation_id=target.observation_id, variable=target.variable,
                value=target.value, unit=target.unit, source_type=target.source_type,
                measurement_type=target.measurement_type, status=reason or 'qualified', selected=False,
                distance_km=distance, time_separation_min_hours=lower, time_separation_max_hours=upper,
                sample_time=sample.get('collection_date_utc'), sample_lat=sample.get('lat'), sample_lon=sample.get('lon'),
                sample_depth_m=depths.get(sid), target=t, profile_id=profile.profile_id,
                profile_sha256=digest(profile.model_dump()), sample_source_file_id=sample.get('source_file_id')))
    # One selected observation per sample/source/variable; no pseudoreplicates.
    groups = {}
    for row in output:
        if row['status'] == 'qualified':
            key = row['sample_id'], row['source_type'], row['variable']
            order = row['time_separation_max_hours'], row['distance_km'], row['observation_id']
            if key not in groups or order < groups[key][0]:
                groups[key] = order, row
    for _, row in groups.values():
        row['selected'] = True
    return output


def environmental_reports(recipe, inputs, diversity, environment):
    observations = [EnvironmentObservation.model_validate(row) for row in environment]
    if len({o.observation_id for o in observations}) != len(observations):
        raise ValueError('Duplicate environmental observation ID')
    measurements = metadata_report(recipe, inputs)
    samples = [s for s in inputs['edna_sample'] if s.get('sample_kind') == 'environmental' and s.get('is_control') is False]
    links = qualified_links(recipe, samples, measurements, observations)
    pairs = []
    for row in diversity:
        values = [dict(m, evidence_type='anemone_metadata') for m in measurements if m['sample_id'] == row['sample_id'] and m['status'] == 'available' and m['variable'] in {'temperature', 'salinity'}]
        values.extend(dict(m, evidence_type=m['measurement_type']) for m in links if m['sample_id'] == row['sample_id'] and m.get('selected'))
        for value in values:
            pairs.append(dict(sample_id=row['sample_id'], assay_id=row['assay_id'], assignment_method=row['assignment_method'],
                partition_id=row['partition_id'], rank=row['rank'], variable=value['variable'], value=value['value'], unit=value['unit'],
                evidence_type=value['evidence_type'], richness=row['richness'], shannon=row['shannon'], evidence=value))
    correlations = []
    groups = {(r['partition_id'], r['variable'], r['evidence_type']) for r in pairs}
    sites = {s.sample_id: s.site_id for s in recipe.sites}
    for partition, variable, kind in sorted(groups):
        rows = [r for r in pairs if (r['partition_id'], r['variable'], r['evidence_type']) == (partition, variable, kind)]
        for metric in ('richness', 'shannon'):
            valid = [r for r in rows if r[metric] is not None]
            x, y = [r['value'] for r in valid], [r[metric] for r in valid]
            rho = float(spearmanr(x, y).statistic) if len(valid) >= 3 and len(set(x)) > 1 and len(set(y)) > 1 else None
            correlations.append(dict(partition_id=partition, assignment_method=rows[0]['assignment_method'], variable=variable,
                evidence_type=kind, metric=metric, spearman_rho=rho, pairs=len(valid),
                samples=len({r['sample_id'] for r in valid}), sites=len({sites[r['sample_id']] for r in valid if r['sample_id'] in sites}),
                status='descriptive_only' if rho is not None else 'insufficient_pairs_or_variation',
                replicate_design='not_inferred', excluded_pairs=len(rows)-len(valid)))
    return dict(metadata=measurements, environment_links=links, environment_pairs=pairs, associations=correlations)
