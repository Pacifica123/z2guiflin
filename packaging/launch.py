#!/usr/bin/python3 -I
"""Package-owned launcher; its prefix is derived from this installed file."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
LIB=Path(__file__).resolve().parent
sys.path.insert(0,str(LIB/'python'))
from zap2_gui.distribution import main
if __name__=='__main__':
    try:raise SystemExit(main(LIB.parents[1]/'share/zap2gui'))
    except (ValueError,OSError) as exc:
        print('Zap2 install/lifecycle error: '+str(exc),file=sys.stderr);raise SystemExit(2)
