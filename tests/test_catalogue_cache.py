from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from orchestration.catalogue_cache import VerifiedCatalogueCache


def test_expiry_revision_and_copy_isolation():
    now, rev, calls = [0], ['a'], []
    cache = VerifiedCatalogueCache(clock=lambda:now[0])
    def load():
        calls.append(1)
        return {'analyses':[{'status':'current'}]}
    first, state = cache.get(load, lambda:rev[0])
    first['analyses'][0]['status']='corrupt'
    second, state = cache.get(load, lambda:rev[0])
    assert state['state']=='hit' and second['analyses'][0]['status']=='current'
    now[0]=60
    cache.get(load, lambda:rev[0])
    rev[0]='b'
    cache.get(load, lambda:rev[0])
    assert len(calls)==3


def test_failed_revision_cannot_reuse_saved_catalogue():
    cache = VerifiedCatalogueCache()
    cache.get(lambda:{'current':1},lambda:'a')
    def failed():
        raise OSError('unavailable')
    result, state = cache.get(lambda:{'current':2},failed)
    assert result=={'current':2} and state['revision'] is None and not cache.entries
    with pytest.raises(ValueError):
        cache.get(lambda:(_ for _ in ()).throw(ValueError('corrupt')),lambda:'b')


def test_rollover_during_load_rechecks_and_bounds_revisions():
    cache=VerifiedCatalogueCache()
    rev=['a']
    calls=[]
    def load():
        calls.append(1)
        rev[0]='b'
        return {'generation':rev[0]}
    value,state=cache.get(load,lambda:rev[0])
    assert len(calls)==2 and value['generation']=='b' and state['revision']=='b'
    for i in range(6):
        cache.get(lambda:{},lambda:str(i))
    assert len(cache.entries)==4


def test_single_refresh_for_concurrent_requests():
    cache=VerifiedCatalogueCache()
    entered,release=Event(),Event()
    calls=[]
    def load():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return {'analyses':[]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(cache.get,load,lambda:'a') for _ in range(4)]
        assert entered.wait(2)
        release.set()
        values=[f.result() for f in futures]
    assert len(calls)==1 and sum(state['state']=='hit' for _,state in values)==3


def test_continuous_rollover_and_postload_failure_fail_closed():
    cache=VerifiedCatalogueCache()
    rev=iter(['a','b','c'])
    with pytest.raises(ValueError,match='changed'):
        cache.get(lambda:{},lambda:next(rev))
    assert not cache.entries
