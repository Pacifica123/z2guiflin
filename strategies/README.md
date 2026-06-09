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
