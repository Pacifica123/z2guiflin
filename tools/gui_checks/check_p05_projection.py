#!/usr/bin/env python3
"""Check current P05 views and preserved semantic authority against frozen PRE."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'gui'))
from zap2_gui import __version__, PRODUCT_LABEL
from zap2_gui.models.discovery import build_index, contextual_help, direct_invoke_allowed, CONCEPT_HELP
from zap2_gui.models.action_catalog import ACTION_CONTRACTS, validation_errors
from zap2_gui.models.domain_semantics import CANONICAL_DOMAIN_NOUNS
from zap2_gui.models.navigation import default_navigation_sections
from zap2_gui.adapters.action_dispatcher import dispatcher_validation_errors

def main():
    pre=json.loads((ROOT/'runtime/p05/pre-forensics.json').read_text())
    errors=[]
    for name,expected in pre['inputSha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:errors.append('preserved authority drift: '+name)
    if __version__!='0.9.0rc5' or PRODUCT_LABEL!='v0.9 RC5':errors.append('version mismatch')
    if 'version = "0.9.0rc5"' not in (ROOT/'pyproject.toml').read_text():errors.append('pyproject version mismatch')
    errors.extend(validation_errors());errors.extend(dispatcher_validation_errors())
    index=build_index();by_id={e.semantic_id:e for e in index}
    if len(by_id)!=len(index):errors.append('duplicate semantic ID')
    pages={s.key for s in default_navigation_sections()}
    if set(CONCEPT_HELP)!=set(CANONICAL_DOMAIN_NOUNS):errors.append('concept help drift from ontology')
    for c in ACTION_CONTRACTS:
        if not c.internal and c.action_id not in by_id:errors.append('unsearchable action: '+c.action_id)
        for part in ('Что:','Когда:','Эффект:','Условия:'):
            if part not in contextual_help(c.action_id):errors.append('missing help: '+c.action_id)
        if direct_invoke_allowed(c.action_id) and (not c.safe_invoke or c.privilege!='none' or c.effect not in {'show','list','inspect','validate'}):errors.append('unsafe invoke: '+c.action_id)
    for e in index:
        if e.page not in pages or not e.focus_target:errors.append('unresolved target: '+e.semantic_id)
    if errors:
        print('\n'.join(errors),file=sys.stderr);return 1
    print(f'P05 projection: PASS ({len(ACTION_CONTRACTS)} actions, {len(index)} total entries)')
    print('last accepted release: 0.8.0; current candidate: 0.9.0rc5; owner acceptance: NOT_RUN')
    return 0
if __name__=='__main__':raise SystemExit(main())
