"""Read existing current-session evidence; never choose the newest historical file."""
from pathlib import Path
import json
from .runtime_kernel import runtime_kernel_status
from .discord_tunnel import tunnel_store_paths, _session_path, _load_bound_evidence_graph
from ..models.health_projection import project_health

def load_health(root: Path | None = None):
    try: runtime = runtime_kernel_status(root)
    except (OSError,ValueError,TypeError): runtime = None
    graph = None; run_id = ''
    try:
        paths = tunnel_store_paths(root)
        session = json.loads(_session_path(paths,'default').read_text(encoding='utf-8'))
        # Stopped/dead sessions cannot certify current connectivity.
        from .discord_tunnel import _load_running_tunnel_session
        session = _load_running_tunnel_session(paths,'default')
        if session.get('state') != 'running':
            raise ValueError('stored session is not running')
        from .discord_tunnel import _read_cmdline
        core = str(session.get('coreBinary',''))
        cmdline = _read_cmdline(int(session.get('pid',0)))
        if not core or not cmdline or (core not in cmdline and Path(core).name not in cmdline):
            raise ValueError('current process is not the recorded core')
        run_id = str(session.get('runId',''))
        graph = _load_bound_evidence_graph(paths,'default',session)
    except (OSError,ValueError,TypeError,KeyError): pass
    return project_health(runtime,graph,current_run_id=run_id)
