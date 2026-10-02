"""Diálogo para escolher qual superfície NURBS de um .3dm editar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.models.nurbs_surface import NurbsFaceInfo


class NurbsFaceSelectionDialog(QDialog):
    """Lista as superfícies encontradas num .3dm para o usuário escolher uma.

    Um casco modelado no Rhino normalmente vem em várias superfícies —
    costado, fundo, espelho de popa — então esta tela deixa explícito qual
    delas vai ganhar pontos de controle editáveis, em vez de adivinhar.
    """

    def __init__(self, candidates: list[NurbsFaceInfo], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Escolher superfície para editar")
        self.resize(600, 380)
        self._candidates = candidates

        layout = QVBoxLayout(self)
        message = (
            "Este arquivo tem várias superfícies. Escolha qual delas você "
            "quer editar por pontos de controle; a maior costuma ser o "
            "costado principal do casco."
            if len(candidates) > 1
            else "Superfície encontrada neste arquivo:"
        )
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.list_widget = QListWidget(self)
        for info in candidates:
            item = QListWidgetItem(info.describe())
            item.setData(Qt.ItemDataRole.UserRole, info.face_index)
            self.list_widget.addItem(item)
        if candidates:
            # Palpite razoável: a superfície com mais pontos de controle
            # tende a ser o costado principal, não um painel plano auxiliar.
            best = max(range(len(candidates)), key=lambda i: candidates[i].control_point_count)
            self.list_widget.setCurrentRow(best)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_face_index(self) -> int | None:
        """Índice da face escolhida, ou ``None`` se nada estiver selecionado."""
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
