"""Identidade visual simples e consistente para a aplicação."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


APPLICATION_STYLESHEET = """
QWidget {
    background-color: #171b20;
    color: #edf2f7;
}
QMainWindow, QMenuBar, QMenu, QStatusBar, QToolBar {
    background-color: #171b20;
}
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #27313b;
}
QToolBar {
    border: none;
    border-bottom: 1px solid #303943;
    spacing: 6px;
    padding: 6px;
}
QToolButton {
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 9px;
}
QToolButton:hover {
    background-color: #27313b;
    border-color: #3b4652;
}
QDockWidget {
    color: #edf2f7;
}
QDockWidget::title {
    background-color: #20262d;
    border-bottom: 1px solid #303943;
    padding: 8px;
    text-align: left;
}
QGroupBox {
    border: 1px solid #35404b;
    border-radius: 7px;
    margin-top: 13px;
    padding: 13px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QDoubleSpinBox, QSpinBox {
    background-color: #20262d;
    border: 1px solid #3b4652;
    border-radius: 5px;
    padding: 4px 7px;
    selection-background-color: #2379b5;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #4ea5d9;
}
QPushButton {
    background-color: #27313b;
    border: 1px solid #3b4652;
    border-radius: 6px;
    padding: 7px 11px;
}
QPushButton:hover {
    background-color: #313d49;
}
QPushButton:pressed {
    background-color: #202830;
}
QPushButton:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {
    color: #6f7b86;
    background-color: #1d2228;
}
QPushButton#primaryButton {
    background-color: #2379b5;
    border-color: #3f9bd5;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background-color: #2d8dcc;
}
QPushButton#secondaryButton {
    border-color: #3f9bd5;
    color: #d9effc;
}
QLabel#panelTitle {
    font-size: 19px;
    font-weight: 700;
}
QLabel#secondaryText {
    color: #aab4bf;
}
QLabel#modeHint {
    background-color: #302a1e;
    border: 1px solid #725d2c;
    border-radius: 6px;
    color: #e8d59c;
    padding: 9px;
}
QLabel[state="valid"] {
    color: #74c991;
}
QLabel[state="error"] {
    color: #ff8b86;
}
QProgressBar {
    background-color: #20262d;
    border: 1px solid #35404b;
    border-radius: 4px;
}
QProgressBar::chunk {
    background-color: #4ea5d9;
    border-radius: 3px;
}
QStatusBar {
    border-top: 1px solid #303943;
}
QScrollArea {
    border: none;
}
"""


def apply_application_style(application: QApplication) -> None:
    """Aplica tema e tipografia sem depender do tema do sistema operacional."""
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 10))
    application.setStyleSheet(APPLICATION_STYLESHEET)
