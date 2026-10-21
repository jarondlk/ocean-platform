"""C22 prerequisite/Git/receipt audit only; no tests, services or selection.

Creates new verification/formal-map files exclusively. --check only rereads the
saved pins; later intentional source supersessions require a new audit chain.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = Path('docs/plans/ocean-v1/evidence')
FORMAL = ('C01', 'C07', 'C09', 'C17', 'C21')
SOURCE = '567684b6649ed8a31ed4f89f1a0e223a677f2fe8'
METADATA = '69123408c5bf9caaefe365ef0fc05905c70984c5'
ORIGINAL = '0ab726a243a4c74d584a4894dca1a71158cb9cc2'

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

def read(path):
    return json.loads((ROOT / path).read_text())

def aggregate(files):
    return hashlib.sha256(''.join(f'{p}:{h}\n' for p,h in sorted(files.items())).encode()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def ancestor(a,b):
    subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=ROOT,check=True)

def verify(files):
    wrong=[p for p,h in files.items() if not (ROOT/p).is_file() or sha(p)!=h]
    assert not wrong, wrong

def blobs(commit, paths):
    result={}
    with subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
        for path in sorted(paths):
            proc.stdin.write(f'{commit}:{path}\n'.encode());proc.stdin.flush()
            header=proc.stdout.readline().split();assert len(header)==3 and header[1]==b'blob',(commit,path,header)
            body=proc.stdout.read(int(header[2]));assert len(body)==int(header[2]) and proc.stdout.read(1)==b'\n'
            result[path]=hashlib.sha256(body).hexdigest()
        proc.stdin.close();assert proc.wait()==0
    return result

def committed_evidence(commit):
    listing=subprocess.check_output(['git','ls-tree','-r','-z',commit,'--',str(BASE)],cwd=ROOT)
    paths=[]
    for row in listing.split(b'\0'):
        if not row:continue
        meta,path=row.split(b'\t');mode,kind,_=meta.split();assert mode in (b'100644',b'100755') and kind==b'blob';paths.append(path.decode())
    return blobs(commit,paths)

def collect():
    assert git('branch','--show-current')=='overhaul'
    head=git('rev-parse','HEAD');ancestor(SOURCE,METADATA);ancestor(METADATA,head);ancestor(head,'origin/overhaul')
    assert not [p for p in git('diff','--name-only',SOURCE,head).splitlines() if not p.startswith('docs/plans/ocean-v1/')]
    tracked=committed_evidence(METADATA);verify(tracked)
    pins={};sequence=[];originals={}
    def source_map(c,path,field='files'):
        r=read(path);m=r[field];assert aggregate(m)==r['source_sha256'],path;pins[str(path)]=sha(path);sequence.append((c,str(path),m));return r
    for n in range(1,22):
        c=f'C{n:02}';p=BASE/c/'verification.json';originals[c]=source_map(c,p)['files']
        for suffix in ['accepted-source.json',*{'C13':['method-alias-amendment/accepted-source.json'],'C19':['ci-budget-amendment/accepted-source.json'],'C20':['history-amendment/accepted-source.json']}.get(c,[])]:
            p=BASE/c/suffix
            if (ROOT/p).exists():source_map(c,p)
        if c=='C02':
            p=BASE/'delivery-2026-10-14/verification.json';r=source_map(c,p)
            for stage,details in r['component_receipt_drift'].items():
                for path,change in details['changed_since_component_receipt'].items():
                    assert change['historical_sha256']==originals[stage][path] and change['current_sha256']==r['files'][path]
    local=read(BASE/'C21/verification.json');start=read(BASE/'C21/start-snapshot.json')
    delivered=source_map('C21',BASE/'C21/delivery.json','source_files');hosted=read(BASE/'C21/hosted-ci.json');amend=read(BASE/'C21/ci-budget-amendment/selection.json')
    assert len(start['prior_source_files'])==626 and len(start['prior_evidence_files'])==1068
    assert blobs(start['base_commit'],start['prior_source_files'])==start['prior_source_files']
    changes={p:{'prior':h,'current':local['files'].get(p,h)} for p,h in start['prior_source_files'].items() if local['files'].get(p,h)!=h}
    assert len(changes)==17 and changes==local['intentional_source_supersessions']
    assert len(delivered['source_files'])==51 and delivered['source_commit']==SOURCE
    assert amend['original_source_commit']==ORIGINAL and amend['final_source_files']==delivered['source_files']
    workflow='.github/workflows/tests.yml';old=subprocess.check_output(['git','show',ORIGINAL+':'+workflow],cwd=ROOT);new=subprocess.check_output(['git','show',SOURCE+':'+workflow],cwd=ROOT)
    assert old.replace(b'timeout-minutes: 30',b'timeout-minutes: 60',1)==new
    assert all(local['files'][p]==h for p,h in delivered['source_files'].items() if p!=workflow)
    verify(delivered['source_files']);assert blobs(SOURCE,delivered['source_files'])==delivered['source_files']
    effective={**start['prior_source_files'],**delivered['source_files']};verify(effective)
    tested={**local['tested_transitive_source_files'],workflow:delivered['source_files'][workflow]};assert len(tested)==715;verify(tested);assert blobs(SOURCE,tested)==tested
    for item in [delivered['local_receipt'],delivered['hosted_receipt']]:assert sha(item['path'])==item['sha256']
    run=hosted['run'];assert hosted['source_commit']==SOURCE==run['head_sha'] and run['head_branch']=='overhaul' and run['status']=='completed' and run['conclusion']=='success' and run['id']==39452550964
    required={'Backend tests and security boundary','Frontend typecheck and build','OCEAN v1 prototype tests and build','PostgreSQL migration and metadata integration'}
    jobs={j['name']:j for j in hosted['jobs']};assert all(jobs[n]['status']=='completed' and jobs[n]['conclusion']=='success' for n in required)
    checks=hosted['checks'];assert checks['backend']['passed']==5031 and checks['backend']['skipped']==254 and checks['backend']['coverage_percent']==86.48
    assert checks['postgres_suites']==[82,12,12,21,60,44,23] and sum(checks['postgres_suites'])==254 and checks['frontend_v1_passed']==930 and checks['frontend_legacy_passed']==132
    logs={v['path']:v['sha256'] for v in hosted['logs'].values()};verify(logs)
    assert '5031 passed' in (ROOT/hosted['logs']['backend']['path']).read_text()
    for label,count in [('frontend-v1',930),('frontend-legacy',132)]:assert f'# pass {count}' in (ROOT/hosted['logs'][label]['path']).read_text()
    pg=(ROOT/hosted['logs']['postgres']['path']).read_text();assert all(f'{count} passed' in pg for count in checks['postgres_suites'])
    protected=start['preservation'];assert {k:len(v) for k,v in protected.items()}=={'unrelated_files':30,'scientific_artifacts':7,'serving_files':2,'legacy_frontend_files':106}
    for values in protected.values():verify(values)
    verify(start['prior_evidence_files']);verify(local['evidence_files'])
    entries={};current={}
    for component in FORMAL:
        entries[component]={}
        for path,initial in originals[component].items():
            chain=[];begun=False
            for stage,receipt,files in sequence:
                begun=begun or stage==component
                if begun and path in files and (not chain or files[path]!=chain[-1]['sha256']):chain.append({'component':stage,'receipt':receipt,'receipt_sha256':pins[receipt],'sha256':files[path]})
            expected=chain[-1]['sha256'];assert sha(path)==expected,(component,path);current[path]=expected
            entries[component][path]={'original_sha256':initial,'current_sha256':expected,'intentional_later_supersession':initial!=expected,'acceptance_chain':chain}
    assert blobs(SOURCE,current)==current
    prior_hosted={}
    for c in ['C07','C09','C17']:
        p=BASE/c/'delivery.json';d=read(p);ci=d['hosted_ci'];r=ci.get('run',ci);commit=ci['source_commit'];assert r['conclusion']=='success' and r['head_sha']==commit;ancestor(commit,SOURCE)
        m=d.get('files',read(BASE/c/'accepted-source.json')['files'] if c=='C17' else originals[c]);assert blobs(commit,m)==m
        pins[str(p)]=sha(p);prior_hosted[c]={'receipt':str(p),'receipt_sha256':sha(p),'source_commit':commit,'run_id':r['id'],'conclusion':'success'}
    planning=['README.md','MASTER_PLAN.md','DECISIONS.md','STATUS.md','ACCEPTANCE_MAP.md','SITE_SEPARATION.md','UI_UX_BRIEF.md','PROMPTS.md','components/C22-experiment-proposals.md',*[f'handoffs/{c}.md' for c in FORMAL]]
    planning_pins={str(Path('docs/plans/ocean-v1')/p):sha(Path('docs/plans/ocean-v1')/p) for p in planning}
    status=(ROOT/'docs/plans/ocean-v1/STATUS.md').read_text();assert 'C21 is In progress' not in status and 'Latest delivered implementation: **C21' in status
    pins.update({str(BASE/'C21'/p):sha(BASE/'C21'/p) for p in ['start-snapshot.json','hosted-ci.json','ci-budget-amendment/selection.json','ci-budget-amendment/pushed-checkpoint.json']})
    assert blobs(METADATA,pins)==pins
    return {'component':'C22','state':'prerequisites_verified_awaiting_root_selection','ready_for_selection':True,'component_selected':False,'audited_at':datetime.now(timezone.utc).isoformat(),'branch':'overhaul','head':head,'source_commit':SOURCE,'pushed_metadata_checkpoint':METADATA,'formal_prerequisites':list(FORMAL),'formal_source_entries':sum(map(len,entries.values())),'unique_source_paths':len(current),'source_entries':entries,'formal_current_source_files':current,'formal_current_source_sha256':aggregate(current),'C21_source_files':delivered['source_files'],'C21_tested_transitive_source_files':tested,'C21_prior626_reconciliation':{'original_source_files':start['prior_source_files'],'intentional17_source_supersessions':changes,'workflow_amendment':amend['source_change'],'effective_source_files':effective},'C21_hosted_delivery':{'receipt':str(BASE/'C21/delivery.json'),'receipt_sha256':sha(BASE/'C21/delivery.json'),'source_commit':SOURCE,'run_id':run['id'],'url':run['html_url'],'conclusion':'success','checks':checks,'logs':logs},'prior_hosted_prerequisites':prior_hosted,'immutable_input_receipt_pins_sha256':pins,'planning_document_pins_sha256':planning_pins,'preservation':{'protected_files':protected,'protected_counts':{k:len(v) for k,v in protected.items()},'prior_evidence_files':tracked,'prior_evidence_count':len(tracked),'git_baseline_commit':METADATA,'C21_start_prior_evidence_count':1068,'C21_local_evidence_count':len(local['evidence_files'])},'findings':[],'resolved_metadata_findings':['C21 stale STATUS opening/latest-delivery copy corrected in pushed metadata6912340; no application source changed.'],'missing_user_decisions_for_authorized_local_C22':[],'authorized_boundary':['Owner-private proposal/revision/approval persistence and APIs','Deterministic bounded exports from authorized synthetic sealed artifacts using shared scope/CSV rules','Current-authorization approval/dispatch eligibility and transactional1-user/2-global reservations with a fake executor','No generated Python execution, provider calls, real-data export/transfer, publication, cloud provisioning or deployment; C23 executes and C25 supplies UI.'],'checks_run':'Read-only source/receipt/log/Git/preservation reconciliation only; no application tests/services or component selection','qualifications':['Remote push is verified by local origin/overhaul containing pushed6912340; no fetch or live GitHub query performed.','Original acceptance and failed/pending CI receipts remain immutable; only later explicit accepted source supersessions clear drift.','C01 original local acceptance is reconciled through explicit C01/C02 delivery drift and the current C21 source-bound full suite; no new scientific approval is claimed.','Formal readiness is for root selection of isolated local C22 only; real execution, real inputs, independent scientific validation, live IAM/isolation and deployment remain separately gated.']}

def main():
    if sys.argv[1:]==['--check']:
        r=read(HERE/'verification.json')
        for k in ['formal_current_source_files','C21_source_files','C21_tested_transitive_source_files','immutable_input_receipt_pins_sha256']:verify(r[k])
        for values in r['preservation']['protected_files'].values():verify(values)
        verify(r['preservation']['prior_evidence_files']);print('Saved C22 source/receipt/protection pins match; no selection or writes');return
    assert not sys.argv[1:]
    r=collect()
    prose='# C22 formal readiness map\n\nFormal prerequisites: C01, C07, C09, C17 and C21.\n\n110 original source entries reconcile to99 current unique source paths. Each entry in verification.json retains the original hash and every explicit later acceptance witness. The C01/C02 delivery receipt accounts for early scope-contract corrections; C13, C19 and C20 amendments are preserved. C21 preserves17 prior-source supersessions and its separate workflow-only30-to60-minute CI allowance.\n\nC21 source567684b binds51 current source files and715 tested transitive paths. Exact-source CI39452550964 passes5031 backend/254 gated skips/86.48% coverage,254 actual PostgreSQL cases,930 v1 and132 legacy tests, generated checks, builds/typechecks/audits and backup/restore. The source and delivery metadata6912340 are in origin/overhaul. Prior source, failed CI and audit evidence is immutable.\n\nProtected30 unrelated files,7 scientific artifacts,2 serving files and106 legacy frontend files match their preserved hashes. All evidence tracked in committed metadata6912340 is verified against Git blobs. No tests, services, production operations or component selection were performed.\n\nNo missing user decision blocks the specified local C22 work: owner-private concrete proposal revisions, deterministic bounded frozen exports, approval hashes and current dispatch eligibility with a fake executor. Generated Python execution belongs to C23 and the UI to C25. Every actual experiment still requires its own concrete owner approval; standing implementation authorization grants no scientific approval or real-data/cloud operation.\n\nVerdict: ready for root selection under the standing sequential authorization. This audit does not select C22.\n'
    with (HERE/'formal-map.md').open('x') as out:out.write(prose)
    r['audit_files_sha256']={str((HERE/p).relative_to(ROOT)):sha(HERE/p) for p in ['audit.py','formal-map.md']}
    with (HERE/'verification.json').open('x') as out:json.dump(r,out,indent=2);out.write('\n')
    print(json.dumps({'ready_for_selection':r['ready_for_selection'],'formal_entries':r['formal_source_entries'],'unique_paths':r['unique_source_paths'],'preserved_evidence':r['preservation']['prior_evidence_count'],'receipt_sha256':sha(HERE/'verification.json')}))

if __name__=='__main__':main()
