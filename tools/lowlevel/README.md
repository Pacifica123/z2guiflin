# Low-level tools

Здесь зарезервировано место для будущих низкоуровневых инструментов рядом с
уровнем `nfqws2`: TCP parser, Ethernet-less IPv4 header parser, packet fixtures,
минимальные dissect/debug utilities и подобные штуки.

По умолчанию это зона read-only/offline экспериментов. Инструменты отсюда не
должны менять сетевые правила, service state или runtime state без отдельного
owner-confirmed слоя.
