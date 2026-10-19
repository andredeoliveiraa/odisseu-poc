"""Estrutura de malha de superfície compatível com PyVista."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class HullMesh:
    """Dados de uma malha de superfície compatível com PyVista."""

    vertices: np.ndarray
    faces: np.ndarray
    triangles: np.ndarray = field(
        default_factory=lambda: np.empty((0, 3), dtype=np.int64)
    )

    @property
    def pyvista_faces(self) -> np.ndarray:
        """Retorna faces no formato achatado exigido por ``pyvista.PolyData``."""
        quads = np.hstack((np.full((len(self.faces), 1), 4), self.faces)).ravel()
        triangles = np.hstack(
            (np.full((len(self.triangles), 1), 3), self.triangles)
        ).ravel()
        return np.concatenate((quads, triangles)).astype(np.int64)

    def triangulated(self) -> np.ndarray:
        """Retorna todas as faces como triângulos, útil para cálculos."""
        return np.vstack(
            (self.faces[:, [0, 1, 2]], self.faces[:, [0, 2, 3]], self.triangles)
        )

    @staticmethod
    def weld(
        vertices: np.ndarray,
        quads: np.ndarray,
        tolerance: float = 1e-7,
    ) -> "HullMesh":
        """Funde vértices coincidentes e converte quadriláteros degenerados.

        Os patches de Coons repetem os vértices das bordas compartilhadas e
        colapsam uma aresta nos patches triangulares; depois de fundir os
        vértices, um quadrilátero com três pontos distintos vira triângulo e
        um com menos de três é descartado.
        """
        scale = max(float(np.ptp(vertices, axis=0).max()), 1.0)
        keys = np.round(vertices / (tolerance * scale)).astype(np.int64)
        _, first, inverse = np.unique(
            keys, axis=0, return_index=True, return_inverse=True
        )
        inverse = inverse.ravel()
        # Mantém a ordem original dos vértices únicos (estabilidade da malha).
        order = np.argsort(first)
        rank = np.empty_like(order)
        rank[order] = np.arange(len(order))
        merged_vertices = vertices[first[order]]
        merged = rank[inverse][quads]

        full, triangles = [], []
        for quad in merged:
            distinct = []
            for index in quad:
                if not distinct or distinct[-1] != index:
                    distinct.append(index)
            if len(distinct) > 1 and distinct[0] == distinct[-1]:
                distinct.pop()
            # Só repetições vizinhas formam triângulos legítimos; um quadrilátero
            # dobrado sobre si mesmo (a, b, a, c) tem área nula e é descartado.
            if len(distinct) == 4 and len(set(distinct)) == 4:
                full.append(distinct)
            elif len(distinct) == 3 and len(set(distinct)) == 3:
                triangles.append(distinct)
        return HullMesh(
            vertices=merged_vertices.astype(np.float64),
            faces=np.array(full, dtype=np.int64).reshape(-1, 4),
            triangles=np.array(triangles, dtype=np.int64).reshape(-1, 3),
        )
