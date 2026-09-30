# Решение по GUI-фреймворку

## Решение

Linux GUI этого проекта строится на **PyQt**. Если более поздний decision record, одобренный владельцем, не изменит это решение, “PyQt” означает линейку PyQt 6.

## Почему PyQt

Проекту нужен полноценный desktop GUI со структурированной навигацией, логами, диагностикой, настройками, редакторами профилей и диалогами подтверждения. Qt хорошо подходит для такой формы приложения, а PyQt сохраняет кодовую базу в Python и при этом даёт зрелую native desktop shell.

## Scope решения после Stage 5

Stage 2 зафиксировал выбор фреймворка, а Stage 5 вводит первый GUI shell skeleton. PyQt6 теперь объявлен как optional dependency `gui`, но не является обязательной зависимостью для read-only проверок. Это означает:

- pure Python модули можно импортировать без установленного PyQt6;
- `python -m zap2_gui.app` показывает текстовое состояние проекта в любой проверочной среде;
- `python -m zap2_gui.app --gui` запускает окно только на локальной машине владельца, где установлен PyQt6 и доступен display server;
- devctl checks не запускают GUI и не требуют системного Qt окружения.

## Архитектурное правило

PyQt относится к application shell и widget layer. Non-UI логика должна оставаться pure Python:

- обнаружение структуры репозитория;
- inventory vendored-ядра;
- генерация build plans;
- планирование диагностики;
- privilege/sudo command plans;
- парсинг логов и report models.

Так тесты смогут выполняться без display server, а GUI не станет единственным способом рассуждать о проекте.

## Stage 5 shell layout

```text
gui/zap2_gui/
  app.py
  qt_compat.py
  qt_app.py
  adapters/gui_state.py
  models/navigation.py
  windows/main_window.py
  widgets/placeholders.py
```

Начальная shell фиксирует разделы `Обзор`, `Ядро`, `Стратегии`, `Диагностика`, `Настройки`, `Логи`. Раздел `Ядро` уже связан с inventory/build map. Остальные разделы пока являются placeholder-страницами и должны развиваться отдельными патчами.

## Не-цели

Не вводить PySide, GTK, Tkinter, Electron, browser-first UI или terminal-first UI как активное направление shell, пока владелец явно не переоткроет решение по GUI-фреймворку. Не смешивать запуск GUI с privileged lifecycle, сборкой ядра, firewall/service mutation или installer behavior.
