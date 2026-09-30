#!/usr/bin/env python3
"""Current reference derives from executable authorities, never a third registry."""
from pathlib import Path
import argparse,dataclasses,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gui'))
from zap2_gui import __version__
from zap2_gui.models.action_catalog import ACTION_CONTRACTS
from zap2_gui.app import build_parser
from zap2_gui.models.action_bindings import GENERATED_LEGACY_ACTION_BINDINGS
from zap2_gui.models.domain_semantics import CANONICAL_DOMAIN_NOUNS,CANONICAL_ACTION_VERBS
from zap2_gui.models.discovery import CONCEPT_HELP
from zap2_gui.adapters.discord_tunnel import VESKTOP_MANDATORY_HTTP_TARGETS,VESKTOP_GATEWAY_TARGET,VESKTOP_MAIN_WINDOW_TARGET
from zap2_gui.product_identity import identity_snapshot

def generated():
    cli=[{'options':a.option_strings,'destination':a.dest,'nargs':a.nargs,'required':a.required} for a in build_parser()._actions if a.option_strings]
    schemas={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'schema':json.loads(p.read_text())} for p in sorted((ROOT/'runtime/schemas').glob('*.json'))}
    identity=identity_snapshot(ROOT)
    data={'schemaVersion':1,'productVersion':__version__,'contracts':[dataclasses.asdict(c) for c in ACTION_CONTRACTS],'cli':cli,'legacyOperandBindings':[dataclasses.asdict(b) for b in GENERATED_LEGACY_ACTION_BINDINGS],'concepts':{'nouns':CANONICAL_DOMAIN_NOUNS,'verbs':CANONICAL_ACTION_VERBS,'help':CONCEPT_HELP},'schemas':schemas,'capabilities':{'mandatoryHttpTargets':list(VESKTOP_MANDATORY_HTTP_TARGETS),'gatewayWebsocket':VESKTOP_GATEWAY_TARGET,'electronNavigation':VESKTOP_MAIN_WINDOW_TARGET,'verdictStates':['PASS','FAIL','UNKNOWN','NOT_RUN'],'boundary':'HTTP alone does not establish gateway, navigation or Voice capability'},'provenance':{'upstream':identity['upstream'],'schemas':identity['schemas'],'manifestSha256':hashlib.sha256((ROOT/'core/zapret2/UPSTREAM_IMPORT.json').read_bytes()).hexdigest()},'packageCli':{'--package-preflight':'verify installed package; no user state','--about':'independent identity axes','--support-bundle FILE':'redacted evidence only','--find QUERY':'read-only ActionContract projection'}}
    raw=json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    md='# Генерируемый справочник текущих контрактов\n\nЭтот документ автоматически получен из исполняемых контрактов, парсера командной строки, схем состояния, требований возможностей и закреплённого происхождения ядра. Ручное изменение справочника запрещено: исправляется соответствующий источник и повторяется генерация. Проверка свежести входит в единый профиль приёмки. Полные структуры находятся в [reference.json](reference.json). Исторические документы описывают только свои этапы и не подменяют текущий контракт.\n\nВерсия продукта: `'+__version__+'`. Команды оболочки установленного пакета `--about`, `--support-bundle FILE`, `--find QUERY`, `--package-preflight` перечислены отдельно от канонического диспетчера.\n\n| Действие | Эффект | Привилегия | CLI aliases |\n|---|---|---|---|\n'
    for c in ACTION_CONTRACTS:md+='| `'+c.action_id+'` | '+c.effect+' | '+c.privilege+' | '+', '.join('`'+x+'`' for x in c.legacy_aliases)+' |\n'
    md+='\nВозможности: обязательный HTTP для '+', '.join(VESKTOP_MANDATORY_HTTP_TARGETS)+'; WebSocket '+VESKTOP_GATEWAY_TARGET+'; Electron navigation '+VESKTOP_MAIN_WINDOW_TARGET+'. Отсутствующее доказательство остаётся UNKNOWN/NOT_RUN. Идентификаторы схем и SHA256 происхождения опубликованы в JSON; продукт, upstream, внешний core и evidence являются независимыми осями.\n'
    return {'docs/generated/reference.json':raw,'docs/generated/reference.md':md}

def main():
    a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');args=a.parse_args();bad=[]
    for rel,text in generated().items():
        path=ROOT/rel
        if args.check:
            if not path.exists() or path.read_text()!=text:bad.append(rel)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    if bad:print('P06 generated reference: STALE '+', '.join(bad));return 1
    print('P06 generated reference: PASS');return 0
if __name__=='__main__':raise SystemExit(main())
