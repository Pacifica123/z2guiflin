# Конспект старого проекта

Предыдущий Linux-проект теперь является источником черновиков, а не активной implementation baseline. Полезные идеи, которые нужно перенести дальше:

- строгая privilege boundary между GUI planning и system mutation;
- guided lifecycle flows вместо необъяснённых кнопок;
- “optimal next action” как dashboard concept;
- source alignment reports для патчей, которые заявляют соответствие upstream/reference behavior;
- transactional thinking вокруг apply/rollback/logging;
- локализация как требование продукта, а не поздняя доработка;
- bytecode-safe и cache-safe checks в devctl.

Главный урок также отрицательный: множество guarded installer patches всё равно могут не доходить до сути продукта, если архитектура центрирована на remote installation. `v0.3-alpha` меняет центр тяжести на vendored native core source tree.
