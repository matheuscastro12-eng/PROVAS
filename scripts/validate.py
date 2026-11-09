"""Valida os dados gerados contra os schemas e regras de consistência.

Regras:
  - cada questão em data/questoes/matematica/*.json valida contra schema/questao.schema.json
  - ids únicos no banco inteiro e coerentes com ano/numero
  - gabarito ∈ letras das alternativas
  - assuntos ∈ taxonomia/assuntos.json; habilidade/competência ∈ matriz-mt.json e coerentes
  - cada resolução em data/resolucoes/*.json valida contra schema/resolucao.schema.json,
    aponta para uma questão existente e tem gabarito igual ao da questão
  - executa o codigo_sympy de cada resolução e confere resultado_esperado (use --sem-sympy para pular)
  - index.json, curadas.json e stats.json coerentes com as questões

Uso: uv run python scripts/validate.py [--sem-sympy]
"""
from __future__ import annotations

import argparse
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from comum import DIR_DATA, DIR_QUESTOES, DIR_RESOLUCOES, DIR_SCHEMA, DIR_TAXONOMIA, ler_json
from verificar_sympy import executar_verificacao


def carregar_validadores() -> tuple[Draft202012Validator, Draft202012Validator]:
    sq = ler_json(DIR_SCHEMA / "questao.schema.json")
    sr = ler_json(DIR_SCHEMA / "resolucao.schema.json")
    registro = Registry().with_resources(
        [(sq["$id"], Resource.from_contents(sq)), (sr["$id"], Resource.from_contents(sr)),
         ("https://github.com/matheuscastro12-eng/PROVAS/schema/resolucao.schema.json", Resource.from_contents(sr))]
    )
    return Draft202012Validator(sq, registry=registro), Draft202012Validator(sr, registry=registro)


def validar(com_sympy: bool = True) -> list[str]:
    erros: list[str] = []
    vq, vr = carregar_validadores()
    tax = ler_json(DIR_TAXONOMIA / "assuntos.json")
    ids_assuntos = {a["id"] for a in tax["assuntos"]}
    matriz = ler_json(DIR_TAXONOMIA / "matriz-mt.json")
    comp_de = {h["id"]: h["competencia"] for h in matriz["habilidades"]}
    if len(matriz["habilidades"]) != 30 or len(matriz["competencias"]) != 7:
        erros.append("matriz-mt.json deve ter 30 habilidades e 7 competências")

    questoes: dict[str, dict] = {}
    for arq in sorted(DIR_QUESTOES.glob("*.json")):
        ano = int(arq.stem)
        for q in ler_json(arq):
            for e in vq.iter_errors(q):
                erros.append(f"{arq.name} {q.get('id')}: schema: {e.message[:200]}")
            if q["id"] in questoes:
                erros.append(f"id duplicado: {q['id']}")
            questoes[q["id"]] = q
            if q["id"] != f"enem-{q['ano']}-{q['numero']}" or q["ano"] != ano:
                erros.append(f"{q['id']}: id incoerente com ano/numero/arquivo")
            letras = {a["letra"] for a in q["alternativas"]}
            if q["gabarito"] not in letras:
                erros.append(f"{q['id']}: gabarito {q['gabarito']} não está nas alternativas {sorted(letras)}")
            if len(letras) != len(q["alternativas"]):
                erros.append(f"{q['id']}: letras repetidas nas alternativas")
            for a in q["assuntos"]:
                if a not in ids_assuntos:
                    erros.append(f"{q['id']}: assunto desconhecido '{a}'")
            if q["habilidade"] and comp_de.get(q["habilidade"]) != q["competencia"]:
                erros.append(f"{q['id']}: competência {q['competencia']} não corresponde a {q['habilidade']}")
            if (q["tri"] is None) != (q["dificuldade_estimada"] is None):
                erros.append(f"{q['id']}: tri e dificuldade_estimada devem ser ambos null ou ambos preenchidos")
            if "resolucao" in q and q["classificacao"] != "revisada":
                erros.append(f"{q['id']}: questão com resolução deve ter classificacao 'revisada'")

    for arq in sorted(DIR_RESOLUCOES.glob("*.json")):
        r = ler_json(arq)
        for e in vr.iter_errors(r):
            erros.append(f"{arq.name}: schema: {e.message[:200]}")
        if r.get("id") != arq.stem:
            erros.append(f"{arq.name}: id '{r.get('id')}' difere do nome do arquivo")
        q = questoes.get(arq.stem)
        if q is None:
            erros.append(f"{arq.name}: não existe questão com esse id")
            continue
        if r["gabarito"] != q["gabarito"]:
            erros.append(f"{arq.name}: gabarito da resolução ({r['gabarito']}) difere da questão ({q['gabarito']})")
        if r["verificacao"].get("alternativa_esperada", r["gabarito"]) != q["gabarito"]:
            erros.append(f"{arq.name}: alternativa_esperada difere do gabarito")
        for a in r["assuntos"]:
            if a not in ids_assuntos:
                erros.append(f"{arq.name}: assunto desconhecido '{a}'")
        if com_sympy:
            ok, detalhe = executar_verificacao(r["verificacao"])
            if not ok:
                erros.append(f"{arq.name}: verificação SymPy falhou: {detalhe}")

    indice = ler_json(DIR_DATA / "index.json")
    if {i["id"] for i in indice} != set(questoes):
        erros.append("index.json não bate com as questões (rode build.py)")
    curadas = ler_json(DIR_DATA / "curadas.json")["questoes"]
    ids_cur = [c["id"] for c in curadas]
    if set(ids_cur) != {q["id"] for q in questoes.values() if "resolucao" in q}:
        erros.append("curadas.json não bate com as questões que têm resolução (rode build.py)")
    if [c["ordem"] for c in curadas] != list(range(1, len(curadas) + 1)):
        erros.append("curadas.json: campo ordem fora de sequência")
    stats = ler_json(DIR_DATA / "stats.json")
    if stats["totais"]["n_questoes"] != len(questoes):
        erros.append("stats.json desatualizado (rode build.py)")
    return erros


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sem-sympy", action="store_true")
    args = p.parse_args(argv)
    erros = validar(com_sympy=not args.sem_sympy)
    n_q = sum(len(ler_json(a)) for a in DIR_QUESTOES.glob("*.json"))
    n_r = len(list(DIR_RESOLUCOES.glob("*.json")))
    if erros:
        for e in erros:
            print("ERRO:", e)
        print(f"\n{len(erros)} erro(s) em {n_q} questões e {n_r} resoluções")
        return 1
    print(f"OK: {n_q} questões e {n_r} resoluções válidas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
