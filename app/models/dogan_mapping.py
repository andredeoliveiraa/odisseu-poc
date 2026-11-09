"""Mapeamento entre as 25 variáveis de Dogan (2017) e HullParameters.

As variáveis de projeto de Dogan não têm correspondência um-a-um com
:class:`~app.models.hull_model.HullParameters`.  Este módulo centraliza a
conversão e documenta o que está mapeado com alta confiança, o que depende de
dados externos e o que não tem campo.

Referência: Dogan & Gunpinar, Ocean Engineering 145 (2017) 215–229.
DOI: 10.1016/j.oceaneng.2017.08.056
"""

from __future__ import annotations

from app.models.hull_model import HullParameters

# ---------------------------------------------------------------------------
# Campos ainda sem mapeamento confirmado
# ---------------------------------------------------------------------------
# Esses campos são copiados do ``base`` em dogan_to_hull_parameters().
# Não é um default silencioso: o índice GMDH do casco renderizado vai divergir
# do índice do vetor original nesses campos, até cada TODO ser resolvido.
#
# TODO H     — Dogan H é a altura vertical da roda de proa; confirmar se
#              coincide com HullParameters.H (mesma grandeza, mas unidades ou
#              convenção podem diferir).
# TODO K     — Dogan a1 é a largura total do painel plano do fundo;
#              HullParameters.K é a meia-largura. Mapear como K = a1 / 2
#              depois de confirmar no gerador.
# TODO beta  — Dogan θ → HullParameters.beta (swap de nomenclatura confirmado
#              pelo gerador: beta = arctan(H/rake)); validar antes de ativar.
# TODO alpha — Dogan α → HullParameters.alpha (inclinação do convés);
#              aparentemente direto, mas confirmar convenção de sinal.
# TODO theta — Dogan β → HullParameters.theta (swap de nomenclatura confirmado;
#              theta = ângulo de entrada em planta); validar antes de ativar.
# TODO Fb   — sem variável equivalente em Dogan; manter do base.
UNMAPPED: tuple[str, ...] = ("Fb", "H", "K", "beta", "alpha", "theta")

# Campos de Dogan sem nenhum campo em HullParameters.
# Quando o GMDH estiver disponível, a diferença de índice devida a esses
# campos pode ser quantificada pelo teste de reavaliação.
NO_FIELD: tuple[str, ...] = ("De2", "Dm2", "Dr2", "R0r", "R1e", "R1m", "R1r", "alpha2")


def dogan_to_hull_parameters(
    x: dict[str, float],
    base: HullParameters,
    res1: float,
    res2: float,
    rek: float,
    rms: tuple[float, float],
    rrs: tuple[float, float],
) -> HullParameters:
    """Converte um vetor de projeto de Dogan (2017) em :class:`HullParameters`.

    Parâmetros
    ----------
    x:
        As 25 variáveis de Dogan, já em unidades do gerador (metros ou graus).
        Deve conter pelo menos: ``Le``, ``Lm``, ``Lr``, ``Be``, ``Bm``,
        ``Br``, ``De1``, ``Dm1``, ``Dr1``.
    base:
        Casco de referência.  Campos listados em :data:`UNMAPPED` são copiados
        daqui — ver docstring do módulo para os TODOs correspondentes.
    res1:
        Raio mínimo da curva superior da estação de entrada (metros).
        Corresponde a Dogan R4 (nível 1–3 → metros; conversão por quem chama).
    res2:
        Raio mínimo da curva inferior da estação de entrada (metros).
        Corresponde a Dogan R5.
    rek:
        Raio mínimo da curva longitudinal da quilha na entrada (metros).
        Corresponde a Dogan R0e.
    rms:
        ``(Rms1, Rms2)`` da estação do meio em metros.  Dogan R4m/R5m foram
        eliminados no Survey 2; quem chama fornece os valores adequados.
    rrs:
        ``(Rrs1, Rrs2)`` da estação de popa em metros.  Idem para R4r/R5r.

    Returns
    -------
    HullParameters
        Casco renderizável com os campos mapeados preenchidos.

    Raises
    ------
    ValueError
        Se qualquer raio obrigatório for ``None``.
    KeyError
        Se alguma variável de alta confiança faltar em ``x``.
    """
    for name, value in (("res1", res1), ("res2", res2), ("rek", rek)):
        if value is None:
            raise ValueError(
                f"raio '{name}' não informado: converta o nível de Dogan para "
                "metros antes de chamar dogan_to_hull_parameters()."
            )
    for name, value in (("rms[0]", rms[0]), ("rms[1]", rms[1]),
                        ("rrs[0]", rrs[0]), ("rrs[1]", rrs[1])):
        if value is None:
            raise ValueError(
                f"raio '{name}' não informado: forneça os valores em metros."
            )

    scale = x["De1"] / base.De

    return HullParameters(
        # Alta confiança
        Le=x["Le"],
        Lm=x["Lm"],
        Lr=x["Lr"],
        Be=x["Be"],
        Bm=x["Bm"],
        Br=x["Br"],
        De=x["De1"],
        Dm=x["Dm1"],
        Dr=x["Dr1"],
        # Derivados por escala (mesma estratégia de HullDesign.to_parameters)
        Fe=base.Fe / base.De * x["De1"],
        Fm=base.Fm / base.Dm * x["Dm1"],
        Fr=base.Fr / base.Dr * x["Dr1"],
        Ce=base.Ce * scale,
        Cm=base.Cm * scale,
        Cr=base.Cr * scale,
        # Raios: obrigatórios, vindos de quem chama
        Rek=rek,
        Res1=res1,
        Res2=res2,
        Rms1=rms[0],
        Rms2=rms[1],
        Rrs1=rrs[0],
        Rrs2=rrs[1],
        # Sem mapeamento confirmado: copiar do base (limitação em UNMAPPED)
        Fb=base.Fb,
        H=base.H,         # TODO: mapear x["H"]
        K=base.K,         # TODO: mapear x["a1"] / 2
        beta=base.beta,   # TODO: Dogan θ → beta
        alpha=base.alpha, # TODO: Dogan α → alpha
        theta=base.theta, # TODO: Dogan β → theta
        # Sem campo: De2, Dm2, Dr2, R0r, R1e, R1m, R1r, alpha2
    )
