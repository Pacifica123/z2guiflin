#!/usr/bin/env python3
"""Run focused GUI/model tests in a disposable checkout and isolated settings."""
from pathlib import Path
import os,shutil,tempfile
from check_p07_regression import _run_group
from p07_process import install_signal_cleanup

def main():
    install_signal_cleanup()
    with tempfile.TemporaryDirectory(prefix='zap2-p07-focused-') as tmp:
        _index,rc,log=_run_group(1,['tests/test_p07_qualification.py'],Path(tmp))
        print(log.read_text(encoding='utf-8'))
        destination=os.environ.get('ZAP2_P07_LOG_DIR')
        if destination:
            Path(destination).mkdir(parents=True,exist_ok=True)
            shutil.copy2(log,Path(destination)/'focused.log')
            if log.with_suffix('.xml').exists():shutil.copy2(log.with_suffix('.xml'),Path(destination)/'focused.xml')
        return rc
if __name__=='__main__':raise SystemExit(main())
