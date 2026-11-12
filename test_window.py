"""Отдельное тестовое окно (другой процесс) для проверки сугробов."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


def main() -> int:
    app = QApplication(sys.argv)
    window = QWidget(None, Qt.WindowType.Window)
    window.setWindowTitle("ТЕСТОВОЕ ОКНО")
    window.setGeometry(430, 240, 980, 560)
    window.setStyleSheet("background: #eef3fb;")
    layout = QVBoxLayout(window)
    label = QLabel("Проверка сугроба на верхней кромке окна\n(окно из другого процесса)")
    label.setStyleSheet("font-size: 16px; color: #2c3e58; padding: 24px;")
    layout.addWidget(label)
    window.show()
    window.raise_()
    window.activateWindow()

    # Держимся выше развёрнутых окон, но без флага «поверх всех».
    keeper = QTimer(window)
    keeper.timeout.connect(window.raise_)
    keeper.start(700)

    QTimer.singleShot(120_000, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
