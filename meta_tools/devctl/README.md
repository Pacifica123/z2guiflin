# devctl snapshot

Это локальный снимок инструмента `devctl`, которым применяются devctl-compatible
zip-патчи проекта.

Файлы внутри этой директории не участвуют в runtime Zap2 GUI Linux и не должны
импортироваться приложением. Они сохранены здесь как meta-tooling reference,
чтобы формат патчей, manifest и поведение `devctl plan/start` были доступны в
самом репозитории проекта.

Основные файлы:

- `devctl.py` — исполняемый исходник инструмента;
- `install.sh` — вспомогательная установка wrapper-а;
- `docs/patch-manifest.example.json` — пример manifest;
- `docs/devctl-universal-v0.3-README.md` — описание workflow.
