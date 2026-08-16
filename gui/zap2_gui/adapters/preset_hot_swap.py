"""Transactional one-click preset replacement for Default runtime."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .gui_privilege import execute_gui_privileged_workflow
from .presets import load_preset_catalog, select_preset
from .runtime_default import default_workflow_status, prepare_default_workflow_plan
from .runtime_state import confirm_runtime_plan

@dataclass(frozen=True)
class PresetHotSwapResult:
    requested_preset_id:str; previous_preset_id:str; selected_preset_id:str; runtime_was_running:bool; state:str; message:str; stop_output:str=""; start_output:str=""; rollback_output:str=""
    @property
    def success(self): return self.state in {"selected","switched"}
    def to_text(self):
        x=["Preset hot-swap",f"state: {self.state}",f"previous: {self.previous_preset_id}",f"requested: {self.requested_preset_id}",f"selected: {self.selected_preset_id}",f"runtime was running: {'yes' if self.runtime_was_running else 'no'}",f"message: {self.message}"]
        for name,value in (("stop",self.stop_output),("start",self.start_output),("rollback",self.rollback_output)):
            if value:x += ["",name+":",value.rstrip()]
        return "\n".join(x)

def _run(root, action, profile_id):
    plan=prepare_default_workflow_plan(root=root,action=action,profile_id=profile_id); confirm_runtime_plan(root=root,plan_id=plan.plan_id); result=execute_gui_privileged_workflow(root=root,action=action,profile_id=profile_id,confirm_plan_id=plan.plan_id); return result.success,result.to_text()

def hot_swap_preset(preset_id:str,root:Path|None=None,profile_id:str="default",reason:str="gui-one-click-preset-hot-swap") -> PresetHotSwapResult:
    catalog=load_preset_catalog(root)
    if preset_id not in catalog.by_id(): raise ValueError(f"Неизвестный пресет: {preset_id}")
    previous=catalog.selected_preset_id; status=default_workflow_status(root=root,profile_id=profile_id); running=status.session_status.state=="running"
    if preset_id==previous:return PresetHotSwapResult(preset_id,previous,previous,running,"selected","Пресет уже выбран; runtime не менялся.")
    if not running:
        select_preset(preset_id,root=root,workspace_id=profile_id,reason=reason); return PresetHotSwapResult(preset_id,previous,preset_id,False,"selected","Selection изменён; Default был выключен.")
    stop_ok,stop_text=_run(root,"stop",profile_id); after=default_workflow_status(root=root,profile_id=profile_id)
    if not stop_ok or after.session_status.state=="running": return PresetHotSwapResult(preset_id,previous,previous,True,"stop-failed","Старый runtime не остановлен; selection не изменён.",stop_output=stop_text)
    select_preset(preset_id,root=root,workspace_id=profile_id,reason=reason); start_ok,start_text=_run(root,"start",profile_id); after=default_workflow_status(root=root,profile_id=profile_id)
    if start_ok and after.session_status.state=="running": return PresetHotSwapResult(preset_id,previous,preset_id,True,"switched","Default перезапущен с новым пресетом.",stop_output=stop_text,start_output=start_text)
    select_preset(previous,root=root,workspace_id=profile_id,reason=reason+"-rollback"); rb=[]; rb_ok=False
    try:
        rb_ok,txt=_run(root,"start",profile_id); rb.append(txt); rb_ok=rb_ok and default_workflow_status(root=root,profile_id=profile_id).session_status.state=="running"
    except Exception as exc: rb.append(f"rollback error: {exc}")
    state="start-failed-rolled-back" if rb_ok else "start-failed-rollback-failed"; msg="Новый пресет не запустился; предыдущий runtime восстановлен." if rb_ok else "Новый пресет не запустился; selection восстановлен, restart старого тоже не удался."
    return PresetHotSwapResult(preset_id,previous,previous,True,state,msg,stop_text,start_text,"\n".join(rb))
