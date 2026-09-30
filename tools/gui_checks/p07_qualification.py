"""Candidate-bound, partitioned P07 qualification. Local attestations are not signatures."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,ast,hashlib,importlib.util,json,os,re,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
CONTRACT='docs/developer/p07-contract.json'
PC='docs/developer/P07_PATCH_CONTRACT.md'
FREEZE='runtime/p07/candidate-freeze.json'

def digest(value):return hashlib.sha256(value).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def load_contract(root=ROOT):return json.loads((root/CONTRACT).read_text())

def source_inventory(root=ROOT):
    spec=importlib.util.spec_from_file_location('p07_release_builder',root/'packaging/build_release.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    paths={p.relative_to(root).as_posix():p for p in builder.source_files(root)}
    for p in (root/'tests').glob('test_*.py'):paths[p.relative_to(root).as_posix()]=p
    return {rel:digest(p.read_bytes()) for rel,p in sorted(paths.items())}

def candidate_binding(root=ROOT):
    files=source_inventory(root)
    # Matches the exact records used by the P06 release builder, not an archive timestamp.
    spec=importlib.util.spec_from_file_location('p07_release_builder',root/'packaging/build_release.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    records={p.relative_to(root).as_posix():{'sha256':digest(p.read_bytes()),'mode':0o755 if p.suffix=='.sh' or p.name=='zap2-runtime-executor' else 0o644} for p in builder.source_files(root)}
    return {'candidateVersion':load_contract(root)['candidateVersion'],'candidateDigest':digest(canonical(files)),'releaseDigest':digest(json.dumps(records,sort_keys=True,separators=(',',':')).encode()),'pcSha256':digest((root/PC).read_bytes()),'profileSha256':digest((root/CONTRACT).read_bytes())}

def validate_contract(root=ROOT):
    c=load_contract(root)
    if c.get('schemaVersion')!=1:raise ValueError('unknown qualification schema')
    if [g['id'] for g in c['gates']]!=[f'G{i:02d}' for i in range(1,22)]:raise ValueError('G01..G21 must be complete and ordered')
    if [g['id'] for g in c['journeys']]!=[f'J{i}' for i in range(1,8)]:raise ValueError('J1..J7 must be complete')
    for item in c['gates']+c['journeys']:
        if item.get('must') is not True or not item['requiredPartitions'] or 'deterministic' not in item['requiredPartitions']:raise ValueError('MUST/partition weakening')
        if len(item['requiredPartitions'])!=len(set(item['requiredPartitions'])):raise ValueError('duplicate required partition')
        if not set(item['requiredPartitions'])<=set(c['partitions']):raise ValueError('unknown evidence partition')
        for rel in item['probes']:
            path=Path(rel)
            if path.is_absolute() or '..' in path.parts or not rel.startswith('tests/test_') or not (root/path).is_file():raise ValueError('missing/unsafe probe: '+rel)
    pre=json.loads((root/'runtime/p07/pre-forensics.json').read_text())
    for rel,expected in pre['preservedAuthorities'].items():
        if digest((root/rel).read_bytes())!=expected:raise ValueError('preserved authority drift: '+rel)
    sys.path.insert(0,str(root/'gui'))
    from zap2_gui import __version__
    version=re.search(r'^version\s*=\s*"([^"]+)"',(root/'pyproject.toml').read_text(),re.M).group(1)
    if version!=c['candidateVersion'] or __version__!=version or version==c['targetVersion']:raise ValueError('candidate/final version inference')
    return c

def verify_freeze(root=ROOT):
    frozen=json.loads((root/FREEZE).read_text());current=candidate_binding(root)
    if frozen.get('schemaVersion')!=1 or frozen['binding']!=current or frozen['files']!=source_inventory(root):raise ValueError('candidate freeze is stale; re-forensics required')
    return frozen

def freeze(root=ROOT):
    validate_contract(root)
    result={'schemaVersion':1,'baseSnapshot':'65b60b2','candidateCommit':None,'commitState':'UNASSIGNED_PRE_APPLY; freeze identifies source snapshot, not a fabricated commit','binding':candidate_binding(root),'files':source_inventory(root),'reviewStatus':'NOT_RUN','meaning':'immutable candidate source/profile/PC binding; not runtime or acceptance evidence'}
    path=root/FREEZE;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result

def junit_outcomes(paths):
    outcomes={}
    for path in paths:
        tree=ET.parse(path)
        for case in tree.iter('testcase'):
            classname=case.get('classname','');rel=classname.replace('.','/')+'.py'
            if not rel.startswith('tests/'):continue
            result='FAIL' if case.find('failure') is not None or case.find('error') is not None else 'NOT_RUN' if case.find('skipped') is not None else 'PASS'
            outcomes.setdefault(rel,[]).append({'case':case.get('name',''),'result':result,'xml':Path(path).name})
    return outcomes

def file_verdict(outcomes,probes):
    results=[x['result'] for p in probes for x in outcomes.get(p,[])]
    if any(p not in outcomes for p in probes):return 'NOT_RUN'
    if 'FAIL' in results:return 'FAIL'
    if 'NOT_RUN' in results or not results:return 'NOT_RUN'
    return 'PASS'

def validated_owner_records(bundle,binding,contract,now=None):
    if bundle is None:return [],[]
    now=now or datetime.now(timezone.utc);path=Path(bundle);base=path.parent.resolve();payload=json.loads(path.read_text());issues=[];records=[]
    if payload.get('schemaVersion')!=1:raise ValueError('unknown owner bundle schema')
    required={'candidateDigest','releaseDigest','pcSha256','profileSha256','candidateVersion'}
    for index,record in enumerate(payload.get('records',[])):
        try:
            if any(record.get('binding',{}).get(k)!=binding[k] for k in required):raise ValueError('stale candidate/profile/release/PC binding')
            if record.get('claimId') not in {x['id'] for x in contract['gates']+contract['journeys']}:raise ValueError('unknown claim')
            if record.get('partition') not in contract['partitions'] or record['partition']=='deterministic':raise ValueError('owner may not replace local deterministic evidence')
            if record.get('result') not in {'PASS','FAIL','NOT_RUN','UNKNOWN'}:raise ValueError('unknown result')
            created=datetime.fromisoformat(record['createdAt'].replace('Z','+00:00'));expires=datetime.fromisoformat(record['expiresAt'].replace('Z','+00:00'))
            if created.tzinfo is None or expires.tzinfo is None or created>now or now>=expires or expires<=created or now-created>timedelta(days=contract['evidenceMaxAgeDays']) or expires-created>timedelta(days=contract['evidenceMaxAgeDays']):raise ValueError('expired/future/unbounded evidence')
            if not record.get('producer') or not record.get('method') or not record.get('environment') or not record.get('scope') or not record.get('limits'):raise ValueError('missing typed producer/method/environment/scope/limits')
            if record['partition']=='review':
                if not record.get('reviewer') or record['reviewer']==record['producer']:raise ValueError('independent reviewer required')
                if record['claimId']=='G21' and not re.fullmatch(r'[0-9a-fA-F]{40}',str(record['scope'].get('candidateCommit',''))):raise ValueError('G21 review requires actual candidate commit; source-only PRE is not a commit receipt')
            artifacts=record.get('artifacts',[])
            if not artifacts:raise ValueError('PASS word without supporting artifact')
            for artifact in artifacts:
                rel=Path(artifact['path']);item=base/rel
                if rel.is_absolute() or '..' in rel.parts or item.is_symlink() or base not in item.resolve().parents:raise ValueError('unsafe artifact path')
                if not item.is_file() or digest(item.read_bytes())!=artifact['sha256']:raise ValueError('missing/changed artifact')
            if record['partition']=='liveNetwork' and record['result']=='PASS':
                # J4 bounded failure is valid journey evidence, not a supported G02 lane.
                bounded=record['claimId']=='J4' and record.get('branch')=='bounded-failure'
                predicates=record.get('predicates',{})
                if not bounded and any(predicates.get(k)!='PASS' for k in ['sourceReceipt','semanticFidelity','coreValidate','targetTls','targetHttp']):raise ValueError('missing current-run VLESS predicates')
                scope=record['scope']
                if not scope.get('runId') or not scope.get('coreVersion') or not scope.get('configHash') or not scope.get('connectionReceiptId'):raise ValueError('unbound live lane identity')
                if not bounded and (scope.get('core')!='Xray' or scope.get('transport')!='tcp' or scope.get('security')!='tls'):raise ValueError('live lane outside frozen support profile; amendment required')
                if bounded and not record.get('nextExperiment'):raise ValueError('bounded failure needs next experiment')
            if record['partition']=='targetApp' and record['result']=='PASS':
                if any(record.get('predicates',{}).get(k)!='PASS' for k in ['updatesHttp','discordHttp','gatewayWebsocket','electronNavigation']):raise ValueError('incomplete Vesktop aggregate')
                if not record['scope'].get('appVersion') or not record['scope'].get('runId'):raise ValueError('target app identity required')
            records.append(record)
        except (ValueError,KeyError,TypeError,OSError) as exc:issues.append({'record':index,'error':str(exc)})
    return records,issues

def evaluate(binding,contract,outcomes,records=(),*,floor='PASS',issues=()):
    matrix=[]
    for item in contract['gates']+contract['journeys']:
        cells=[]
        for partition in item['requiredPartitions']:
            if partition=='deterministic':
                value=file_verdict(outcomes,item['probes'])
                if item['id'] in {'G16','G21'} and floor!='PASS':value='FAIL'
                cells.append({'partition':partition,'result':value,'evidenceRefs':item['probes'],'scope':'current local tests only; no privilege/live/package-native inference'})
            else:
                applicable=[r for r in records if r['claimId']==item['id'] and r['partition']==partition]
                # Failures never disappear because another producer submitted PASS.
                results=[r['result'] for r in applicable]
                value='FAIL' if 'FAIL' in results else 'UNKNOWN' if 'UNKNOWN' in results else 'NOT_RUN' if 'NOT_RUN' in results or not results else 'PASS'
                cells.append({'partition':partition,'result':value,'evidenceRefs':[{'sha256':a['sha256']} for record in applicable for a in record['artifacts']],'scope':'owner artifact claim; not cryptographically authenticated'})
        result='FAIL' if any(c['result']=='FAIL' for c in cells) else 'NOT_RUN' if any(c['result']=='NOT_RUN' for c in cells) else 'UNKNOWN' if any(c['result']=='UNKNOWN' for c in cells) else 'PASS'
        matrix.append({'id':item['id'],'claim':item['claim'],'must':True,'result':result,'cells':cells,'unknownClass':None if result=='PASS' else 'resolvable_blocking'})
    passed=all(row['result']=='PASS' for row in matrix) and floor=='PASS' and not issues
    return {'schemaVersion':1,'binding':binding,'result':'PASS' if passed else 'BLOCKED','targetVersion':contract['targetVersion'],'promotionAllowed':passed,'deterministicFloor':floor,'gateMatrix':[x for x in matrix if x['id'].startswith('G')],'journeyMatrix':[x for x in matrix if x['id'].startswith('J')],'blockingClaims':[x['id'] for x in matrix if x['result']!='PASS'],'ownerBundleIssues':list(issues),'limits':'partitions are conjunctive; local tests do not prove owner runtime, live network or independent review'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--binding',action='store_true');args=parser.parse_args()
    if args.freeze:result=freeze();print('P07 freeze: PASS '+result['binding']['candidateDigest']);return 0
    if args.binding:print(json.dumps(candidate_binding(),indent=2));return 0
    validate_contract();verify_freeze();print('P07 candidate/PC/profile/authority freeze: PASS');return 0
if __name__=='__main__':raise SystemExit(main())
