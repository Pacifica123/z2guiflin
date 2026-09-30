"""Support export: a positive field allowlist, no free-form logs/config/credentials."""
from pathlib import Path
import hashlib,json,re,zipfile,os
from .project_paths import discover_layout
from .product_identity import identity_snapshot

SAFE_ID=re.compile(r'^[A-Za-z0-9_.:@-]{1,160}$')
SAFE_RESULT={'PASS','FAIL','UNKNOWN','NOT_RUN'}
SAFE_FAILURES={'core_process','local_listener','socks_method','socks_connect','target_tls_timeout','target_tls_eof_or_reset','target_tls_validation','target_tls','target_http_timeout','target_http_eof_or_reset','target_http','gateway_websocket','electron_navigation',''}
SAFE_KINDS={'process','listener','socks_method','socks_connect','target_tls','target_http','websocket','electron_navigation'}

def digest_id(value) -> str:
    return hashlib.sha256(str(value or '').encode()).hexdigest()


def safe_id(value) -> str:
    value=str(value or '')
    return value if SAFE_ID.fullmatch(value) else 'REDACTED'


SAFE_STATES={'running','started','stopped','reverted','not-started','absent','stale','unknown','failed','failed-rolled-back','conflict','migration-required','applied','exited-after-launch'}
SAFE_ACTIONS={'start','stop','status','apply','revert','build','inspect','probe','validate','prepare','confirm'}
SAFE_EVENTS={'runtime-start-planned','runtime-stop-planned','runtime-status-planned','default-start-planned','default-stop-planned','owner-rules-apply-planned','owner-rules-revert-planned','session-started','session-stopped','default-start-started','default-stop-stopped'}

def enum_field(value,allowed,fallback='unknown'):
    return value if isinstance(value,str) and value in allowed else fallback

def lifecycle_projection(root: Path):
    plans=[];runs=[];logs=[]
    for directory,target in [(root/'.zap2/runtime/plans',plans),(root/'.zap2/runtime/sessions',runs)]:
        if not directory.exists() or directory.is_symlink():continue
        for path in sorted(directory.glob('*.json'))[:32]:
            if path.is_symlink() or path.stat().st_size>1024*1024:continue
            try:data=json.loads(path.read_text())
            except (OSError,ValueError):continue
            if not isinstance(data,dict):continue
            target.append({'planIdSha256':digest_id(data.get('planId')),'planHashSha256':digest_id(data.get('planHash')),'runIdSha256':digest_id(data.get('runId')),'action':enum_field(data.get('action'),SAFE_ACTIONS),'state':enum_field(data.get('state'),SAFE_STATES),'confirmed':data.get('confirmed') is True})
    directory=root/'.zap2/runtime/logs'
    if directory.exists() and not directory.is_symlink():
        for path in sorted(directory.glob('*.jsonl'))[:4]:
            if path.is_symlink():continue
            with path.open('rb') as handle:
                for unused in range(32):
                    line=handle.readline(65537)
                    if not line:break
                    if len(line)>65536:break
                    try:data=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if not isinstance(data,dict):continue
                    logs.append({'eventIdSha256':digest_id(data.get('eventId')),'eventType':enum_field(data.get('eventType'),SAFE_EVENTS,'OTHER'),'planHashSha256':digest_id(data.get('planHash')),'level':enum_field(data.get('level'),{'info','warning','error','debug'})})
    return {'plans':plans,'runs':runs,'logEvents':logs,'nextActionByOwnership':{'absent':'inspect then prepare/confirm intended action','owned-active':'inspect current run; use confirmed stop when needed','owned-stale':'collect exact ownership evidence before reconcile','owned-partial':'inspect receipts; confirmed owned cleanup only','foreign-conflict':'leave foreign resources unchanged; choose another owned scope','unknown':'collect evidence; do not mutate unknown resources'}}

