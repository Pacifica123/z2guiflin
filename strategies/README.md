# Стратегии

`strategies/` хранит каталог высокоуровневых стратегий продукта. Стратегия отвечает на вопрос: **какой тип workflow GUI должен показать владельцу**.

На Stage 7 стратегия не является набором shell-команд и не содержит скрытого исполнения. Это описание намерений, ограничений и future plan boundary. Исполняемые run/apply/session plans появятся только отдельными будущими патчами и должны требовать явного подтверждения владельца.

## v0.4-alpha Stage 5: service-aware export

Generated strategies из Blockcheck теперь получают service label. Если scan был
запущен через `youtube-basic`, `discord-desktop` или `custom`, exporter сохраняет
этот контекст в id/title/metadata стратегии. Это особенно важно для Discord,
потому что sequential run может найти `AVAILABLE` на одном candidate-домене, но
пользователь всё равно должен видеть, что стратегия относится к Discord desktop
non-voice проверке.

## v0.4-alpha Stage 7j: community Discord+YouTube edge-flow bridge

Stage 7j adds `community-discord-youtube-edge-flow` as an explicitly experimental, owner-selected strategy. It is based on the owner-provided community Windows preset that helped on the same network for both YouTube and Discord, but it is not a direct WinDivert port.

Linux bridge decisions:

- WinDivert `--wf-*` capture options are not passed to `nfqws2`; owner-confirmed nftables apply still controls which local traffic reaches NFQUEUE.
- `hostfakesplit_multi` is provided by `core/zapret2/lua/custom_funcs.lua` as a small compatibility shim over built-in `hostfakesplit`.
- The strategy includes a Discord Cloudflare edge `--ipset-ip` profile with `wssize` + `syndata` because Stage 7h/7i observed Discord stuck in `SYN-SENT` before TLS.
- The Windows preset voice/STUN block is intentionally not ported in this strategy; Stage 8 remains the voice/UDP investigation.

Recommended owner experiment:

```bash
PYTHONPATH=gui python -m zap2_gui.app --select-strategy community-discord-youtube-edge-flow
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
```

Then continue through the normal owner-confirmed Default workflow. This strategy is not selected automatically and is not used by tests to mutate firewall/services.


## v0.4-alpha Stage 7k community v2 seed

`community-discord-syndata-edge-flow-v2` is an owner-selectable experiment for the Discord Linux newUpdater SYN-SENT case. It keeps the YouTube fallback from the Stage 7j community bridge but adds explicit phase-zero `send`/`syndata` branches for observed Discord Cloudflare edge IPs. It is not selected automatically.
