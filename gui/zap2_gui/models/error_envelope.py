"""Evidence-bearing guidance, not an independent error/privilege authority."""
from dataclasses import dataclass
from .action_catalog import action_contract

@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    cause: str
    evidence: tuple[str, ...]
    next_action: str

    def text(self) -> str:
        return f'{self.code}: {self.cause}\nДанные: ' + ('; '.join(self.evidence) or 'Нет данных: причина требует проверки') + '\nДалее: ' + action_contract(self.next_action).label


def error_envelope(code: str, cause: str, evidence: tuple[str,...] = ()) -> ErrorEnvelope:
    key = code.lower()
    if 'nft' in key or 'pid' in key or 'stale' in key or 'migration' in key: action_id = 'runtime.owner-rules.reconcile'
    elif 'tunnel' in key and 'core' in key: action_id = 'discord.tunnel.core.preflight'
    elif 'core' in key or 'binary' in key: action_id = 'default.build.dependencies.inspect'
    elif any(s in key for s in ('tls','socks','transport','tunnel','xhttp')):
        action_id = 'discord.tunnel.evidence'
    else: action_id = 'default.workflow.status'
    return ErrorEnvelope(code,cause,evidence,action_id)
