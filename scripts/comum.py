"""Utilidades compartilhadas pelos scripts do banco de questões."""
from __future__ import annotations

import json
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATA = RAIZ / "data"
DIR_QUESTOES = DIR_DATA / "questoes" / "matematica"
DIR_RESOLUCOES = DIR_DATA / "resolucoes"
DIR_SCHEMA = RAIZ / "schema"
DIR_TAXONOMIA = RAIZ / "taxonomia"

# Cache de downloads fica fora do repositório (zips e CSVs brutos do INEP não são versionados).
DIR_CACHE = Path(os.environ.get("GABARITA_CACHE", "/workspace/gabarita/cache"))
DIR_CACHE_ENEMDEV = DIR_CACHE / "enemdev"
DIR_CACHE_INEP = DIR_CACHE / "inep"

ANOS_PADRAO = list(range(2009, 2024))


def ler_json(caminho: Path):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho: Path, dados, indent: int = 2) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=indent)
        f.write("\n")
