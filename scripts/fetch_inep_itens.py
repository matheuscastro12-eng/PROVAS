"""Baixa os microdados do ENEM (INEP) e extrai só o arquivo ITENS_PROVA_{ano}.csv.

Fonte: https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip
(páginas: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem)

Os zips são grandes (centenas de MB), por isso ficam em GABARITA_CACHE
(padrão /workspace/gabarita/cache), fora do repositório, e nunca são versionados.
Do zip extraímos apenas o CSV de itens, e dele gravamos um JSON compacto com os
itens de Matemática (SG_AREA = 'MT'): posição, gabarito, habilidade, parâmetros TRI
(a, b, c), cor do caderno, código da prova e flag de item anulado.

Uso:
    uv run python scripts/fetch_inep_itens.py                # 2019–2023
    uv run python scripts/fetch_inep_itens.py 2021 2022
    uv run python scripts/fetch_inep_itens.py 2022 --csv /caminho/ITENS_PROVA_2022.csv  # CSV já baixado

Se o download falhar (o host do INEP às vezes recusa conexões fora do Brasil), o
script registra a falha em inep/status.json e build.py segue com tri = null.
"""
from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import requests

from comum import DIR_CACHE_INEP, gravar_json, ler_json

URL_ZIP = "https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"
ANOS_PADRAO = [2019, 2020, 2021, 2022, 2023]
CABECALHOS = {"User-Agent": "Mozilla/5.0 (gabarita-banco-questoes; uso educacional)"}


