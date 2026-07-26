"""Совместимый импорт старого имени вкладки.

Новая основная сущность интерфейса — пресет с упорядоченными traffic-профилями.
"""

from .presets import make_presets_page


def make_strategies_page(root=None):
    """Legacy alias для старой сборки MainWindow."""

    return make_presets_page(root)
