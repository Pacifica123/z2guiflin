# Автоматизированный runner строки матрицы Discord

Статус: справка по Stage 7o2d.

Auto mode сокращает ручную работу с build/start plan ID, но не отменяет owner confirmation и не превращает сетевой эксперимент в автономный тест.

## Команда

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --discord-observation-matrix-run-row multisplit \
  --matrix-row-auto
```

Для strategy row режим может:

- проверить/подготовить сборку;
- выбрать стратегию;
- подготовить и подтвердить plans;
- при наличии нужных прав запустить workflow;
- выполнить guided probe;
- сохранить evidence.

Если требуется `sudo`, runner останавливается на безопасной границе и печатает следующую owner-команду. Он не должен скрыто повышать права.

Baseline row не запускает Zapret и сначала проверяет, что managed runtime действительно остановлен.