def _num(valor: str | None) -> float | None:
    if valor is None:
        return None
    v = valor.strip().replace(",", ".")
    if v == "" or v.upper() in {"NA", "NULL"}:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def baixar_zip(ano: int, destino: Path, tentativas: int = 3) -> Path:
    """Baixa o zip com retomada (Range). Levanta exceção se não conseguir."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    url = URL_ZIP.format(ano=ano)
    ultimo_erro: Exception | None = None
    for i in range(tentativas):
        ja = destino.stat().st_size if destino.exists() else 0
        cab = dict(CABECALHOS)
        if ja:
            cab["Range"] = f"bytes={ja}-"
        try:
            with requests.get(url, headers=cab, stream=True, timeout=120) as r:
                if r.status_code == 416:  # já completo
                    return destino
                if r.status_code == 200 and ja:
                    ja = 0  # servidor ignorou o Range: recomeça
                r.raise_for_status()
                modo = "ab" if ja else "wb"
                with open(destino, modo) as f:
                    for bloco in r.iter_content(chunk_size=1 << 20):
                        f.write(bloco)
            return destino
        except requests.RequestException as e:
            ultimo_erro = e
            print(f"  {ano}: tentativa {i + 1} falhou: {e}", file=sys.stderr)
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"download do INEP falhou para {ano}: {ultimo_erro}")


def localizar_csv_itens(zip_path: Path, ano: int) -> str:
    """Equivalente a `unzip -l`: acha o caminho de ITENS_PROVA_{ano}.csv dentro do zip."""
    with zipfile.ZipFile(zip_path) as z:
        nomes = z.namelist()
    alvo = f"ITENS_PROVA_{ano}.csv".lower()
    cands = [n for n in nomes if n.lower().endswith(alvo)]
    if not cands:
        cands = [n for n in nomes if "itens_prova" in n.lower() and n.lower().endswith(".csv")]
    if not cands:
        raise FileNotFoundError(f"ITENS_PROVA_{ano}.csv não encontrado no zip ({len(nomes)} arquivos)")
    return cands[0]


def extrair_csv(zip_path: Path, membro: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    # unzip extrai só o membro pedido, sem descompactar o resto (os microdados têm vários GB).
    try:
        subprocess.run(["unzip", "-o", "-q", "-j", str(zip_path), membro, "-d", str(destino.parent)], check=True)
        extraido = destino.parent / Path(membro).name
        if extraido != destino:
            extraido.rename(destino)
    except (FileNotFoundError, subprocess.CalledProcessError):
        with zipfile.ZipFile(zip_path) as z, z.open(membro) as src, open(destino, "wb") as dst:
            dst.write(src.read())
    return destino


def ler_itens_mt(csv_path: Path) -> list[dict]:
    """Lê ITENS_PROVA_{ano}.csv (latin-1, separador ';') e devolve só os itens de Matemática."""
    bruto = csv_path.read_bytes()
    for enc in ("latin-1", "utf-8-sig"):
        try:
            texto = bruto.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = bruto.decode("latin-1", errors="replace")
    primeira = texto.splitlines()[0]
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=sep)
    itens = []
    for linha in leitor:
        if (linha.get("SG_AREA") or "").strip() != "MT":
            continue
        itens.append(
            {
                "posicao": int(linha["CO_POSICAO"]),
                "co_item": (linha.get("CO_ITEM") or "").strip(),
                "gabarito": (linha.get("TX_GABARITO") or "").strip(),
                "habilidade": int(_num(linha.get("CO_HABILIDADE")) or 0) or None,
                "anulado": (linha.get("IN_ITEM_ABAN") or "0").strip() == "1",
                "motivo_anulacao": (linha.get("TX_MOTIVO_ABAN") or "").strip() or None,
                "a": _num(linha.get("NU_PARAM_A")),
                "b": _num(linha.get("NU_PARAM_B")),
                "c": _num(linha.get("NU_PARAM_C")),
                "cor": (linha.get("TX_COR") or "").strip().upper(),
                "co_prova": (linha.get("CO_PROVA") or "").strip(),
                "lingua": (linha.get("TP_LINGUA") or "").strip() or None,
                "adaptado": (linha.get("IN_ITEM_ADAPTADO") or "").strip() or None,
            }
        )
    return itens


def processar_ano(ano: int, csv_manual: Path | None = None) -> dict:
    status = {"ano": ano, "ok": False, "erro": None, "url": URL_ZIP.format(ano=ano)}
    try:
        if csv_manual:
            csv_path = csv_manual
        else:
            csv_path = DIR_CACHE_INEP / f"ITENS_PROVA_{ano}.csv"
            if not csv_path.exists():
                zip_path = DIR_CACHE_INEP / f"microdados_enem_{ano}.zip"
                baixar_zip(ano, zip_path)
                membro = localizar_csv_itens(zip_path, ano)
                extrair_csv(zip_path, membro, csv_path)
        itens = ler_itens_mt(csv_path)
        provas = {}
        for it in itens:
            chave = it["co_prova"]
            provas.setdefault(chave, {"co_prova": chave, "cor": it["cor"], "n_itens": 0, "n_com_tri": 0})
            provas[chave]["n_itens"] += 1
            provas[chave]["n_com_tri"] += int(it["b"] is not None)
        gravar_json(
            DIR_CACHE_INEP / f"itens_mt_{ano}.json",
            {"fonte": status["url"], "ano": ano, "arquivo": f"ITENS_PROVA_{ano}.csv", "provas": sorted(provas.values(), key=lambda p: p["co_prova"]), "itens": itens},
        )
        status.update(ok=True, n_itens_mt=len(itens), n_provas=len(provas))
        print(f"{ano}: {len(itens)} itens de MT em {len(provas)} cadernos")
    except Exception as e:  # noqa: BLE001
        status["erro"] = f"{type(e).__name__}: {e}"
        print(f"{ano}: FALHA — {status['erro']}", file=sys.stderr)
    return status


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("anos", nargs="*", type=int, default=ANOS_PADRAO)
    p.add_argument("--csv", type=Path, help="usar um ITENS_PROVA_{ano}.csv já baixado (só com um ano)")
    args = p.parse_args(argv)
    if args.csv and len(args.anos) != 1:
        p.error("--csv exige exatamente um ano")

    status_path = DIR_CACHE_INEP / "status.json"
    status = ler_json(status_path) if status_path.exists() else {}
    for ano in args.anos:
        status[str(ano)] = processar_ano(ano, args.csv) | {"verificado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        gravar_json(status_path, status)  # grava a cada ano para não perder o registro se interrompido
    return 0 if all(status[str(a)]["ok"] for a in args.anos) else 1


if __name__ == "__main__":
    sys.exit(main())
