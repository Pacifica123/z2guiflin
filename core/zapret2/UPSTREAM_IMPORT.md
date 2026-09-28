# Импорт upstream — поколение P03

`core/zapret2` содержит filtered source generation **bol-van/zapret2 1.0.6** на commit `00f5aaa36de500971faf6db440dd7d8b25672281`.

- SHA-256 исходного архива: `769df14fa4463fbe9744a2aab97e7f1bfe1a2f77a669981f4e6372d7b86d71a9`;
- файлов в архиве: `253`;
- исключено policy `zap2-p03-filter-v1`: `9`;
- импортировано upstream-файлов: `244`;
- SHA-256 filtered tree: `fd472f723743909d3f4b281ed8be3a8f9327f5bb091be677bc5f9e5f174e7d22`;
- поколение Lua compatibility: `6`.

Точный commit старого legacy upstream остаётся **исторически невосстановимым**; P03 не придумывает его.

Project-local Lua compatibility и C source transforms больше не скрываются внутри upstream tree. Они находятся в `core/overlays/zapret2/`, имеют собственные hashes/classification и входят в whole-generation receipt отдельно. Canonical `core/zapret2` остаётся byte-exact filtered candidate at rest.