def support_snapshot(root: Path | None=None) -> dict:
    layout=discover_layout(root);identity=identity_snapshot(layout.root)
    # Dynamic identity strings can come from external binaries/user state;
    # export only strict IDs, digests and schema integers.
    from .adapters.core_generation import P03_UPSTREAM_REPO,P03_UPSTREAM_VERSION,P03_UPSTREAM_COMMIT
    clean={'productVersion':identity['productVersion'],'upstream':{'name':P03_UPSTREAM_REPO,'version':P03_UPSTREAM_VERSION,'commit':P03_UPSTREAM_COMMIT,'observedMetadataSha256':digest_id(json.dumps(identity['upstream'],sort_keys=True))},'schemas':identity['schemas'],'helper':identity['helper'],'externalCoreIdentity':digest_id(identity['externalCore']['identityHash']),'evidence':{k+'Sha256':digest_id(v) for k,v in identity['evidence'].items()},'service':'plan-only'}
    observations=[];capabilities=[];graph_state='UNKNOWN'
    try:
        from .adapters.discord_tunnel import tunnel_store_paths,_load_running_tunnel_session,_load_bound_evidence_graph
        paths=tunnel_store_paths(layout.root);session=_load_running_tunnel_session(paths,'default')
        if session.get('state')!='running':raise ValueError('not current')
        graph=_load_bound_evidence_graph(paths,'default',session)
        graph_state='CURRENT_RUN_BOUND'
        for span in graph.spans:
            observations.append({'spanIdSha256':digest_id(span.span_id),'kind':span.kind if span.kind in SAFE_KINDS else 'UNKNOWN','result':span.result if span.result in SAFE_RESULT else 'UNKNOWN','failureClass':span.failure_class if span.failure_class in SAFE_FAILURES else 'UNKNOWN','failureClassSha256':digest_id(span.failure_class),'targetSha256':hashlib.sha256(span.target.encode()).hexdigest(),'runIdSha256':digest_id(span.run_id)})
        known={'discord.bootstrap.gateway','vesktop.navigation','vesktop.bootstrap','route.https:updates.discord.com','route.https:discord.com'}
        for verdict in getattr(graph,'verdicts',[]):
            capabilities.append({'capabilityId':verdict.capability_id if verdict.capability_id in known else 'OTHER','capabilityIdSha256':digest_id(verdict.capability_id),'runIdSha256':digest_id(verdict.run_id),'support':verdict.support if verdict.support in {'SUPPORTED','EXPERIMENTAL','UNSUPPORTED','UNKNOWN'} else 'UNKNOWN','missingRequirements':len(verdict.missing_requirements),'failedRequirements':len(verdict.failed_requirements),'evidenceRefsSha256':[digest_id(v) for v in verdict.evidence_refs]})
    except (ValueError,OSError,TypeError,KeyError):pass
    try:
        from .adapters.runtime_kernel import runtime_kernel_status
        runtime=runtime_kernel_status(layout.root)
        state=runtime.ownership_state if runtime.ownership_state in {'absent','owned-active','owned-stale','owned-partial','foreign-conflict','unknown','migration-required'} else 'unknown'
    except (ValueError,OSError,TypeError):state='unknown'
    return {'schemaVersion':1,'identity':clean,'runtimeOwnershipState':state,'networkEvidenceState':graph_state,'observations':observations,'capabilities':capabilities,'lifecycle':lifecycle_projection(layout.root),'excluded':['raw logs','VLESS URI','core config','user profiles','environment variables','filesystem paths','HAR','server addresses','UUID/password/token/key material'],'limits':'typed evidence only; UNKNOWN stays UNKNOWN; no probes run'}


def write_support_bundle(output: Path,root: Path | None=None) -> Path:
    data=support_snapshot(root)
    output=output.absolute()
    if output.exists():raise ValueError('support output already exists; choose a new filename')
    output.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as handle:
        with zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('support.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    output.chmod(0o600)
    return output
