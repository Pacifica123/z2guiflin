"""Read-only native catalog for bundled legacy strat_collection."""
from __future__ import annotations
from dataclasses import dataclass
import json,re,shlex
from pathlib import Path
from typing import Any
from ..project_paths import discover_layout
COLLECTION_RELATIVE_ROOT=Path("presets/collections/strat_collection")
@dataclass(frozen=True)
class StratCollectionEntry:
    entry_id:str; name:str; description:str; version:str; provider:str; author:str; updated:str; label:str; ports:str; host_lists:str; fragments:bool; sort_order:int; source_path:Path; source_exists:bool; winws_args:tuple[str,...]; referenced_files:tuple[str,...]; missing_referenced_files:tuple[str,...]; desync_modes:tuple[str,...]
    @property
    def compatibility(self): return "legacy zapret1 / reference-only"
    @property
    def search_text(self): return " ".join((self.entry_id,self.name,self.description,self.provider,self.author,self.label,self.ports,self.host_lists," ".join(self.desync_modes))).lower()
    def to_text(self,root:Path):
        try: src=self.source_path.relative_to(root)
        except ValueError: src=self.source_path
        x=[f"strat_collection: {self.entry_id}",f"name: {self.name}",f"description: {self.description or '-'}",f"provider: {self.provider or '-'}; author: {self.author or '-'}",f"version: {self.version or '-'}; updated: {self.updated or '-'}; label: {self.label or '-'}",f"ports: {self.ports or '-'}",f"host lists: {self.host_lists or '-'}",f"compatibility: {self.compatibility}",f"source: {src} ({'ok' if self.source_exists else 'missing'})",f"desync modes: {', '.join(self.desync_modes) or '-'}",f"assets: {len(self.referenced_files)}; missing: {len(self.missing_referenced_files)}"]
        if self.missing_referenced_files:x.append("missing assets: "+", ".join(self.missing_referenced_files))
        x += ["","winws args (анализ; НЕ исполняются):"] + (["  "+a for a in self.winws_args] or ["  -"]); return "\n".join(x)
@dataclass(frozen=True)
class StratCollectionCatalog:
    root:Path; entries:tuple[StratCollectionEntry,...]
    def search(self,q:str):
        words=q.strip().lower().split(); return tuple(e for e in self.entries if all(w in e.search_text for w in words))
def _safe(root:Path,rel:str):
    p=(root/rel).resolve()
    try:p.relative_to(root.resolve())
    except ValueError as exc:raise ValueError(f"path traversal in strat_collection: {rel}") from exc
    return p
def _joined(text:str):
    out=[]; buf=""
    for raw in text.replace("\r\n","\n").split("\n"):
        s=raw.strip()
        if not s:continue
        buf=(buf+" "+s).strip()
        if buf.endswith("^"):buf=buf[:-1].rstrip();continue
        out.append(buf);buf=""
    if buf:out.append(buf)
    return out
def _args(text:str):
    lines=_joined(text); cmd=" ".join(x for x in lines if "winws.exe" in x.lower() or x.startswith("--")); tail=cmd[cmd.find("--"):] if "--" in cmd else ""
    if not tail:return ()
    try: parts=shlex.split(tail.replace("^"," "),posix=False)
    except ValueError:parts=tail.split()
    return tuple(x.strip() for x in parts if x.strip().startswith("--"))
def _refs(args):
    out=set()
    for a in args:
        if "=" not in a:continue
        val=a.split("=",1)[1].strip().strip('"\'')
        for x in re.split(r"[,;]",val):
            x=x.strip().strip('"\'').replace("\\","/")
            if re.search(r"\.(txt|bin|dat)$",x,re.I):out.add(x)
    return tuple(sorted(out))
def load_strat_collection(root:Path|None=None):
    layout=discover_layout(root); cr=(layout.root/COLLECTION_RELATIVE_ROOT).resolve(); cp=cr/"strag.json"
    if not cp.is_file():return StratCollectionCatalog(cr,())
    raw:Any=json.loads(cp.read_text(encoding="utf-8"));
    if not isinstance(raw,dict):raise ValueError("strag.json должен быть object")
    es=[]
    for eid,m in raw.items():
        if not isinstance(m,dict):continue
        rel=str(m.get("file_path","")).strip(); src=_safe(cr,rel) if rel else cr/"__missing__"; text=src.read_text(encoding="utf-8",errors="replace") if src.is_file() else ""; args=_args(text); refs=_refs(args); missing=tuple(x for x in refs if not _safe(cr,x).is_file()); modes=sorted({z for a in args if a.startswith("--dpi-desync=") for z in a.split("=",1)[1].split(",") if z})
        es.append(StratCollectionEntry(str(eid),str(m.get("name",eid)),str(m.get("description","")),str(m.get("version","")),str(m.get("provider","")),str(m.get("author","")),str(m.get("updated","")),str(m.get("label","")),str(m.get("ports","")),str(m.get("host_lists","")),bool(m.get("fragments",False)),int(m.get("sort_order",9999)),src,src.is_file(),args,refs,missing,tuple(modes)))
    es.sort(key=lambda e:(e.sort_order,e.name.lower(),e.entry_id)); return StratCollectionCatalog(cr,tuple(es))
