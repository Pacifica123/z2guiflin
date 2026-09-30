#!/usr/bin/env python3
"""Construct a package-manager-owned prefix. Never touch HOME/user state."""
from pathlib import Path
import argparse,hashlib,json,shutil


def install(source: Path,destdir: Path,prefix: str='/usr') -> Path:
    if not prefix.startswith('/') or '..' in Path(prefix).parts:raise ValueError('prefix must be absolute')
    target=destdir/prefix.lstrip('/')
    if target.is_symlink() or any(p.is_symlink() for p in target.parents):raise ValueError('symlink install prefix')
    manifest=json.loads((source/'RELEASE_MANIFEST.json').read_text())
    if manifest.get('schemaVersion')!=1:raise ValueError('unknown manifest')
    records=manifest['files']
    if hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=manifest.get('releaseDigest'):raise ValueError('manifest digest mismatch')
    owned=[]
    def copy(src,dst,mode=0o644):
        if dst.is_symlink() or any(p.is_symlink() for p in dst.parents if p!=target and target in p.parents):raise ValueError('unsafe package destination')
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);dst.chmod(mode);owned.append(str(dst.relative_to(target)))
    share=target/'share/zap2gui'
    for rel,entry in manifest['files'].items():
        path=Path(rel)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] in {'.zap2','.git'} or entry.get('mode') not in {0o644,0o755}:raise ValueError('unsafe package source')
        src=source/path
        if src.is_symlink() or source.resolve() not in src.resolve().parents or hashlib.sha256(src.read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('source hash mismatch: '+rel)
        copy(src,share/path,entry['mode'])
    copy(source/'RELEASE_MANIFEST.json',share/'RELEASE_MANIFEST.json')
    for rel in manifest['files']:
        if rel.startswith('gui/zap2_gui/'):
            copy(source/rel,target/'lib/zap2gui/python'/Path(rel).relative_to('gui'))
    copy(source/'packaging/launch.py',target/'lib/zap2gui/launch.py',0o755)
    copy(source/'tools/privileged/zap2-runtime-executor',target/'lib/zap2gui/zap2-runtime-executor',0o755)
    # Tiny executable launcher, no caller-controlled PYTHONPATH.
    script=target/'bin/zap2-gui';script.parent.mkdir(parents=True,exist_ok=True)
    if script.is_symlink() or any(p.is_symlink() for p in script.parents if p!=target and target in p.parents):raise ValueError('unsafe launcher destination')
    script.write_text('#!/bin/sh\nexec /usr/bin/python3 -I "'+prefix+'/lib/zap2gui/launch.py" "$@"\n');script.chmod(0o755);owned.append(str(script.relative_to(target)))
    copy(source/'packaging/zap2-gui.desktop',target/'share/applications/zap2-gui.desktop')
    copy(source/'LICENSE',target/'share/licenses/zap2gui-linux/LICENSE')
    copy(source/'core/zapret2/docs/LICENSE.txt',target/'share/licenses/zap2gui-linux/zapret2-LICENSE')
    receipt=target/'share/zap2gui/INSTALL_FILES.json'
    if receipt.is_symlink():raise ValueError('unsafe install receipt destination')
    receipt.write_text(json.dumps({'schemaVersion':1,'files':sorted(owned+['share/zap2gui/INSTALL_FILES.json']),'uninstall':'only listed system files; never user workspace'},indent=2)+'\n');receipt.chmod(0o644)
    return target


def uninstall_staged(target: Path) -> list[str]:
    """Test/package staging operation; real users uninstall through pacman."""
    if target.resolve() in {Path('/usr'),Path('/')} or target.is_symlink() or any(p.is_symlink() for p in target.parents):raise ValueError('use pacman for live system uninstall')
    receipt=json.loads((target/'share/zap2gui/INSTALL_FILES.json').read_text())
    paths=receipt['files']
    for rel in paths:
        p=Path(rel)
        if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe uninstall member')
        item=target/p
        if item.is_symlink() or any(parent.is_symlink() for parent in item.parents if target in parent.parents):raise ValueError('unsafe uninstall symlink')
    for rel in paths:(target/rel).unlink(missing_ok=True)
    return paths

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--destdir',type=Path,required=True);p.add_argument('--prefix',default='/usr');a=p.parse_args();print(install(a.source,a.destdir,a.prefix))
