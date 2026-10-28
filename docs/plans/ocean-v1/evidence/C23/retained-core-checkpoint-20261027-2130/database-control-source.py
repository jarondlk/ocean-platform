"""Private operator control: new isolated synthetic SCRAM cluster only.
No credential file/log from this directory is an evidence artifact or guest input.
"""
from pathlib import Path
import json, os, secrets, socket, subprocess, sys, time, uuid
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from orchestration.experiment_sandbox.execution_store import ExecutionRolePolicy, ExecutionStoreConfig, bootstrap_retained_controller_reads
from orchestration.experiment_sandbox.proofs import TerminationVerifierRegistry, PinnedTerminationIssuer
from schema.experiment_execution import TerminationIssuerScope
from db.app_models import AppBase
from db.experiment_execution_models import EXECUTION_MODELS
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
ROOT=Path('/Users/jaronchai/Documents/GitHub/provenance-eco-rag')
BINARY=Path('/opt/homebrew/opt/postgresql@18/bin')
assert len(sys.argv)==3 and sys.argv[2] in {'scientific','publication-revoked'}
CONTROL=Path('/private/tmp/c23-retained-control-20261027-v1-'+sys.argv[2])
WORKER_PORT=55423 if sys.argv[2]=='scientific' else 55424
os.umask(0o077)
def save(path,value):
    with path.open('x') as f: json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
def call(name,argv,*,env=None):
    with (CONTROL/(name+'.stdout')).open('xb') as stdout,(CONTROL/(name+'.stderr')).open('xb') as stderr:
        return subprocess.run(argv,stdout=stdout,stderr=stderr,cwd=ROOT,env=env,timeout=120,check=False).returncode

def shutdown(prefix,port):
    tag=prefix+'-'+uuid.uuid4().hex
    checks={'observation_tag':tag}
    for label,args in (
        ('stop',[str(BINARY/'pg_ctl'),'-D',str(CONTROL/'data'),'-m','fast','-w','stop']),
        ('status',[str(BINARY/'pg_ctl'),'-D',str(CONTROL/'data'),'status'])):
        try: checks[label+'_exit']=call(tag+'-'+label,args)
        except BaseException as failure: checks[label+'_error_type']=type(failure).__name__
    try:
        with socket.socket() as probe:
            probe.settimeout(2)
            try: probe.connect(('127.0.0.1',port));checks['tcp_refused']=False
            except ConnectionRefusedError: checks['tcp_refused']=True
    except BaseException as failure:
        checks['tcp_refused']=False;checks['tcp_error_type']=type(failure).__name__
    for label,path in [('pid',CONTROL/'data/postmaster.pid'),('socket',CONTROL/'socket'/('.s.PGSQL.'+str(port)))]:
        try: checks[label+'_absent']=not path.exists()
        except BaseException as failure: checks[label+'_error_type']=type(failure).__name__
    checks['shutdown_verified']=(checks.get('stop_exit')==0 and checks.get('status_exit')==3
        and checks.get('tcp_refused') is True and checks.get('pid_absent') is True and checks.get('socket_absent') is True)
    save(CONTROL/('public-'+tag+'.json'),checks)
    return checks

