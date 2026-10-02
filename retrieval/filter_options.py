"""Bounded, searchable choices from the same active corpus used by chat."""
from copy import deepcopy

from sqlalchemy import text

import config
from db.connection import get_session
from ingestion.artifact_store import ArtifactStore
from ingestion.provenance_snapshot import SnapshotError
from retrieval.edna_document_builder import TAXON_COLUMNS
from retrieval.local_retriever import LocalRetriever
from retrieval.source_scope import FAMILIES, document_matches, scope_sql

OPTION_FIELDS = {
    'ctd': ('bay', 'station', 'sample_id'),
    'metagenome': ('bay', 'station', 'sample_id'),
    'remote_sensing': (),
    'edna_metabarcoding': ('sample_id', 'provider', 'provider_project_id', 'provider_run_id',
                         'assignment_method', 'taxon', 'sample_kind', 'is_control'),
}
OPTION_LIMIT = 100


def _facet_scope(scope, family, field):
    result = deepcopy(scope)
    for key in FAMILIES:
        result['sources'][key]['enabled'] = key == family
    # A choice must fit the other filters, but can replace its own selection.
    result['sources'][family]['filters'].pop(field, None)
    return result


def _value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _page(values):
    return {'values': values[:OPTION_LIMIT], 'truncated': len(values) > OPTION_LIMIT}


def _publication_predicate():
    """Mirror hybrid retrieval's remote eDNA publication generation guard."""
    if not config.EDNA_ARTIFACT_URI:
        return 'TRUE', {}
    try:
        pointer, _ = ArtifactStore(config.EDNA_ARTIFACT_URI).pointer('retrieval/current.json')
    except (ValueError, OSError, KeyError, SnapshotError):
        pointer = None
    if not pointer or pointer.get('status') != 'ready':
        return "rd.source_type <> 'edna_metabarcoding'", {}
    return ("(rd.source_type <> 'edna_metabarcoding' OR EXISTS "
            "(SELECT 1 FROM corpus_publication publication WHERE publication.channel = 'edna' "
            "AND publication.generation_id = :published_generation "
            "AND publication.manifest_sha256 = :published_manifest))", {
                'published_generation': pointer.get('generation_id'),
                'published_manifest': pointer.get('manifest_sha256'),
            })


def _postgres_options(scope, fields, search, members, methods):
    publication, published_params = _publication_predicate()
    sources = {}
    with get_session() as session:
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        for family, keys in fields.items():
            available = bool(session.execute(text(
                'SELECT EXISTS (SELECT 1 FROM retrieval_document rd WHERE rd.active IS TRUE '
                f'AND rd.source_type = :family AND {publication})'
            ), {'family': family, **published_params}).scalar())
            options = {}
            for field in keys:
                predicate, params = scope_sql(_facet_scope(scope, family, field), alias='rd',
                                              sample_ids=members, assignment_methods=methods)
                joins = ''
                column = f'CAST(rd.{field} AS text)'
                if field == 'taxon':
                    # Full canonical taxonomy, including terms outside featured text.
                    joins = ('JOIN edna_detection detection ON detection.assay_id = rd.assay_id '
                             'AND detection.assignment_method = rd.assignment_method '
                             'AND detection.active IS TRUE CROSS JOIN LATERAL (VALUES '
                             + ','.join(f'(detection."{rank}")' for rank in TAXON_COLUMNS)
                             + ') AS taxa(value)')
                    column = 'taxa.value'
                statement = (f'SELECT DISTINCT {column} AS value FROM retrieval_document rd {joins} '
                             f'WHERE rd.active IS TRUE AND {publication} AND {predicate} '
                             f"AND {column} IS NOT NULL AND {column} <> '' "
                             f'AND strpos(lower({column}), lower(:search)) > 0 '
                             'ORDER BY value LIMIT :limit')
                rows = session.execute(text(statement), {**params, **published_params,
                                                          'search': search, 'limit': OPTION_LIMIT + 1})
                options[field] = _page([str(row.value) for row in rows])
            sources[family] = {'available': available, 'fields': options}
    return {'backend': 'postgres', 'sources': sources}


def _local_options(scope, fields, search, members, methods):
    # load() reads and normalizes the published JSONL; it never embeds or calls a model.
    retriever = LocalRetriever()
    retriever.load()
    sources = {}
    for family, keys in fields.items():
        documents = [d for d in retriever.documents if d.get('source_type') == family]
        options = {}
        for field in keys:
            facet = _facet_scope(scope, family, field)
            values = set()
            for document in documents:
                if not document_matches(document, facet):
                    continue
                if family == 'edna_metabarcoding':
                    if members is not None and document.get('sample_id') not in members:
                        continue
                    if methods is not None and document.get('assignment_method') not in methods:
                        continue
                metadata = {**(document.get('metadata') or {}), **document}
                candidates = metadata.get('taxon_terms', []) if field == 'taxon' else [metadata.get(field)]
                values.update(_value(value) for value in candidates if value is not None
                              and str(value) and search.casefold() in _value(value).casefold())
            options[field] = _page(sorted(values))
        sources[family] = {'available': bool(documents), 'fields': options}
    return {'backend': 'local', 'sources': sources}


def filter_options(scope, *, pg_available, family=None, field=None, search='', members=None, methods=None):
    # Field names used in SQL only come from this fixed allowlist.
    if family is not None and family not in OPTION_FIELDS:
        raise ValueError('Unknown source family')
    if field is not None and (family is None or field not in OPTION_FIELDS[family]):
        raise ValueError('Unknown selection field')
    fields = {key: (field,) if field else values for key, values in OPTION_FIELDS.items()
              if family is None or key == family}
    return (_postgres_options if pg_available else _local_options)(scope, fields, search.strip(), members, methods)
