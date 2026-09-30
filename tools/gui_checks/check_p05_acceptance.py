#!/usr/bin/env python3
"""One deterministic acceptance pipeline shared by devctl and owner shell wrapper.

It mirrors run_step/fail-fast/log+archive of hyperpatch_acceptance.sh without
root canaries. Tests run in temporary copies; only evidence output is written.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    logs=ROOT/'.zap2/runtime/acceptance'/('p05-'+stamp);logs.mkdir(parents=True)
    env=os.environ.copy();env.update(PYTHONPATH=str(ROOT/'gui'),PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='offscreen', ZAP2_P05_LOG_DIR=str(logs/'regression'))
    (logs/'environment.json').write_text(json.dumps({'python':sys.version,'executable':sys.executable,'platform':sys.platform,'pid':os.getpid(),'procSelf':os.readlink('/proc/self') if Path('/proc/self').exists() else None},indent=2)+'\n')
    stages=[
        ('P05 projection and PRE bindings',[sys.executable,'tools/gui_checks/check_p05_projection.py']),
        ('P05 GUI dependencies',[sys.executable,'-c','import pytest,PyQt6; print("pytest/PyQt6: PASS")']),
        ('P05 focused search help errors health GUI',[sys.executable,'tools/gui_checks/check_p05_focused.py']),
        ('Generated action metadata',[sys.executable,'meta_tools/generate_p04d_action_bindings.py','--check']),
        ('P03 generation identity preserved',[sys.executable,'tools/gui_checks/check_p03_core_generation.py']),
        ('Project tree structural gate',[sys.executable,'tools/gui_checks/check_project_tree.py']),
        ('Full isolated regression',[sys.executable,'tools/gui_checks/check_p05_regression.py']),
    ]
    results=[];status=0
    try:
        for i,(name,cmd) in enumerate(stages,1):
            print(f'[RUN {i}] {name}',flush=True)
            try:
                result=subprocess.run(cmd,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=1800)
                output=result.stdout;rc=result.returncode
            except subprocess.TimeoutExpired as exc:
                output=(exc.stdout or b'').decode('utf-8','replace') if isinstance(exc.stdout,bytes) else (exc.stdout or '')
                output+='\nTIMEOUT\n';rc=124
            (logs/f'{i:02d}.log').write_text(output,encoding='utf-8')
            print(output,flush=True)
            results.append({'step':name,'returncode':rc,'command':cmd})
            if rc:status=1;break
    except Exception as exc:
        print(str(exc),file=sys.stderr);status=1
    summary={'schemaVersion':1,'patch':'P05','version':'0.9.0rc5','result':'PASS' if status==0 else 'FAIL','readiness':'READY_FOR_RC5_REVIEW' if status==0 else 'BLOCKED','scope':'deterministic regression; no network/root canary; owner acceptance NOT_RUN','steps':results}
    (logs/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=logs.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(logs.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(logs))
    print('P05 deterministic acceptance: '+summary['result'])
    print('HYPERPATCH ACCEPTANCE: '+summary['result'])
    print('readiness: '+summary['readiness']);print('evidence archive: '+str(archive))
    return status
if __name__=='__main__':raise SystemExit(main())