def prepare():
    CONTROL.mkdir(mode=0o700,exist_ok=False)
    (CONTROL/'socket').mkdir(mode=0o700)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    suffix=uuid.uuid4().hex[:16]
    database='ocean_c23_retained_'+suffix
    schema='c23_retained_'+suffix
    admin='c23_control_admin'
    password=secrets.token_hex(32)
    roles=ExecutionRolePolicy(*(f'c23_{name}_{suffix}' for name in ('serving','controller','verifier','owner')))
    passwords={getattr(roles,name):secrets.token_hex(32) for name in ('serving_role','controller_role','verifier_role')}
    pwfile=CONTROL/'bootstrap-password'
    pwfile.write_text(password+'\n');pwfile.chmod(0o600)
    base=URL.create('postgresql+psycopg2',username=admin,password=password,host='127.0.0.1',port=port,database='postgres')
    control={'version':'c23-private-database-control-v1','cluster':str(CONTROL/'data'),'port':port,'database_name':database,'schema':schema,'admin_dsn':base.set(database=database).render_as_string(hide_password=False),'roles':{k:getattr(roles,k) for k in roles.__dataclass_fields__},'role_passwords':passwords,'created_at_ns':time.time_ns()}
    save(CONTROL/'private-control.json',control)
    startup_attempted=False
    try:
        assert call('initdb',[str(BINARY/'initdb'),'-D',str(CONTROL/'data'),'-U',admin,'--auth-host=scram-sha-256','--auth-local=scram-sha-256','--pwfile='+str(pwfile),'--encoding=UTF8','--locale=C'])==0
        startup_attempted=True
        assert call('start',[str(BINARY/'pg_ctl'),'-D',str(CONTROL/'data'),'-l',str(CONTROL/'private-server.log'),'-o',f'-h 127.0.0.1 -p {port} -k {CONTROL / "socket"}','-w','start'])==0
        engine=create_engine(base,isolation_level='AUTOCOMMIT',hide_parameters=True)
        with engine.connect() as connection: connection.exec_driver_sql(f'CREATE DATABASE {database}')
        engine.dispose()
        dburl=base.set(database=database)
        engine=create_engine(dburl,hide_parameters=True)
        with engine.begin() as connection: connection.exec_driver_sql(f'CREATE SCHEMA {schema}')
        options=f'-csearch_path={schema} -clock_timeout=8000 -cstatement_timeout=20000'
        env=dict(os.environ,DATABASE_URL=dburl.update_query_dict({'options':options}).render_as_string(hide_password=False),AUTH_MODE='disabled',DEPLOYMENT_ENV='test',ENABLE_MOCK_LOGIN='false',PERSIST_LOCAL_CHAT='false')
        assert call('migrate',[str(ROOT/'.venv/bin/python'),'-m','alembic','upgrade','20261027_0021'],env=env)==0
        scoped=create_engine(dburl,connect_args={'options':options},hide_parameters=True)
        # Synthetic temporary registry satisfies strict setup types only. It
        # grants no runtime/proof authority and is NEVER transferred or used.
        setupkey=Ed25519PrivateKey.generate()
        scope=TerminationIssuerScope(site_id='v1:c17-synthetic',image_digest='sha256:'+'a'*64,**{n:'a'*64 for n in TerminationIssuerScope.model_fields if n not in {'site_id','image_digest'}})
        registry=TerminationVerifierRegistry(trust_scope='synthetic-software-test',issuers=[PinnedTerminationIssuer(issuer_id='setup-only',key_id='setup-only',trust_scope='synthetic-software-test',public_key=setupkey.public_key().public_bytes_raw(),scope=scope)])
        config=ExecutionStoreConfig(site_id='v1:c17-synthetic',database_name=database,schema=schema,controller_session_factory=lambda:None,recorder_session_factory=lambda:None,roles=roles,verifier_registry=registry,store_scope='isolated-unmounted-operator')
        with scoped.begin() as connection:
            assert connection.scalar(text('SELECT current_database()'))==database
            for role in roles.__dataclass_fields__:
                name=getattr(roles,role)
                login='LOGIN PASSWORD :password' if name in passwords else 'NOLOGIN'
                connection.execute(text(f'CREATE ROLE {name} {login} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'), {'password':passwords[name]} if name in passwords else {})
            bootstrap_retained_controller_reads(connection,config=config)
            exclude={m.__tablename__ for m in EXECUTION_MODELS}
            for table in AppBase.metadata.tables.values():
                if table.name not in exclude:
                    connection.exec_driver_sql(f'GRANT SELECT,INSERT,UPDATE ON TABLE {schema}.{table.name} TO {roles.serving_role}')
        identities=[]
        for name in passwords:
            role_engine=create_engine(dburl.set(username=name,password=passwords[name]),connect_args={'options':options},hide_parameters=True)
            with role_engine.connect() as connection:
                row=connection.execute(text('SELECT current_database(),current_schema(),current_user,session_user,host(inet_server_addr())')).one()
                assert tuple(row)==(database,schema,name,name,'127.0.0.1')
                identities.append(list(row))
            role_engine.dispose()
        with scoped.connect() as connection:
            grants=[dict(row._mapping) for row in connection.execute(text("SELECT grantee,table_name,privilege_type FROM information_schema.role_table_grants WHERE table_schema=:s ORDER BY grantee,table_name,privilege_type"),{'s':schema})]
            role_state=[dict(row._mapping) for row in connection.execute(text('SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls FROM pg_roles WHERE rolname = ANY(:names) ORDER BY rolname'),{'names':list(control['roles'].values())})]
        scoped.dispose();engine.dispose()
        save(CONTROL/'public-setup.json',{'version':'c23-retained-native-database-setup-v1','database_name':database,'schema':schema,'port':port,'local_host_auth':'scram-sha-256','private_socket_mode':'0700','identities':identities,'roles':role_state,'table_grants':grants,'setup_registry_scope':'synthetic-software-test, setup type validation only; not runtime authority','admin_credentials_transferred':False,'actual_linux_execution':False,'C23_complete':False})
        worker={'database_name':database,'schema':schema,'roles':control['roles']}
        for key,role in [('application_dsn',roles.serving_role),('controller_dsn',roles.controller_role),('verifier_dsn',roles.verifier_role)]:
            worker[key]=dburl.set(username=role,password=passwords[role],port=WORKER_PORT).render_as_string(hide_password=False)
        save(CONTROL/'private-worker-database.json',worker)
        key=Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
        (CONTROL/'private-issuer-key').write_bytes(key)
        print(json.dumps({'prepared':True,'port':port,'database_name':database,'schema':schema,'credentials_logged':False}))
    except BaseException:
        # An absent start acknowledgement never proves an absent postmaster.
        if startup_attempted:
            try: shutdown('prepare-failure',port)
            except BaseException: pass  # Preserve original error; no cleanup claim.
        raise

