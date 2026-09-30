#!/usr/bin/env python3
"""Run focused GUI/model tests in a disposable checkout and isolated settings."""
from pathlib import Path
import os,shutil,tempfile
from check_p06_regression import _run_group

def main():
    with tempfile.TemporaryDirectory(prefix='zap2-p06-focused-') as tmp:
        _index,rc,log=_run_group(1,['tests/test_p06_productization.py'],Path(tmp))
        print(log.read_text(encoding='utf-8'))
        destination=os.environ.get('ZAP2_P06_LOG_DIR')
        if destination:
            Path(destination).mkdir(parents=True,exist_ok=True)
            shutil.copy2(log,Path(destination)/'focused.log')
        return rc
if __name__=='__main__':raise SystemExit(main())
