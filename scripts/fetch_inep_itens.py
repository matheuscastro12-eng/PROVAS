"""Lê os microdados do ENEM (INEP) e extrai só os itens de Matemática de ITENS_PROVA_{ano}.csv.

Fonte oficial: https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip
(páginas: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem)
Espelho público usado quando o host do INEP está inacessível: Zenodo record 18801899,
"Microdados Oficiais do ENEM (2009-2023) - Relação Itens e Prova",
https://zenodo.org/records/18801899 (só os CSVs ITENS_PROVA_{ano}.csv).

Os zips são grandes (centenas de MB), por isso ficam em GABARITA_CACHE
(padrão /workspace/gabarita/cache), fora do repositório, e nunca são versionados.
Do CSV gravamos um JSON compacto com os itens de Matemática (SG_AREA = 'MT'): posição,
gabarito, habilidade, parâmetros TRI (a, b, c), cor do caderno, código da prova e flag de
item anulado.

Validação dos parâmetros TRI (faixas plausíveis: a em (0, 6], b em [-6, 6], c em [0, 1)):
  - valor dentro da faixa → aceito como está;
  - valor fora da faixa com o padrão de decimal quebrado do espelho ("141.931" no lugar de
    "1.41931": a string é um inteiro formatado com separador de milhar) → corrigido pela
    inserção do ponto decimal após o primeiro dígito, SÓ se o resultado cair na faixa;
    o item recebe tri_corrigido = true;
  - qualquer outro valor fora da faixa (ex.: b = 17.62443 com a = 0.09882, publicado assim
    pelo INEP) → os três parâmetros viram null e o motivo fica em tri_descartado.

Uso:
    uv run python scripts/fetch_inep_itens.py                     # baixa 2019–2023 do INEP
    uv run python scripts/fetch_inep_itens.py 2021 2022
    uv run python scripts/fetch_inep_itens.py 2022 --csv /caminho/ITENS_PROVA_2022.csv
    uv run python scripts/fetch_inep_itens.py --csv-dir /workspace/gabarita/cache/zenodo \
        --espelho "Zenodo record 18801899"                        # 2009–2023 a partir dos CSVs do espelho

Se o download falhar (o host do INEP às vezes recusa conexões fora do Brasil), o
script registra a falha em inep/status.json e build.py segue com tri = null.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

import requests

from comum import DIR_CACHE_INEP, gravar_json, ler_json

URL_ZIP = "https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"
URL_ESPELHO_ZENODO = "https://zenodo.org/records/18801899"
ANOS_PADRAO = [2019, 2020, 2021, 2022, 2023]
ANOS_ESPELHO = list(range(2009, 2024))
CABECALHOS = {"User-Agent": "Mozilla/5.0 (gabarita-banco-questoes; uso educacional)"}

# Faixas plausíveis dos parâmetros do modelo logístico de 3 parâmetros na escala do INEP.
FAIXAS = {"a": (0.0, 6.0), "b": (-6.0, 6.0), "c": (0.0, 1.0)}
# Padrão do decimal quebrado do espelho: inteiro com separador de milhar ("141.931", "24.516").
_PADRAO_MILHAR = re.compile(r"^(-?)(\d{1,3})((?:\.\d{3})+)$")


def dentro_da_faixa(nome: str, valor: float) -> bool:
    lo, hi = FAIXAS[nome]
    if nome == "a":
        return lo < valor <= hi
    if nome == "c":
        return lo <= valor < hi
    return lo <= valor <= hi


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


def normalizar_parametro(nome: str, bruto: str | None) -> tuple[float | None, bool, str | None]:
    """Devolve (valor, corrigido, problema).

    valor = None e problema = None → parâmetro ausente no CSV.
    valor = None e problema ≠ None → fora da faixa e sem correção inequívoca.
    corrigido = True → ponto decimal reinserido após o primeiro dígito (padrão do espelho).
    """
    valor = _num(bruto)
    if valor is None:
        return None, False, None
    if dentro_da_faixa(nome, valor):
        return valor, False, None
    m = _PADRAO_MILHAR.match((bruto or "").strip())
    if m:
        sinal, digitos = m.group(1), m.group(2) + m.group(3).replace(".", "")
        corrigido = float(f"{sinal}{digitos[0]}.{digitos[1:]}")
        if dentro_da_faixa(nome, corrigido):
            return corrigido, True, None
    lo, hi = FAIXAS[nome]
    return None, False, f"{nome}={bruto.strip()} fora da faixa [{lo}, {hi}] e sem correção inequívoca"


def normalizar_cor(cor: str) -> str:
    """'Azul', 'AZUL', 'Amarela' → 'AZUL', 'AMARELA' (maiúsculas, sem acento, espaços simples)."""
    t = unicodedata.normalize("NFD", cor.strip().upper())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", t)


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
    """Lê ITENS_PROVA_{ano}.csv (latin-1 ou utf-8, separador ';') e devolve só os itens de Matemática,
    com os parâmetros TRI validados (ver normalizar_parametro)."""
    bruto = csv_path.read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
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
        brutos = {"a": linha.get("NU_PARAM_A"), "b": linha.get("NU_PARAM_B"), "c": linha.get("NU_PARAM_C")}
        params, corrigido, problemas = {}, False, []
        for nome, valor in brutos.items():
            v, corr, problema = normalizar_parametro(nome, valor)
            params[nome] = v
            corrigido = corrigido or corr
            if problema:
                problemas.append(problema)
        if problemas or any(v is None for v in params.values()):
            # TRI só é aproveitado quando os três parâmetros existem e são plausíveis
            params = {"a": None, "b": None, "c": None}
            corrigido = False
        itens.append(
            {
                "posicao": int(linha["CO_POSICAO"]),
                "co_item": (linha.get("CO_ITEM") or "").strip(),
                "gabarito": (linha.get("TX_GABARITO") or "").strip(),
                "habilidade": int(_num(linha.get("CO_HABILIDADE")) or 0) or None,
                "anulado": (linha.get("IN_ITEM_ABAN") or "0").strip() == "1",
                "motivo_anulacao": (linha.get("TX_MOTIVO_ABAN") or "").strip() or None,
                "a": params["a"],
                "b": params["b"],
                "c": params["c"],
                "tri_corrigido": corrigido,
                "tri_descartado": "; ".join(problemas) or None,
                "tri_bruto": {k: (v or "").strip() or None for k, v in brutos.items()} if (corrigido or problemas) else None,
                "cor": normalizar_cor(linha.get("TX_COR") or ""),
                "cor_original": (linha.get("TX_COR") or "").strip(),
                "co_prova": (linha.get("CO_PROVA") or "").strip(),
                "lingua": (linha.get("TP_LINGUA") or "").strip() or None,
                "adaptado": (linha.get("IN_ITEM_ADAPTADO") or "").strip() or None,
                "versao_digital": (linha.get("TP_VERSAO_DIGITAL") or "").strip() or None,
            }
        )
    return itens


def processar_ano(ano: int, csv_manual: Path | None = None, espelho: str | None = None) -> dict:
    status = {"ano": ano, "ok": False, "erro": None, "url": URL_ZIP.format(ano=ano), "espelho": espelho}
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
            provas.setdefault(chave, {"co_prova": chave, "cor": it["cor"], "n_itens": 0, "n_com_tri": 0, "n_tri_corrigidos": 0, "n_tri_descartados": 0})
            provas[chave]["n_itens"] += 1
            provas[chave]["n_com_tri"] += int(it["b"] is not None)
            provas[chave]["n_tri_corrigidos"] += int(it["tri_corrigido"])
            provas[chave]["n_tri_descartados"] += int(it["tri_descartado"] is not None)
        fonte = f"INEP, microdados do ENEM {ano} (ITENS_PROVA)" + (f", espelho {espelho}" if espelho else "")
        gravar_json(
            DIR_CACHE_INEP / f"itens_mt_{ano}.json",
            {
                "fonte": fonte,
                "url_oficial": status["url"],
                "url_espelho": URL_ESPELHO_ZENODO if espelho and "zenodo" in espelho.lower() else None,
                "ano": ano,
                "arquivo": csv_path.name,
                "faixas_tri": FAIXAS,
                "provas": sorted(provas.values(), key=lambda p: int(p["co_prova"]) if p["co_prova"].isdigit() else 0),
                "itens": itens,
            },
        )
        n_corr = sum(1 for it in itens if it["tri_corrigido"])
        n_desc = sum(1 for it in itens if it["tri_descartado"])
        status.update(ok=True, n_itens_mt=len(itens), n_provas=len(provas), n_tri_corrigidos=n_corr, n_tri_descartados=n_desc)
        print(f"{ano}: {len(itens)} itens de MT em {len(provas)} cadernos; TRI corrigidos: {n_corr}, descartados: {n_desc}")
    except Exception as e:  # noqa: BLE001
        status["erro"] = f"{type(e).__name__}: {e}"
        print(f"{ano}: FALHA — {status['erro']}", file=sys.stderr)
    return status


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("anos", nargs="*", type=int)
    p.add_argument("--csv", type=Path, help="usar um ITENS_PROVA_{ano}.csv já baixado (só com um ano)")
    p.add_argument("--csv-dir", type=Path, help="diretório com ITENS_PROVA_{ano}.csv já baixados (ex.: espelho Zenodo)")
    p.add_argument("--espelho", help='descrição do espelho de onde vieram os CSVs (ex.: "Zenodo record 18801899")')
    args = p.parse_args(argv)
    if args.csv and len(args.anos) != 1:
        p.error("--csv exige exatamente um ano")
    if args.csv and args.csv_dir:
        p.error("use --csv ou --csv-dir, não os dois")
    anos = args.anos or (ANOS_ESPELHO if args.csv_dir else ANOS_PADRAO)

    status_path = DIR_CACHE_INEP / "status.json"
    status = ler_json(status_path) if status_path.exists() else {}
    for ano in anos:
        csv_path = args.csv
        if args.csv_dir:
            csv_path = args.csv_dir / f"ITENS_PROVA_{ano}.csv"
            if not csv_path.exists():
                print(f"{ano}: {csv_path} não existe, pulando", file=sys.stderr)
                status[str(ano)] = {"ano": ano, "ok": False, "erro": f"arquivo ausente: {csv_path}", "url": URL_ZIP.format(ano=ano), "espelho": args.espelho}
                continue
        status[str(ano)] = processar_ano(ano, csv_path, args.espelho) | {"verificado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        gravar_json(status_path, status)  # grava a cada ano para não perder o registro se interrompido
    return 0 if all(status[str(a)]["ok"] for a in anos) else 1


if __name__ == "__main__":
    sys.exit(main())
