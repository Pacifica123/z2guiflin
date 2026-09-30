"""Deterministic, non-executing views over the executable catalog and ontology."""
from __future__ import annotations
from dataclasses import dataclass
import re
import unicodedata
from .action_catalog import ACTION_CONTRACTS, action_contract
from .domain_semantics import CANONICAL_DOMAIN_NOUNS

# Contextual ontology help; these entries declare no actions or privilege policy.
CONCEPT_HELP = {
    'runtimeContext': ('Контекст запуска', 'контекст workspace profile', 'Выбранные настройки запуска и его локальное состояние.'),
    'preset': ('Пресет', 'пресет стратегия recipe', 'Рецепт обработки пакетов. Один удачный тест не гарантирует работу на другом маршруте.'),
    'trafficProfile': ('Профиль трафика', 'фильтр traffic filter', 'Упорядоченный блок правил внутри пресета.'),
    'desyncAction': ('Действие desync', 'обход dpi пакет segmentation fake', 'Меняет наблюдение DPI, сохраняя смысл соединения для конечного узла.'),
    'tunnelConnection': ('VLESS / SOCKS / Discord', 'туннель vless socks tls discord vesktop дискорд почему не работает', 'Локальный SOCKS, удалённый TLS и приложение проверяются отдельно. localhost сам по себе не гарантирует приватность.'),
    'backend/core': ('Ядро', 'ядро core nfqws2 xray v2ray binary сборка', 'Исполняемый компонент; версия и происхождение важны для совместимости.'),
    'runtimeResource': ('Firewall / NFQUEUE', 'nfqueue nft firewall файрвол очередь откат undo firewall', 'Принадлежащие этому запуску правила и процессы. Чужие или неизвестные ресурсы нельзя удалять автоматически.'),
    'operation/action': ('Действие', 'действие action команда command', 'Именованная операция с контрактом эффекта и прав.'),
    'Plan': ('План и подтверждение', 'план безопасно запустить safe start confirm confirmation', 'Сначала подготовьте план, проверьте эффект и подтвердите его ID; затем исполните через штатный workflow.'),
    'probe': ('Проверка', 'проверка диагностика probe diagnostic', 'Наблюдение одного слоя на свежем соединении; результат ограничен условиями проверки.'),
    'Evidence': ('Данные проверки', 'evidence доказательство лог журнал', 'Наблюдения имеют run ID, время, входные хеши и границы применимости.'),
    'Verdict': ('Результат', 'verdict fail pass unknown неизвестно', 'PASS относится к проверенному утверждению. Недостающие и устаревшие данные дают UNKNOWN.'),
    'Capability': ('Возможность приложения', 'capability health состояние здоровье доступность', 'Требует всех обязательных проверок. Работа процесса не доказывает работу приложения.'),
}

DOMAIN_WORDS = {
    'runtime': 'запуск процесс очередь nfqueue nft firewall файрвол',
    'default': 'обычный запуск',
    'start': 'безопасно запустить safe start', 'stop': 'остановить stop',
    'discord': 'туннель дискорд discord vesktop vless socks tls',
    'vless': 'туннель дискорд discord vesktop vless socks tls',
    'preset': 'пресет стратегия', 'strategy': 'пресет стратегия',
    'core': 'ядро сборка nfqws2 binary', 'blockcheck': 'диагностика проверка домен',
}

@dataclass(frozen=True)
class DiscoveryEntry:
    semantic_id: str
    kind: str
    label: str
    text: str
    help_text: str
    page: str
    focus_target: str


def normalize(value: str) -> str:
    return ' '.join(re.findall(r'[\w]+', unicodedata.normalize('NFKC', value).casefold().replace('ё', 'е')))


def action_page(action_id: str) -> str:
    words = normalize(action_id).split()
    if any(w in words for w in ('discord', 'vless', 'tunnel', 'vesktop', 'socks')): return 'tunnel'
    if any(w in words for w in ('preset', 'strategy', 'strategies')): return 'strategies'
    if any(w in words for w in ('blockcheck', 'har', 'dns', 'probe', 'diagnostics')): return 'diagnostics'
    if 'core' in words or 'build' in words: return 'core'
    if 'log' in words or 'logs' in words: return 'logs'
    return 'overview'


