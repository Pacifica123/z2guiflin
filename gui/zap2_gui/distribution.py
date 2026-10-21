"""Installed lifecycle: immutable package files and a separately receipted user workspace.

The compatibility workspace is a user-owned copy, never a package install root.
This keeps P02/P04 path and plan semantics intact while runtime/tools write only
under XDG_DATA_HOME. The GUI's Python code and privileged helper remain package-owned.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json,os,shutil,tempfile,fcntl,sys,re

WORKSPACE_SCHEMA_VERSION=1
INSTALL_ROOT_ENV='ZAP2_INSTALLED_ROOT'
USER_SEEDS={'profiles','presets','strategies','themes'}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def user_workspace(environ=None) -> Path:
    env=os.environ if environ is None else environ
    data=Path(env.get('XDG_DATA_HOME') or Path.home()/'.local/share').expanduser()
    if not data.is_absolute(): raise ValueError('XDG_DATA_HOME must be absolute')
    return data/'zap2gui'/'workspace'


def manifest_at(package_root: Path) -> dict:
    manifest=json.loads((package_root/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))
    if manifest.get('schemaVersion')!=1:raise ValueError('unknown release manifest schema')
    records=manifest['files']
    expected=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if manifest.get('releaseDigest')!=expected:raise ValueError('release manifest digest mismatch')
    for rel,entry in records.items():
        path=Path(rel)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] in {'.zap2','.git'} or entry.get('mode') not in {0o644,0o755}:raise ValueError('unsafe release member')
        source=package_root/path
        if source.is_symlink() or package_root.resolve() not in source.resolve().parents or sha(source)!=entry['sha256']:raise ValueError('package resource drift: '+rel)
    return manifest


RUNTIME_RECORD_DIRS=('.zap2/runtime/sessions','.zap2/tunnel/runtime')
TERMINAL_STATES={'stopped','reverted','not-started','absent','exited-after-launch','failed-rolled-back'}
LIFECYCLE_HINT=('проверьте: zap2-gui --lifecycle-status; если runtime на самом деле остановлен '
                '(sudo nft list tables | grep zap2 пусто, процессов nfqws2/xray нет) — zap2-gui --lifecycle-confirm-stopped')


def _boot_time() -> float | None:
    """Момент загрузки ядра: процессы и nft-правила runtime не переживают перезагрузку."""
    try:
        for line in Path('/proc/stat').read_text().splitlines():
            if line.startswith('btime '):return float(line.split()[1])
    except (OSError,ValueError,IndexError):
        return None
    return None


def _pid_alive(pid: int, expected_names: set[str]) -> bool:
    if pid<=0:return False
    try:os.kill(pid,0)
    except ProcessLookupError:return False
    except PermissionError:pass  # чужой (root) процесс жив
    except OSError:return False
    if expected_names:
        try:cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        except OSError:return True
        # PID переиспользован другим процессом: наш runtime уже не существует.
        if cmdline and not any(name in cmdline for name in expected_names):return False
    return True


def _record_pids(data: dict) -> tuple[list[int],set[str]]:
    pids=[]
    for holder in (data,data.get('sessionResult') if isinstance(data.get('sessionResult'),dict) else {}):
        try:
            pid=int(holder.get('pid') or 0)
        except (TypeError,ValueError):
            pid=0
        if pid>0:pids.append(pid)
    names={Path(str(data[key])).name for key in ('binaryPath','runtimeExecutablePath','corePath','coreBinary') if data.get(key)}
    return pids,{name for name in names if name}


def runtime_record_activity(path: Path, boot_time: float | None=None) -> str | None:
    """Почему запись держит обновление; None — запись не мешает.

    Fail-closed: непонятная запись мешает. Но то, что проверяется без root, проверяется:
    запись старше текущей загрузки описывает уже несуществующий runtime, а запись с PID —
    живой процесс или нет.
    """
    if path.name.endswith('.session-socks-auth.json'):return None  # секрет туннеля, не состояние
    try:data=json.loads(path.read_text())
    except (ValueError,OSError):return 'unreadable record'
    if not isinstance(data,dict):return 'unreadable record'
    state=data.get('state') or data.get('workflowState')
    if state in TERMINAL_STATES:return None
    if boot_time is not None:
        try:
            if path.stat().st_mtime<boot_time:return None
        except OSError:
            return 'unreadable record'
    pids,names=_record_pids(data)
    if pids:
        alive=[pid for pid in pids if _pid_alive(pid,names)]
        return f'state={state}, live pid {alive[0]}' if alive else None
    return f'state={state}'


def active_runtime_records(workspace: Path) -> dict[str,str]:
    boot=_boot_time();active={}
    for rel in RUNTIME_RECORD_DIRS:
        directory=workspace/rel
        if not directory.exists():continue
        for path in sorted(directory.glob('*.json')):
            reason=runtime_record_activity(path,boot)
            if reason:active[f'{rel}/{path.name}']=reason
    return active


def _active_records(workspace: Path) -> list[str]:
    return [f'{name} ({reason})' for name,reason in active_runtime_records(workspace).items()]


def confirm_runtime_stopped(workspace: Path, archive_root: Path | None=None) -> list[str]:
    """Явное подтверждение пользователя: перенести мешающие записи из workspace, ничего не удаляя."""
    active=active_runtime_records(workspace)
    if any('live pid' in reason for reason in active.values()):
        raise ValueError('owned runtime process is still alive; stop it first: '+', '.join(f'{k} ({v})' for k,v in active.items()))
    if not active:return []
    from datetime import datetime,timezone
    target=(archive_root or workspace.parent/'lifecycle-archive')/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    moved=[]
    for rel in active:
        destination=target/rel;destination.parent.mkdir(parents=True,exist_ok=True)
        os.replace(workspace/rel,destination);moved.append(str(destination))
    return moved


def ensure_workspace(package_root: Path, workspace: Path) -> dict:
    package_root=package_root.resolve();workspace=workspace.absolute()
    # Reject aliases into the immutable installation, and symlink state roots.
    if workspace.is_symlink() or package_root==workspace or package_root in workspace.resolve().parents:
        raise ValueError('user workspace must be separate from package resources')
    if any(parent.is_symlink() for parent in workspace.parents):raise ValueError('symlink workspace ancestor')
    manifest=manifest_at(package_root)
    workspace.parent.mkdir(parents=True,exist_ok=True)
    if (workspace.parent/'workspace.lock').is_symlink() or (workspace.parent/'backups').is_symlink():raise ValueError('symlink lifecycle control path')
    with (workspace.parent/'workspace.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not workspace.exists() and (workspace.parent/'backups').exists():
            raise ValueError('workspace absent with retained backups; explicit recovery required')
        receipt_path=workspace/'.zap2/installation/receipt.json'
        if workspace.exists() and any(p.is_symlink() for p in workspace.rglob('*')):raise ValueError('workspace contains symlinks; data preserved')
        old=json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        if old and old.get('schemaVersion')!=WORKSPACE_SCHEMA_VERSION:
            raise ValueError('unknown newer workspace receipt; no migration performed')
        if workspace.exists() and old is None:
            raise ValueError('existing unreceipted workspace; choose a new data directory or explicit migration')
        # Managed copies can be replaced only if still equal to their recorded
        # package baseline. User seeds and .zap2 state are never overwritten.
        previous=old.get('files',{}) if old else {}
        for rel in previous:
            if Path(rel).is_absolute() or '..' in Path(rel).parts:
                raise ValueError('unsafe historical receipt member')
        if old and any(p.is_symlink() for p in workspace.rglob('*')):
            raise ValueError('workspace contains symlinks; upgrade preserved data and stopped')
        if old and old.get('releaseDigest')==manifest['releaseDigest']:
            return old
        if old and _active_records(workspace):
            raise ValueError('stop/reconcile owned runtime before workspace upgrade: '+'; '.join(_active_records(workspace))+'. '+LIFECYCLE_HINT)
        if old:
            def version_key(value):
                match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?',str(value))
                if not match:raise ValueError('unknown workspace version; explicit migration required')
                major,minor,patch,kind,number=match.groups()
                return (int(major),int(minor),int(patch),{'a':0,'b':1,'rc':2,None:3}[kind],int(number or 0))
            if version_key(manifest['version'])<version_key(old.get('version')):
                raise ValueError('workspace downgrade refused; retain data and restore an explicit backup')
        conflicts=[]
        for rel,entry in manifest['files'].items():
            destination=workspace/rel
            if Path(rel).parts[0] in USER_SEEDS:continue
            if destination.exists() and (rel not in previous or destination.is_symlink() or sha(destination)!=previous[rel]['sha256']):
                conflicts.append(rel)
        for rel in set(previous)-set(manifest['files']):
            destination=workspace/rel
            if Path(rel).parts[0] not in USER_SEEDS and destination.exists() and (destination.is_symlink() or sha(destination)!=previous[rel]['sha256']):conflicts.append(rel)
        if conflicts:raise ValueError('managed-copy conflicts; data preserved: '+', '.join(sorted(conflicts)))
        stage=Path(tempfile.mkdtemp(prefix='.workspace-stage-',dir=workspace.parent))
        backup=None
        try:
            if old:shutil.copytree(workspace,stage,dirs_exist_ok=True,symlinks=True)
            for rel in set(previous)-set(manifest['files']):
                if Path(rel).parts[0] not in USER_SEEDS and (stage/rel).exists():(stage/rel).unlink()
            for rel,entry in manifest['files'].items():
                destination=stage/rel
                if Path(rel).parts[0] in USER_SEEDS and destination.exists():continue
                # A user-controlled parent symlink must never redirect copying
                # outside the staged workspace.
                if any(parent.is_symlink() for parent in destination.parents if parent!=stage and stage in parent.parents):
                    raise ValueError('symlink parent in workspace: '+rel)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(package_root/rel,destination)
                destination.chmod(entry['mode'])
            receipt={'schemaVersion':WORKSPACE_SCHEMA_VERSION,'version':manifest['version'],'releaseDigest':manifest['releaseDigest'],'previousReleaseDigest':old.get('releaseDigest') if old else None,'files':manifest['files'],'ownership':{'packageRoot':'package-owned, immutable','workspace':'user-owned compatibility copies','seeds':'user-owned, preserve on upgrade','runtime':'.zap2, user-owned, preserve on uninstall'}}
            path=stage/'.zap2/installation/receipt.json';path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
            if old:
                backups=workspace.parent/'backups';backups.mkdir(exist_ok=True)
                backup=backups/('workspace-'+old['releaseDigest'][:16])
                if backup.exists():raise ValueError('backup already exists; review before retrying upgrade')
                os.replace(workspace,backup)
            try:os.replace(stage,workspace)
            except Exception:
                if backup is not None:os.replace(backup,workspace)
                raise
            return receipt
        finally:
            if stage.exists():shutil.rmtree(stage)


def prepare_installed(package_root: Path, workspace: Path | None=None) -> Path:
    workspace=user_workspace() if workspace is None else workspace
    ensure_workspace(package_root,workspace)
    os.environ[INSTALL_ROOT_ENV]=str(package_root.resolve())
    os.environ['ZAP2_RESOURCE_ROOT']=str(workspace.resolve())
    # This file is package-owned. Every actual operation still verifies its
    # root ownership, mode and content hash through the P02 status gate.
    prefix=package_root.parents[1]
    os.environ['ZAP2_PRIVILEGED_EXECUTOR']=str(prefix/'lib/zap2gui/zap2-runtime-executor')
    return workspace


def python_module_command(module: str, arguments: list[str]) -> list[str]:
    # No manual PYTHONPATH and no import from user workspace in subprocesses.
    package_path=Path(__file__).resolve().parent.parent
    code='import sys;sys.dont_write_bytecode=True;sys.path.insert(0,'+repr(str(package_path))+');import runpy;sys.argv=['+repr(module)+']+'+repr(arguments)+';runpy.run_module('+repr(module)+',run_name="__main__")'
    return [sys.executable,'-I','-c',code]


def main(package_root: Path | None=None) -> int:
    arguments=sys.argv[1:]
    if package_root is not None:
        if arguments==['--package-preflight']:
            manifest=manifest_at(package_root)
            print(json.dumps({'version':manifest['version'],'releaseDigest':manifest['releaseDigest'],'resources':'verified','service':'plan-only','runtimeMutation':False},indent=2));return 0
        if arguments==['--lifecycle-status']:
            workspace=user_workspace()
            print(json.dumps({'workspace':str(workspace),'blockingRecords':active_runtime_records(workspace),'hint':LIFECYCLE_HINT},ensure_ascii=False,indent=2));return 0
        if arguments==['--lifecycle-confirm-stopped']:
            moved=confirm_runtime_stopped(user_workspace())
            print('\n'.join(['перенесено (не удалено):',*moved]) if moved else 'мешающих записей нет');return 0
        prepare_installed(package_root)
    if arguments==['--about']:
        from .product_identity import identity_snapshot
        print(json.dumps(identity_snapshot(),ensure_ascii=False,indent=2));return 0
    if arguments and arguments[0]=='--support-bundle':
        if len(arguments)!=2:raise ValueError('--support-bundle requires an output file')
        from .support_bundle import write_support_bundle
        print(write_support_bundle(Path(arguments[1])));return 0
    if arguments and arguments[0]=='--find':
        from .models.discovery import search
        print(json.dumps([{'id':e.semantic_id,'label':e.label,'help':e.help_text} for e in search(' '.join(arguments[1:]))],ensure_ascii=False,indent=2));return 0
    from .app import main as app_main
    return app_main(arguments or ['--gui'])
