"""Gráfico de resistência ao avanço em função da velocidade."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.models.hydrodynamics import KNOT, ResistancePoint

SURFACE = QColor("#1c2127")
GRID = QColor("#2b333c")
AXIS = QColor("#3b4652")
TEXT_PRIMARY = QColor("#edf2f7")
TEXT_SECONDARY = QColor("#aab4bf")
MARKER = QColor("#aab4bf")


@dataclass(frozen=True)
class Series:
    key: str
    label: str
    color: QColor


# Paleta categórica (modo escuro), validada contra a superfície #1c2127.
SERIES = (
    Series("total", "Total (Rt)", QColor("#3987e5")),
    Series("wave", "Ondas (Rw)", QColor("#d95926")),
    Series("friction", "Atrito (Rf)", QColor("#199e70")),
)


def _nice_step(span: float, target: int = 5) -> float:
    raw = span / max(target, 1)
    magnitude = 10 ** np.floor(np.log10(raw)) if raw > 0 else 1.0
    for factor in (1, 2, 2.5, 5, 10):
        if factor * magnitude >= raw:
            return factor * magnitude
    return 10 * magnitude


class ResistanceChart(QWidget):
    """Linhas de Rt, Rw e Rf (kN) por velocidade (nós), com mira ao passar o mouse."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._points: list[ResistancePoint] = []
        self._design_speed: float | None = None
        self._hover_index: int | None = None
        self._message = "Calculando…"

    def set_message(self, message: str) -> None:
        self._points = []
        self._message = message
        self.update()

    def set_curve(self, points: list[ResistancePoint], design_speed: float | None) -> None:
        self._points = points
        self._design_speed = design_speed
        self._hover_index = None
        self.update()

    # ------------------------------------------------------------- geometria

    def _plot_rect(self) -> QRectF:
        # Espaço à esquerda para os rótulos do eixo y, à direita para os
        # rótulos diretos e em cima para a legenda.
        return QRectF(44, 34, self.width() - 44 - 74, self.height() - 34 - 34)

    def _ranges(self) -> tuple[float, float, float]:
        speeds = np.array([p.speed / KNOT for p in self._points])
        top = max(p.total for p in self._points) / 1000.0
        return float(speeds.min()), float(speeds.max()), float(top)

    def _map(self, speed_knots: float, force_kn: float, rect: QRectF, ranges) -> QPointF:
        low, high, top = ranges
        x = rect.left() + (speed_knots - low) / max(high - low, 1e-9) * rect.width()
        y = rect.bottom() - force_kn / max(top, 1e-9) * rect.height()
        return QPointF(x, y)

    # --------------------------------------------------------------- desenho

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), SURFACE)
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        if not self._points:
            painter.setPen(TEXT_SECONDARY)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        rect = self._plot_rect()
        low, high, top = self._ranges()
        y_step = _nice_step(top)
        top = np.ceil(top / y_step) * y_step
        ranges = (low, high, top)

        # Grade e eixos discretos.
        painter.setPen(QPen(GRID, 1))
        value = 0.0
        while value <= top + 1e-9:
            y = self._map(low, value, rect, ranges).y()
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(TEXT_SECONDARY)
            painter.drawText(
                QRectF(0, y - 8, rect.left() - 6, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:g}",
            )
            painter.setPen(QPen(GRID, 1))
            value += y_step
        x_step = _nice_step(high - low, 6)
        speed = np.ceil(low / x_step) * x_step
        painter.setPen(TEXT_SECONDARY)
        while speed <= high + 1e-9:
            x = self._map(speed, 0, rect, ranges).x()
            painter.drawText(
                QRectF(x - 20, rect.bottom() + 4, 40, 14), Qt.AlignmentFlag.AlignCenter, f"{speed:g}"
            )
            speed += x_step
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 18, rect.width(), 14),
            Qt.AlignmentFlag.AlignCenter,
            "Velocidade (nós)",
        )
        painter.drawText(QRectF(0, rect.top() - 18, 60, 14), Qt.AlignmentFlag.AlignLeft, "kN")
        painter.setPen(QPen(AXIS, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # Legenda numa linha acima do gráfico.
        x = rect.left() + 26
        for series in SERIES:
            painter.setPen(QPen(series.color, 2))
            painter.drawLine(QPointF(x, 11), QPointF(x + 14, 11))
            painter.setPen(TEXT_SECONDARY)
            painter.drawText(QPointF(x + 19, 15), series.label)
            x += 19 + metrics.horizontalAdvance(series.label) + 16

        # Velocidade de projeto.
        if self._design_speed is not None and low <= self._design_speed / KNOT <= high:
            x = self._map(self._design_speed / KNOT, 0, rect, ranges).x()
            pen = QPen(MARKER, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        # Linhas de 2 px e rótulo direto no fim de cada uma.
        labels_y = []
        for series in SERIES:
            path = QPainterPath()
            for index, point in enumerate(self._points):
                position = self._map(point.speed / KNOT, getattr(point, series.key) / 1000.0, rect, ranges)
                path.moveTo(position) if index == 0 else path.lineTo(position)
            pen = QPen(series.color, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            end = path.currentPosition()
            label_y = end.y()
            for used in labels_y:
                if abs(label_y - used) < 13:
                    label_y = used + 13
            labels_y.append(label_y)
            painter.setPen(TEXT_PRIMARY)
            painter.drawText(QPointF(rect.right() + 6, label_y + 4), series.label.split(" ")[-1].strip("()"))

        self._paint_hover(painter, rect, ranges, metrics)

    def _paint_hover(self, painter: QPainter, rect: QRectF, ranges, metrics: QFontMetrics) -> None:
        if self._hover_index is None:
            return
        point = self._points[self._hover_index]
        x = self._map(point.speed / KNOT, 0, rect, ranges).x()
        painter.setPen(QPen(AXIS, 1))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for series in SERIES:
            position = self._map(point.speed / KNOT, getattr(point, series.key) / 1000.0, rect, ranges)
            painter.setPen(QPen(SURFACE, 2))
            painter.setBrush(series.color)
            painter.drawEllipse(position, 4.5, 4.5)

        lines = [f"{point.speed / KNOT:.1f} nós · Fn {point.froude:.2f}"]
        lines += [
            f"{series.label}: {getattr(point, series.key) / 1000.0:.2f} kN" for series in SERIES
        ]
        lines.append(f"Potência efetiva: {point.effective_power / 1000.0:.1f} kW")
        width = max(metrics.horizontalAdvance(line) for line in lines) + 16
        height = len(lines) * 15 + 10
        left = x + 10 if x + 10 + width < self.width() else x - 10 - width
        box = QRectF(left, rect.top() + 4, width, height)
        painter.setPen(QPen(AXIS, 1))
        painter.setBrush(QColor("#171b20"))
        painter.drawRoundedRect(box, 5, 5)
        for index, line in enumerate(lines):
            painter.setPen(TEXT_PRIMARY if index == 0 else TEXT_SECONDARY)
            painter.drawText(QPointF(box.left() + 8, box.top() + 17 + 15 * index), line)

    # --------------------------------------------------------------- mouse

    def mouseMoveEvent(self, event) -> None:
        if not self._points:
            return
        rect = self._plot_rect()
        ranges = self._ranges()
        xs = np.array([self._map(p.speed / KNOT, 0, rect, ranges).x() for p in self._points])
        index = int(np.argmin(np.abs(xs - event.position().x())))
        if rect.adjusted(-12, -12, 12, 12).contains(event.position()):
            if index != self._hover_index:
                self._hover_index = index
                self.update()
        elif self._hover_index is not None:
            self._hover_index = None
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover_index = None
        self.update()
