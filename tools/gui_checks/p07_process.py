"""Bounded POSIX test process groups, including interrupted qualification workers."""
from __future__ import annotations
import os,signal,subprocess,threading
from dataclasses import dataclass
_ACTIVE=set()
_LOCK=threading.RLock()

@dataclass(frozen=True)
class Result:
    returncode: int
    output: str
    timed_out: bool

def _signal_group(pid,sig):
    try:os.killpg(pid,sig)
    except ProcessLookupError:pass

def install_signal_cleanup():
    def interrupted(sig,frame):
        with _LOCK:groups=list(_ACTIVE)
        for pid in groups:_signal_group(pid,signal.SIGTERM)
        raise SystemExit(128+sig)
    for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,interrupted)

def run_bounded(command,*,cwd=None,env=None,timeout=900):
    process=subprocess.Popen(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    with _LOCK:_ACTIVE.add(process.pid)
    def terminate_group(sig):_signal_group(process.pid,sig)
    def terminate_and_collect():
        terminate_group(signal.SIGTERM)
        try:return process.communicate(timeout=5)[0]
        except subprocess.TimeoutExpired:
            terminate_group(signal.SIGKILL);return process.communicate(timeout=5)[0]
    timed_out=False
    try:
        output,_=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True;output=terminate_and_collect()
    except BaseException:
        # Give a nested qualification worker time to terminate its own groups.
        terminate_and_collect();raise
    finally:
        terminate_group(signal.SIGKILL)
        with _LOCK:_ACTIVE.discard(process.pid)
    return Result(124 if timed_out else process.returncode,(output or '')+('\nTIMEOUT — owned process group terminated\n' if timed_out else ''),timed_out)
