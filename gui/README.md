# GUI-пакет

`gui/` содержит наш application-side Python-код и будет развиваться в desktop GUI на PyQt. Он не должен поглощать upstream-исходники ядра и не должен выполнять privileged host mutations во время import.

Начальные обязанности пакета до появления PyQt shell:

- знать структуру репозитория;
- читать vendored-core metadata, inventory snapshot и build map;
- предоставлять будущую точку входа GUI shell;
- держать привилегированные операции за явными user-owned plans.

Настоящий UI следует вводить постепенно как PyQt shell после стабилизации дерева исходников, inventory/build-map модели и продуктовых правил. Не переключать планируемую shell на PySide, GTK, Tkinter, Electron или CLI-only interface без явного решения владельца.
