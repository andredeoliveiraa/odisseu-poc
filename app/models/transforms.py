"""Transformações geométricas independentes da interface e do renderizador."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TransformParameters:
    """Valores de uma transformação aplicada ao objeto como uma operação."""

    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_degrees: tuple[float, float, float] = (0.0, 0.0, 0.0)
    uniform_scale: float = 1.0

    @property
    def is_identity(self) -> bool:
        return (
            self.translation == (0.0, 0.0, 0.0)
            and self.rotation_degrees == (0.0, 0.0, 0.0)
            and self.uniform_scale == 1.0
        )


def transformation_matrix(
    parameters: TransformParameters,
    pivot: tuple[float, float, float],
) -> np.ndarray:
    """Compõe escala e rotações ao redor do pivô, seguidas da translação."""
    if parameters.uniform_scale <= 0:
        raise ValueError("A escala deve ser maior que zero.")

    rotation_x, rotation_y, rotation_z = np.radians(parameters.rotation_degrees)
    cosine_x, sine_x = np.cos(rotation_x), np.sin(rotation_x)
    cosine_y, sine_y = np.cos(rotation_y), np.sin(rotation_y)
    cosine_z, sine_z = np.cos(rotation_z), np.sin(rotation_z)

    scale = np.diag(
        [
            parameters.uniform_scale,
            parameters.uniform_scale,
            parameters.uniform_scale,
            1.0,
        ]
    )
    rotate_x = np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, cosine_x, -sine_x, 0.0],
            [0.0, sine_x, cosine_x, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    rotate_y = np.array(
        [
            [cosine_y, 0.0, sine_y, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [-sine_y, 0.0, cosine_y, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    rotate_z = np.array(
        [
            [cosine_z, -sine_z, 0.0, 0.0],
            [sine_z, cosine_z, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    pivot_to_origin = np.eye(4)
    pivot_to_origin[:3, 3] = -np.asarray(pivot, dtype=float)
    restore_pivot = np.eye(4)
    restore_pivot[:3, 3] = np.asarray(pivot, dtype=float)
    translate = np.eye(4)
    translate[:3, 3] = np.asarray(parameters.translation, dtype=float)

    return (
        translate
        @ restore_pivot
        @ rotate_z
        @ rotate_y
        @ rotate_x
        @ scale
        @ pivot_to_origin
    )
