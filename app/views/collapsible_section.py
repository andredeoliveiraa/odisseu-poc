"""Seção recolhível reutilizada pelo painel de parâmetros."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLayout, QPushButton, QVBoxLayout, QWidget


class CollapsibleSection(QFrame):
    """Agrupamento com cabeçalho clicável que mostra ou esconde o conteúdo.

    Ocupa o lugar de um ``QGroupBox`` no painel, mas em formato de sanfona:
    cada seção pode ser recolhida para reduzir a rolagem quando o usuário não
    está mexendo nela.
    """

    EXPANDED_MARK = "▾"
    COLLAPSED_MARK = "▸"

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        expanded: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self._title = title

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = QPushButton(self)
        self._header.setObjectName("sectionHeader")
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setAccessibleName(title)
        self._header.setToolTip(f"Clique para recolher ou expandir “{title}”.")
        self._header.toggled.connect(self._on_toggled)
        outer.addWidget(self._header)

        self._content = QWidget(self)
        self._content.setObjectName("sectionContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 6, 12, 12)
        self._content_layout.setSpacing(8)
        outer.addWidget(self._content)

        self._apply_state(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._apply_state(checked)
        self.toggled.emit(checked)

    def _apply_state(self, expanded: bool) -> None:
        mark = self.EXPANDED_MARK if expanded else self.COLLAPSED_MARK
        self._header.setText(f"{mark}  {self._title}")
        self._content.setVisible(expanded)

    def add_layout(self, layout: QLayout) -> None:
        """Acrescenta um layout ao corpo da seção, na ordem de inserção."""
        self._content_layout.addLayout(layout)

    def add_widget(self, widget: QWidget) -> None:
        """Acrescenta um widget ao corpo da seção, na ordem de inserção."""
        self._content_layout.addWidget(widget)

    def is_expanded(self) -> bool:
        return self._header.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._header.setChecked(expanded)

    def setEnabled(self, enabled: bool) -> None:
        """Desabilita apenas o conteúdo; o cabeçalho continua recolhível.

        Uma seção desabilitada (por exemplo, os parâmetros do gerador com uma
        malha importada) ainda precisa poder ser aberta e fechada, mesmo que
        os campos dentro dela fiquem inativos.
        """
        self._content.setEnabled(enabled)