def cleanup():
    assert CONTROL.resolve()==CONTROL and CONTROL.stat().st_uid==os.geteuid()
    config=json.loads((CONTROL/'private-control.json').read_text())
    assert config['cluster']==str(CONTROL/'data')
    empty=False;engine=None
    try:
        engine=create_engine(config['admin_dsn'],hide_parameters=True)
        with engine.begin() as connection:
            # Retained rows cannot be discarded until root verifies the export.
            assert (CONTROL/'export-verified').read_text().strip()=='c23-synthetic-export-verified'
            schema=config['schema'];connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS {schema} CASCADE')
            for name in reversed(list(config['roles'].values())):
                if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:n)'),{'n':name}):
                    connection.exec_driver_sql(f'DROP OWNED BY {name}')
                    connection.exec_driver_sql(f'DROP ROLE {name}')
            assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)'),{'s':schema})
            assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY(:names))'),{'names':list(config['roles'].values())})
        # Only acknowledged commit plus a fresh independently observed catalog
        # absence supports the deletion receipt; unknown ACK remains unknown.
        with engine.connect() as connection:
            assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)'),{'s':config['schema']})
            assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY(:names))'),{'names':list(config['roles'].values())})
        empty=True
    finally:
        try:
            if engine is not None: engine.dispose()
        finally:
            evidence=shutdown('cleanup',config['port'])
            evidence['roles_schema_absent']=empty
            save(CONTROL/('public-cleanup-summary-'+uuid.uuid4().hex+'.json'),evidence)
            print(json.dumps(evidence))
    assert empty and evidence.get('shutdown_verified') is True, 'Owned cluster cleanup did not pass all physical/catalog gates'
if __name__=='__main__':
    assert sys.argv[1] in {'prepare','cleanup'}
    try:
        (prepare if sys.argv[1]=='prepare' else cleanup)()
    except BaseException as error:
        # Utility DDL diagnostics may contain credentials even when the engine
        # hides bind parameters. Never emit an unsanitized traceback to tools.
        if CONTROL.is_dir():
            import traceback
            with (CONTROL/('private-failure-'+uuid.uuid4().hex+'.log')).open('x') as stream:
                traceback.print_exc(file=stream)
        print(json.dumps({'operation':sys.argv[1],'case':sys.argv[2],'succeeded':False,'error_type':type(error).__name__,'private_diagnostics_retained':True}))
        raise SystemExit(1)
