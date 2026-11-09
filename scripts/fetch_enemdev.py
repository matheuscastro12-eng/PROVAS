"""Baixa as questões de Matemática do ENEM da API pública enem.dev.

A enem.dev é uma transcrição comunitária das provas oficiais do INEP. Este script
apenas grava a resposta bruta da API em cache (fora do repo); a normalização para o
schema do Gabarita é feita por build.py.

Uso:
    uv run python scripts/fetch_enemdev.py            # anos 2009–2023
    uv run python scripts/fetch_enemdev.py 2022 2023  # anos específicos
    uv run python scripts/fetch_enemdev.py --forcar   # ignora cache
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

from comum import ANOS_PADRAO, DIR_CACHE_ENEMDEV, gravar_json, ler_json

BASE = "https://api.enem.dev/v1"
LIMITE = 50
CABECALHOS = {"User-Agent": "gabarita-banco-questoes/0.1 (uso educacional; fonte: INEP via enem.dev)"}


def buscar_pagina(ano: int, offset: int, tentativas: int = 4) -> dict:
    url = f"{BASE}/exams/{ano}/questions"
    for i in range(tentativas):
        try:
            r = requests.get(url, params={"limit": LIMITE, "offset": offset}, headers=CABECALHOS, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:  # noqa: PERF203
            if i == tentativas - 1:
                raise
            print(f"  aviso: {e}; tentando de novo", file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise RuntimeError("inalcançável")


def baixar_ano(ano: int, forcar: bool = False) -> list[dict]:
    destino = DIR_CACHE_ENEMDEV / f"{ano}.json"
    if destino.exists() and not forcar:
        dados = ler_json(destino)
        print(f"{ano}: cache ({len(dados['questoes_matematica'])} questões de matemática)")
        return dados["questoes_matematica"]

    todas: list[dict] = []
    offset = 0
    while True:
        pagina = buscar_pagina(ano, offset)
        todas.extend(pagina["questions"])
        meta = pagina["metadata"]
        if not meta.get("hasMore"):
            break
        offset += LIMITE
        time.sleep(0.3)

    mat = [q for q in todas if q.get("discipline") == "matematica"]
    gravar_json(
        destino,
        {
            "fonte": "https://api.enem.dev/v1",
            "ano": ano,
            "baixado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_questoes_prova": len(todas),
            "questoes_matematica": mat,
        },
    )
    print(f"{ano}: {len(todas)} questões na API, {len(mat)} de matemática")
    return mat


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("anos", nargs="*", type=int, default=ANOS_PADRAO)
    p.add_argument("--forcar", action="store_true", help="rebaixa mesmo com cache")
    args = p.parse_args(argv)
    falhas = []
    for ano in args.anos:
        try:
            baixar_ano(ano, args.forcar)
        except Exception as e:  # noqa: BLE001
            print(f"{ano}: FALHA {e}", file=sys.stderr)
            falhas.append(ano)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