def contextual_help(action_id: str) -> str:
    c = action_contract(action_id)
    when = 'Используйте для просмотра или проверки состояния.' if c.effect in {'show','list','inspect','validate'} else 'Используйте, когда требуется указанный эффект; сначала проверьте входные параметры.'
    boundary = 'Откройте раздел и используйте штатную подготовку и подтверждение для изменений; поиск их не исполняет.' if not direct_invoke_allowed(action_id) else 'Можно явно выполнить просмотр или проверку без изменения системы.'
    verbs={'show':'просмотр','list':'список','inspect':'просмотр','validate':'проверка','prepare':'подготовка','plan':'планирование','start':'запуск','stop':'остановка','apply':'применение','revert':'откат','confirm':'подтверждение','probe':'диагностика','reconcile':'сверка','launch':'запуск приложения','import':'импорт','export':'экспорт'}
    rights={'none':'обычные','owner':'владелец','bounded-root':'ограниченное повышение прав'}
    return '\n'.join((f'Что: {c.short_help}', f'Когда: {when}', f'Эффект: {verbs[c.effect]}; права: {rights[c.privilege]}.', 'Условия: ' + ('; '.join(c.preconditions) or 'Параметры выбранного контекста и операции должны быть корректны.'), boundary, f'Технический ID: {c.action_id}', 'CLI: --action ' + c.action_id + ' ' + ' '.join(c.legacy_aliases)))


def direct_invoke_allowed(action_id: str) -> bool:
    c = action_contract(action_id)
    return c.safe_invoke and c.privilege == 'none' and c.effect in {'show', 'list', 'inspect', 'validate'} and not c.preconditions


def build_index() -> tuple[DiscoveryEntry, ...]:
    entries = []
    for c in ACTION_CONTRACTS:
        if c.internal: continue
        words = normalize(c.action_id).split()
        aliases = ' '.join(DOMAIN_WORDS.get(word, '') for word in words)
        text = ' '.join((c.action_id, c.label, c.short_help, *c.keywords, *c.aliases, *c.legacy_aliases, *c.concept_links, aliases))
        entries.append(DiscoveryEntry(c.action_id, 'action', c.label, text, contextual_help(c.action_id), action_page(c.action_id), 'discoveryDetails'))
    for noun in CANONICAL_DOMAIN_NOUNS:
        label, aliases, help_text = CONCEPT_HELP[noun]
        entries.append(DiscoveryEntry(noun, 'concept', label, f'{noun} {label} {aliases}', help_text, 'tunnel' if noun == 'tunnelConnection' else 'overview', 'discoveryDetails'))
    # Settings metadata lives beside the controls and is consumed by both views.
    from ..widgets.settings import setting_help_rows
    for setting_id, label, help_text in setting_help_rows():
        entries.append(DiscoveryEntry(setting_id, 'setting', label, f'{setting_id} {label} {help_text} settings настройки тема theme', help_text, 'settings', setting_id))
    return tuple(entries)


def _one_edit(a: str, b: str) -> bool:
    if len(a) < 4 or len(b) < 4 or abs(len(a)-len(b)) > 1: return False
    if len(a) == len(b):
        differences = [i for i,(x,y) in enumerate(zip(a,b)) if x != y]
        return len(differences) <= 1 or (len(differences) == 2 and differences[1] == differences[0]+1 and a[differences[0]] == b[differences[1]] and a[differences[1]] == b[differences[0]])
    if len(a) > len(b): a,b = b,a
    i=j=errors=0
    while i < len(a) and j < len(b):
        if a[i] == b[j]: i+=1; j+=1
        else: errors+=1; j+=1
        if errors > 1: return False
    return True


def search(query: str, *, limit: int = 30) -> tuple[DiscoveryEntry, ...]:
    tokens = normalize(query).split()[:12]
    if not tokens: return ()
    ranked = []
    for entry in build_index():
        words = normalize(entry.text).split(); score = 0
        for token in tokens:
            if token in words: score += 100
            elif any(w.startswith(token) for w in words): score += 60
            elif any(_one_edit(token,w) for w in words): score += 20
            else: break
        else:
            score += 60 * sum(token in normalize(entry.semantic_id).split() for token in tokens)
            if normalize(query) == normalize(entry.semantic_id): score += 300
            if normalize(query) in normalize(entry.label): score += 40
            ranked.append((-score, entry.semantic_id, entry))
    return tuple(row[2] for row in sorted(ranked, key=lambda r:(r[0],r[1]))[:max(0, min(limit,100))])


def main() -> int:
    import argparse, json
    parser = argparse.ArgumentParser(description='Поиск действий, понятий и настроек; ничего не исполняет')
    parser.add_argument('query', nargs='?', default='')
    parser.add_argument('--help-id')
    args = parser.parse_args()
    if args.help_id:
        match = next((e for e in build_index() if e.semantic_id == args.help_id), None)
        if match is None: parser.error('Неизвестный semantic ID')
        print(match.help_text)
    else:
        print(json.dumps([dict(id=e.semantic_id,kind=e.kind,label=e.label,page=e.page,help=e.help_text) for e in search(args.query)], ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
