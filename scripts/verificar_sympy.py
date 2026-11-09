"""Executa o bloco `verificacao` de uma resolução curada com SymPy.

O código em `codigo_sympy` deve definir a variável `resultado`. Ele roda com o
namespace do SymPy já importado (from sympy import *) e com `Fraction`/`math`
disponíveis. `resultado_esperado` é uma expressão SymPy em texto (ex.: "125",
"Rational(3, 8)", "2.5", "sqrt(2)"). A comparação é numérica, com tolerância
absoluta `tolerancia` (padrão 1e-9), ou simbólica quando o resultado não é
numérico (ex.: uma expressão em x).
"""
from __future__ import annotations

import math
from fractions import Fraction

import sympy
from sympy import N, S, simplify, sympify


def _namespace() -> dict:
    ns: dict = {}
    exec("from sympy import *", ns)  # noqa: S102 — código de curadoria versionado no repo
    ns.update({"Fraction": Fraction, "math": math, "sympy": sympy})
    return ns


def executar_verificacao(verificacao: dict) -> tuple[bool, str]:
    ns = _namespace()
    try:
        exec(verificacao["codigo_sympy"], ns)  # noqa: S102
    except Exception as e:  # noqa: BLE001
        return False, f"erro ao executar codigo_sympy: {type(e).__name__}: {e}"
    if "resultado" not in ns:
        return False, "codigo_sympy não definiu a variável `resultado`"
    obtido = ns["resultado"]
    try:
        esperado = sympify(verificacao["resultado_esperado"], locals=ns)
    except Exception as e:  # noqa: BLE001
        return False, f"resultado_esperado inválido: {e}"
    tol = float(verificacao.get("tolerancia", 1e-9))
    try:
        if isinstance(obtido, (list, tuple, set, frozenset)):
            obtido_s = sorted((S(x) for x in obtido), key=lambda v: str(v))
            esperado_s = sorted((S(x) for x in esperado), key=lambda v: str(v))
            if len(obtido_s) != len(esperado_s):
                return False, f"obtido {obtido!r}, esperado {esperado!r}"
            for a, b in zip(obtido_s, esperado_s):
                if abs(float(N(a - b))) > tol:
                    return False, f"obtido {obtido!r}, esperado {esperado!r}"
            return True, "ok"
        obtido_e = S(obtido)
        if obtido_e.is_number and esperado.is_number:
            if abs(float(N(obtido_e - esperado))) <= tol:
                return True, "ok"
            return False, f"obtido {obtido_e} ({float(N(obtido_e)):.6g}), esperado {esperado}"
        if simplify(obtido_e - esperado) == 0:
            return True, "ok"
        return False, f"obtido {obtido_e}, esperado {esperado}"
    except Exception as e:  # noqa: BLE001
        return False, f"erro ao comparar: {type(e).__name__}: {e}"
