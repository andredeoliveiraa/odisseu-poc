"""Ponto de entrada da aplicação CAD de cascos."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    """Cria a aplicação Qt e inicia o loop de eventos."""
    application = QApplication(sys.argv)
    application.setApplicationName("Odisseu")
    application.setOrganizationName("Odisseu")

    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
