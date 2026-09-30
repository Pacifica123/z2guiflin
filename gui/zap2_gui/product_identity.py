"""Independent identity axes; presence/version is not a connectivity verdict."""
from pathlib import Path
import json
from . import __version__,DEVELOPMENT_LINE
from .project_paths import discover_layout
from .adapters.core_generation import load_upstream_manifest
from .models.execution_plan import EXECUTION_PLAN_SCHEMA_VERSION
from .models.network_evidence import EVIDENCE_GRAPH_SCHEMA_VERSION,CONNECTION_RECEIPT_SCHEMA_VERSION,CAPABILITY_VERDICT_SCHEMA_VERSION


def identity_snapshot(root: Path | None=None) -> dict:
    layout=discover_layout(root);upstream=load_upstream_manifest(layout.root)
    session_path=layout.root/'.zap2/tunnel/runtime/default.session.json'
    try:session=json.loads(session_path.read_text())
    except (OSError,ValueError):session={}
    from .adapters.privileged_executor import privileged_executor_status
    helper=privileged_executor_status(layout.root)
    core=session.get('coreCapability') or {}
    return {'productVersion':__version__,'developmentLine':DEVELOPMENT_LINE,'upstream':{'name':upstream.get('upstreamName'),'version':upstream.get('upstreamVersion'),'commit':upstream.get('upstreamCommit')},'externalCore':{'version':core.get('version','UNKNOWN'),'identityHash':core.get('identityHash','UNKNOWN'),'scope':'saved identity; not current connectivity'},'schemas':{'executionPlan':EXECUTION_PLAN_SCHEMA_VERSION,'evidenceGraph':EVIDENCE_GRAPH_SCHEMA_VERSION,'connectionReceipt':CONNECTION_RECEIPT_SCHEMA_VERSION,'capabilityVerdict':CAPABILITY_VERDICT_SCHEMA_VERSION,'workspaceInstallation':1},'evidence':{'runId':session.get('runId','UNKNOWN'),'connectionReceiptId':session.get('connectionReceiptId','UNKNOWN'),'configHash':session.get('configHash','UNKNOWN')},'helper':{'state':helper.state,'sourceSha256':helper.project_sha256,'installedSha256':helper.installed_sha256},'service':'plan-only; package does not install/enable a unit','support':'Arch-like package path; network results environment-dependent'}
