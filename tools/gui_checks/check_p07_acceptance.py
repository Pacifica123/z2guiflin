#!/usr/bin/env python3
"""One fail-fast/log/archive P07 profile shared by devctl and shell; no root/network mutations."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,sys,zipfile
from p07_process import run_bounded,install_signal_cleanup
from p07_qualification import candidate_binding,load_contract,validate_contract,verify_freeze,junit_outcomes,validated_owner_records,evaluate
ROOT=Path(__file__).resolve().parents[2]

def acceptance_passed(floor,report,*,release=False):
    """Application checks source/tests; release additionally requires every owner gate."""
    return floor=='PASS' and not report.get('error') and (not release or report['promotionAllowed'])

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',action='store_true',help='Require all G01-G21/J1-J7 partitions and independent review')
    parser.add_argument('--v11',action='store_true',help='Current v1.1 deterministic acceptance; archive compatibility audit separately')
    args=parser.parse_args(argv)
    if args.v11 and args.release:parser.error('--v11 and --release are separate acceptance modes')
    install_signal_cleanup()
    logs=ROOT/'.zap2/runtime/acceptance'/('p07-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));logs.mkdir(parents=True)
    env=os.environ.copy()
    for key in ['ZAP2_INSTALLED_ROOT','ZAP2_RESOURCE_ROOT','ZAP2_PRIVILEGED_EXECUTOR']:env.pop(key,None)
    env.update(PYTHONPATH=str(ROOT/'gui'),PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='offscreen',ZAP2_P07_LOG_DIR=str(logs/'regression'))
    (logs/'environment.json').write_text(json.dumps({'python':sys.version,'executable':sys.executable,'platform':sys.platform,'pid':os.getpid(),'procSelf':os.readlink('/proc/self') if Path('/proc/self').exists() else None},indent=2)+'\n')
    stages=[('Candidate PC/source/profile authority freeze',[sys.executable,'tools/gui_checks/p07_qualification.py','--check']),('Generated current reference',[sys.executable,'meta_tools/generate_p06_reference.py','--check']),('Generated ActionContract bindings',[sys.executable,'meta_tools/generate_p04d_action_bindings.py','--check']),('P07 composition/migration/support/falsifiers',[sys.executable,'tools/gui_checks/check_p07_focused.py']),('P03 generation identity and semantic corpus',[sys.executable,'tools/gui_checks/check_p03_core_generation.py']),('Structural current/history gate',[sys.executable,'tools/gui_checks/check_project_tree.py']),('Bounded complete isolated regression L0-L2',[sys.executable,'tools/gui_checks/check_p07_regression.py'])]
    results=[];floor='PASS';records=[];issues=[]
    for i,(name,command) in enumerate(stages,1):
        print(f'[RUN {i}] {name}',flush=True)
        try:
            result=run_bounded(command,cwd=ROOT,env=env,timeout=1800);output=result.output;rc=result.returncode
        except (Exception,KeyboardInterrupt,SystemExit) as exc:output=str(exc)+'\n';rc=1
        (logs/f'{i:02d}.log').write_text(output);print(output,flush=True);results.append({'step':name,'returncode':rc,'command':command})
        if rc:floor='FAIL';break
    try:
        contract=load_contract();binding=candidate_binding();validate_contract();verify_freeze()
        outcomes=junit_outcomes(sorted((logs/'regression').glob('*.xml')))
        records,issues=validated_owner_records(os.environ.get('ZAP2_P07_OWNER_BUNDLE'),binding,contract)
        # Observed source changes during qualification invalidate every attestation.
        if candidate_binding()!=binding:raise ValueError('source changed during qualification')
        report=evaluate(binding,contract,outcomes,records,floor=floor,issues=issues)
    except Exception as exc:
        report={'schemaVersion':1,'result':'BLOCKED','promotionAllowed':False,'deterministicFloor':floor,'error':str(exc),'gateMatrix':[],'journeyMatrix':[]};issues=[{'error':str(exc)}]
    report['steps']=results
    (logs/'qualification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    # Review index carries digests and artifact refs, not source URI/raw network config.
    (logs/'owner-evidence-index.json').write_text(json.dumps({'acceptedClaims':[{'claimId':r['claimId'],'partition':r['partition'],'result':r['result'],'producer':r['producer'],'artifactSha256':[a['sha256'] for a in r['artifacts']]} for r in records],'rejectedRecords':issues},ensure_ascii=False,indent=2)+'\n')
    accepted=acceptance_passed(floor,report,release=args.release)
    summary={'mode':'release' if args.release else 'candidate','applicationAllowed':acceptance_passed(floor,report),'acceptanceResult':'PASS' if accepted else 'FAIL','schemaVersion':1,'patch':'v1.1' if args.v11 else 'P07','version':load_contract()['candidateVersion'],'deterministicResult':floor,'qualificationResult':report['result'],'readiness':('READY_FOR_V11_REVIEW' if accepted else 'BLOCKED') if args.v11 else ('READY_FOR_V1_REVIEW' if report['promotionAllowed'] else 'BLOCKED'),'promotionAllowed':report['promotionAllowed'],'scope':'partitioned qualification; no automatic native/live probes or version/tag mutation','steps':results}
    (logs/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    archive=logs.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(logs.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(logs))
    print('P07 deterministic floor: '+floor)
    for row in report.get('gateMatrix',[])+report.get('journeyMatrix',[]):print(row['id']+': '+row['result'])
    print(('v1.1 compatibility owner audit: ' if args.v11 else 'P07 v1 qualification: ')+report['result']);print('HYPERPATCH ACCEPTANCE: '+('PASS' if accepted else 'FAIL'));print('readiness: '+summary['readiness']);print('evidence archive: '+str(archive))
    print('P07 acceptance mode: '+summary['mode'])
    return 0 if accepted else 1
if __name__=='__main__':raise SystemExit(main())
