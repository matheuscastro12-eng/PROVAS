"""Testes do banco de questões: schema, unicidade, coerência e verificação SymPy das curadas."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from verificar_sympy import executar_verificacao

RAIZ = Path(__file__).resolve().parent.parent
DIR_Q = RAIZ / "data" / "questoes" / "matematica"
DIR_R = RAIZ / "data" / "resolucoes"
DIR_S = RAIZ / "schema"
DIR_T = RAIZ / "taxonomia"


def _ler(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def validadores():
    sq = _ler(DIR_S / "questao.schema.json")
    sr = _ler(DIR_S / "resolucao.schema.json")
    reg = Registry().with_resources([(sq["$id"], Resource.from_contents(sq)), (sr["$id"], Resource.from_contents(sr))])
    return Draft202012Validator(sq, registry=reg), Draft202012Validator(sr, registry=reg)


@pytest.fixture(scope="session")
def questoes() -> dict[str, dict]:
    todas = {}
    for arq in sorted(DIR_Q.glob("*.json")):
        for q in _ler(arq):
            todas[q["id"]] = q
    assert todas, "nenhuma questão gerada (rode scripts/build.py)"
    return todas


@pytest.fixture(scope="session")
def resolucoes() -> dict[str, dict]:
    return {p.stem: _ler(p) for p in sorted(DIR_R.glob("*.json"))}


@pytest.fixture(scope="session")
def taxonomia():
    return {a["id"]: a for a in _ler(DIR_T / "assuntos.json")["assuntos"]}


@pytest.fixture(scope="session")
def matriz():
    return _ler(DIR_T / "matriz-mt.json")


# ------------------------------------------------------------------ taxonomia / matriz
def test_matriz_tem_30_habilidades_e_7_competencias(matriz):
    assert [h["id"] for h in matriz["habilidades"]] == [f"H{i}" for i in range(1, 31)]
    assert [c["id"] for c in matriz["competencias"]] == [f"C{i}" for i in range(1, 8)]
    for c in matriz["competencias"]:
        for h in c["habilidades"]:
            assert next(x for x in matriz["habilidades"] if x["id"] == h)["competencia"] == c["id"]


def test_taxonomia_cobre_assuntos_de_foco(taxonomia, matriz):
    habs = {h["id"] for h in matriz["habilidades"]}
    foco = {
        "porcentagem", "razao-proporcao", "regra-de-tres", "grandezas-unidades-escalas", "probabilidade",
        "analise-combinatoria", "estatistica-basica", "graficos-tabelas", "funcao-afim", "funcao-quadratica",
        "leitura-grafico-funcao", "equacao-1-grau", "equacao-2-grau", "geometria-plana", "sequencias-pa",
    }
    assert foco <= set(taxonomia)
    for a in taxonomia.values():
        assert a["habilidades"] and set(a["habilidades"]) <= habs, a["id"]
        assert a["descricao"].strip()


# ------------------------------------------------------------------ questões
def test_questoes_validam_contra_schema(validadores, questoes):
    vq, _ = validadores
    erros = [f"{q['id']}: {e.message}" for q in questoes.values() for e in vq.iter_errors(q)]
    assert not erros, "\n".join(erros[:20])


def test_ids_unicos_e_coerentes():
    vistos = []
    for arq in sorted(DIR_Q.glob("*.json")):
        for q in _ler(arq):
            vistos.append(q["id"])
            assert q["id"] == f"enem-{q['ano']}-{q['numero']}"
            assert q["ano"] == int(arq.stem)
    assert len(vistos) == len(set(vistos)), "ids duplicados"


def test_gabarito_pertence_as_alternativas(questoes):
    for q in questoes.values():
        letras = [a["letra"] for a in q["alternativas"]]
        assert len(letras) == len(set(letras)), q["id"]
        assert q["gabarito"] in letras, q["id"]


def test_assuntos_habilidade_competencia_coerentes(questoes, taxonomia, matriz):
    comp_de = {h["id"]: h["competencia"] for h in matriz["habilidades"]}
    for q in questoes.values():
        assert set(q["assuntos"]) <= set(taxonomia), q["id"]
        if q["habilidade"]:
            assert q["competencia"] == comp_de[q["habilidade"]], q["id"]
        else:
            assert q["competencia"] is None
        assert (q["tri"] is None) == (q["dificuldade_estimada"] is None), q["id"]
        if q["tri"]:
            b = q["tri"]["b"]
            esperado = "facil" if b < 0.5 else "media" if b < 1.5 else "dificil"
            assert q["dificuldade_estimada"] == esperado, q["id"]


# ------------------------------------------------------------------ curadas
def test_quantidade_de_curadas(resolucoes):
    assert 40 <= len(resolucoes) <= 60, len(resolucoes)


def test_curadas_cobrem_todos_os_assuntos_de_foco(resolucoes, taxonomia):
    foco = {a for a, d in taxonomia.items() if d["foco_inicial"]}
    cobertos = {a for r in resolucoes.values() for a in r["assuntos"]}
    assert foco <= cobertos, f"assuntos de foco sem curadas: {sorted(foco - cobertos)}"


def test_resolucoes_validam_contra_schema(validadores, resolucoes):
    _, vr = validadores
    erros = [f"{rid}: {e.message}" for rid, r in resolucoes.items() for e in vr.iter_errors(r)]
    assert not erros, "\n".join(erros[:20])


def test_resolucoes_apontam_para_questoes_e_gabarito_bate(resolucoes, questoes):
    for rid, r in resolucoes.items():
        assert r["id"] == rid
        assert rid in questoes, f"resolução {rid} sem questão"
        q = questoes[rid]
        assert r["gabarito"] == q["gabarito"], rid
        assert q["classificacao"] == "revisada", rid
        assert q.get("resolucao", {}).get("id") == rid, "build.py não incorporou a resolução"
        assert r["verificacao"].get("alternativa_esperada", r["gabarito"]) == q["gabarito"]
        letras_distratores = {e["alternativa"] for e in r["erros_comuns"]}
        assert r["gabarito"] not in letras_distratores, f"{rid}: erro comum apontando para o gabarito"
        assert len(letras_distratores) >= 3, f"{rid}: explique ao menos 3 distratores"
        assert "$" in r["resolucao"], f"{rid}: resolução sem LaTeX"


@pytest.mark.parametrize("rid", [p.stem for p in sorted(DIR_R.glob("*.json"))])
def test_codigo_sympy_confere_com_gabarito(rid, resolucoes, questoes):
    r = resolucoes[rid]
    ok, detalhe = executar_verificacao(r["verificacao"])
    assert ok, f"{rid}: {detalhe}"
    # o resultado verificado corresponde à alternativa do gabarito oficial
    assert r["verificacao"].get("alternativa_esperada", r["gabarito"]) == questoes[rid]["gabarito"]


# ------------------------------------------------------------------ índices
def test_index_curadas_e_stats_coerentes(questoes, resolucoes):
    indice = _ler(RAIZ / "data" / "index.json")
    assert {i["id"] for i in indice} == set(questoes)
    curadas = _ler(RAIZ / "data" / "curadas.json")["questoes"]
    assert {c["id"] for c in curadas} == set(resolucoes)
    assert [c["ordem"] for c in curadas] == list(range(1, len(curadas) + 1))
    stats = _ler(RAIZ / "data" / "stats.json")
    assert stats["totais"]["n_questoes"] == len(questoes)
    assert stats["totais"]["n_curadas"] == len(resolucoes)
