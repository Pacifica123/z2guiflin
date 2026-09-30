"""P04d frozen compatibility bindings between legacy CLI selectors and ActionContracts."""
from __future__ import annotations

from dataclasses import dataclass

from .action_bindings_generated import GENERATED_LEGACY_ACTION_SPECS


@dataclass(frozen=True)
class LegacyActionBinding:
    selector: str
    action_id: str
    operand_arity: int = 0
    choices: tuple[str, ...] = ()
    option_strings: tuple[str, ...] = ()


GENERATED_LEGACY_ACTION_BINDINGS: tuple[LegacyActionBinding, ...] = tuple(
    LegacyActionBinding(
        selector=str(spec["selector"]),
        action_id=str(spec["action_id"]),
        operand_arity=int(spec["operand_arity"]),
        choices=tuple(str(value) for value in spec["choices"]),
        option_strings=tuple(str(value) for value in spec["option_strings"]),
    )
    for spec in GENERATED_LEGACY_ACTION_SPECS
)

GENERATED_BINDING_BY_SELECTOR: dict[str, LegacyActionBinding] = {
    binding.selector: binding for binding in GENERATED_LEGACY_ACTION_BINDINGS
}
GENERATED_BINDING_BY_ACTION_ID: dict[str, LegacyActionBinding] = {
    binding.action_id: binding for binding in GENERATED_LEGACY_ACTION_BINDINGS
}
