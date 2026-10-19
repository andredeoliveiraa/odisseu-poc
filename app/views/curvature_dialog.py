"""Gráficos de curvatura das curvas características (Figura 3.15 da referência)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import bezier as bz
from app.models.hull_model import REGION_NAMES, HullModel
from app.models.shape_operators import continuity_report

INPUT_COLOR = QColor("#4ea5d9")
MODIFIED_COLOR = QColor("#ff9f4a")


class CurvePlot(QWidget):
    """Curvatura ao longo da curva: entrada (azul) e modificada (laranja)."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._series: list[tuple[np.ndarray, QColor]] = []
        self._similarity: float | None = None
        self.setMinimumSize(260, 170)

    def set_data(
        self, before: np.ndarray, after: np.ndarray, similarity: float | None
    ) -> None:
        self._series = [(before, INPUT_COLOR), (after, MODIFIED_COLOR)]
        self._similarity = similarity
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - API do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#1c2127"))
        margin_left, margin_bottom, margin_top = 46, 22, 26
        area = QRectF(
            margin_left,
            margin_top,
            self.width() - margin_left - 10,
            self.height() - margin_top - margin_bottom,
        )
        painter.setPen(QColor("#c7d2dd"))
        text = self._title
        if self._similarity is not None:
            text += f"   F = {self._similarity:.7f}"
        painter.drawText(QPointF(10, 17), text)
        painter.setPen(QPen(QColor("#3b4652"), 1))
        painter.drawRect(area)
        if not self._series:
            return
        top = max(float(values.max()) for values, _ in self._series)
        top = top * 1.08 if top > 0 else 1.0
        painter.setPen(QColor("#aab4bf"))
        painter.drawText(QPointF(4, area.top() + 10), f"{top:.3g}")
        painter.drawText(QPointF(4, area.bottom()), "0")
        painter.drawText(QPointF(area.left(), self.height() - 6), "i = 0")
        painter.drawText(QPointF(area.right() - 40, self.height() - 6), f"i = {len(self._series[0][0]) - 1}")
        for values, color in self._series:
            painter.setPen(QPen(color, 2))
            count = len(values)
            points = [
                QPointF(
                    area.left() + area.width() * index / max(count - 1, 1),
                    area.bottom() - area.height() * float(value) / top,
                )
                for index, value in enumerate(values)
            ]
            painter.drawPolyline(points)


class CurvatureDialog(QDialog):
    """Compara a curvatura das curvas antes e depois dos operadores."""

    def __init__(self, before: HullModel, after: HullModel, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verificação de fairness · distribuição de curvatura")
        self.resize(900, 560)
        self._before = before
        self._after = after

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Curvatura das curvas características antes (azul) e depois (laranja) "
            "da última aplicação de operadores. A função objetivo F (cosseno entre "
            "as distribuições) vale 1 quando as curvas têm a mesma forma."
        )
        intro.setWordWrap(True)
        intro.setObjectName("secondaryText")
        layout.addWidget(intro)

        header = QHBoxLayout()
        header.addWidget(QLabel("Região:"))
        self.region = QComboBox()
        self.region.addItems(REGION_NAMES)
        self.region.setCurrentIndex(1)
        self.region.currentIndexChanged.connect(self._refresh)
        header.addWidget(self.region)
        header.addStretch()
        layout.addLayout(header)

        plots = QHBoxLayout()
        self._plots = {
            "Linha de convés": CurvePlot("Linha de convés"),
            "Linha de quina": CurvePlot("Linha de quina"),
            "Linha de quilha": CurvePlot("Linha de quilha"),
        }
        for plot in self._plots.values():
            plots.addWidget(plot)
        layout.addLayout(plots, 1)

        self.continuity = QLabel()
        self.continuity.setWordWrap(True)
        layout.addWidget(self.continuity)

        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        self._refresh()

    def _refresh(self) -> None:
        region = self.region.currentIndex()
        sources = {
            "Linha de convés": (self._before.deck, self._after.deck),
            "Linha de quina": (self._before.chine, self._after.chine),
            "Linha de quilha": (self._before.keel, self._after.keel),
        }
        for name, plot in self._plots.items():
            old_curves, new_curves = sources[name]
            before = bz.curvature_distribution(old_curves[region])
            after = bz.curvature_distribution(new_curves[region])
            similarity = float(bz.similarity(before, after[None, :])[0])
            plot.set_data(before, after, similarity)

        worst = max(continuity_report(self._after).values())
        self.continuity.setText(
            f"Continuidade G1 nas estações: desvio angular máximo de {worst:.4f}° "
            "(0° indica segmentos de controle colineares)."
        )
        self.continuity.setProperty("state", "valid" if worst < 0.01 else "warning")
        self.continuity.style().unpolish(self.continuity)
        self.continuity.style().polish(self.continuity)
