"""Testes do banco de questões: schema, unicidade, coerência e verificação SymPy das curadas."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fetch_inep_itens import FAIXAS, normalizar_cor, normalizar_parametro
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
def stats():
    return _ler(RAIZ / "data" / "stats.json")


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


def test_assuntos_habilidade_competencia_coerentes(questoes, taxonomia, matriz, stats):
    comp_de = {h["id"]: h["competencia"] for h in matriz["habilidades"]}
    lim = stats["limiares_dificuldade"]
    assert lim["facil_max"] < lim["media_max"]
    for q in questoes.values():
        assert set(q["assuntos"]) <= set(taxonomia), q["id"]
        if q["habilidade"]:
            assert q["competencia"] == comp_de[q["habilidade"]], q["id"]
        else:
            assert q["competencia"] is None
        assert (q["tri"] is None) == (q["dificuldade_estimada"] is None), q["id"]
        if q["tri"]:
            b = q["tri"]["b"]
            esperado = "facil" if b < lim["facil_max"] else "media" if b < lim["media_max"] else "dificil"
            assert q["dificuldade_estimada"] == esperado, q["id"]


# ------------------------------------------------------------------ microdados do INEP (TRI, gabarito, casamento)
def test_parametros_tri_dentro_das_faixas_plausiveis(questoes):
    for q in questoes.values():
        if not q["tri"]:
            continue
        a, b, c = q["tri"]["a"], q["tri"]["b"], q["tri"]["c"]
        assert 0 < a <= 6, f"{q['id']}: a={a}"
        assert -6 <= b <= 6, f"{q['id']}: b={b}"
        assert 0 <= c < 1, f"{q['id']}: c={c}"
        assert q["tri"]["fonte"].startswith(f"INEP, microdados do ENEM {q['ano']} (ITENS_PROVA)"), q["id"]
        assert isinstance(q["tri"]["corrigido"], bool)


def test_decimal_corrigido_so_onde_o_espelho_estava_quebrado(questoes, stats):
    """A correção de decimal (141.931 → 1.41931) só ocorreu em 2009; nos outros anos nenhum valor foi alterado."""
    corrigidos = {q["ano"] for q in questoes.values() if q["tri"] and q["tri"]["corrigido"]}
    assert corrigidos <= {2009}, corrigidos
    for q in questoes.values():
        if q["tri"] and q["tri"]["corrigido"]:
            assert any("decimal quebrado" in o for o in q["qualidade"]["observacoes"]), q["id"]
    assert stats["totais"]["n_tri_corrigidos"] == sum(1 for q in questoes.values() if q["tri"] and q["tri"]["corrigido"])


@pytest.mark.parametrize(
    "nome, bruto, esperado",
    [
        ("a", "141.931", (1.41931, True)),    # decimal quebrado do espelho → corrigido
        ("b", "250.064", (2.50064, True)),
        ("a", "24.516", (2.4516, True)),      # trailing zero perdido: 2.4516(0)
        ("b", "-0.35276", (-0.35276, False)), # negativo na faixa → intacto
        ("a", "0.70844", (0.70844, False)),
        ("b", "17.62443", (None, False)),     # legítimo do INEP, mas implausível e sem padrão de milhar → descartado
        ("a", "8.33058", (None, False)),
        ("a", "6.20439", (None, False)),
        ("c", "1.2", (None, False)),
        ("b", "", (None, False)),             # ausente
        ("b", None, (None, False)),
    ],
)
def test_normalizar_parametro(nome, bruto, esperado):
    valor, corrigido, problema = normalizar_parametro(nome, bruto)
    assert (valor, corrigido) == esperado
    if valor is None and bruto:
        assert problema and "fora da faixa" in problema
    else:
        assert problema is None


def test_normalizar_cor():
    assert normalizar_cor("Azul") == normalizar_cor("AZUL") == "AZUL"
    assert normalizar_cor("Amarela") == "AMARELA"
    assert normalizar_cor("LARANJA - BRAILE") == "LARANJA - BRAILE"
    assert FAIXAS == {"a": (0.0, 6.0), "b": (-6.0, 6.0), "c": (0.0, 1.0)}


def test_casamento_inep_por_ano(stats, questoes):
    for ano, s in stats["anos"].items():
        i = s["inep"]
        assert i["disponivel"], ano
        assert i["casado"], f"{ano}: {i['observacao']}"
        assert i["cor"] == "AZUL", ano
        assert i["taxa_gabarito"] >= 0.90, ano
        assert i["n_divergentes"] == len(i["divergencias"]), ano
        assert i["deslocamento_posicao"] == (135 if ano == "2017" else 0), ano
        assert i["n_com_tri"] == sum(1 for q in questoes.values() if q["ano"] == int(ano) and q["tri"]), ano
        assert "Zenodo record 18801899" in i["fonte"], ano


def test_gabarito_oficial_prevalece(questoes, stats):
    divergentes = {d["id"]: d for s in stats["anos"].values() for d in s["inep"]["divergencias"]}
    assert divergentes, "esperava ao menos uma divergência enem.dev × INEP registrada"
    for q in questoes.values():
        assert q["gabarito_fonte"] in {"inep", "transcricao"}
        if q["tri"]:
            assert q["gabarito_fonte"] == "inep", q["id"]
        if q["gabarito_fonte"] == "transcricao":
            # só quando o INEP não tem gabarito comparável (item anulado) ou a posição não casou
            assert q["anulada"] or any("posição não encontrada" in o for o in q["qualidade"]["observacoes"]), q["id"]
        if q["id"] in divergentes:
            assert q["gabarito"] == divergentes[q["id"]]["inep"], q["id"]
            assert any("prevalece o INEP" in o for o in q["qualidade"]["observacoes"]), q["id"]
    for q in questoes.values():
        if q["anulada"]:
            assert q["gabarito_fonte"] == "transcricao", q["id"]
            assert q["tri"] is None, q["id"]


def test_gabaritos_antes_suspeitos_resolvidos_pelo_inep(questoes):
    q = questoes["enem-2020-140"]
    assert (q["gabarito"], q["gabarito_fonte"]) == ("C", "inep")
    # a transcrição trazia "1 caixa do tipo B" na alternativa C; a prova oficial tem 2 (18 peças, R$ 159,00)
    assert next(a for a in q["alternativas"] if a["letra"] == "C")["texto"] == "3 caixas do tipo A e 2 caixas do tipo B."
    assert any("transcrição corrigida" in o for o in q["qualidade"]["observacoes"])
    q = questoes["enem-2022-145"]
    assert (q["gabarito"], q["gabarito_fonte"]) == ("E", "inep")


def test_habilidade_oficial_do_inep(questoes, stats):
    for q in questoes.values():
        if q["habilidade_origem"] == "inep":
            assert q["habilidade"] and q["fonte"]["microdados_url"] and q["fonte"]["microdados_espelho_url"], q["id"]
    assert stats["totais"]["habilidade_origem"].get("inep", 0) >= 0.95 * len(questoes)


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
    # trilha fáceis-primeiro: quem tem b vem antes de quem não tem, e b é não decrescente
    com_b = [c["b"] for c in curadas if c["b"] is not None]
    assert com_b == sorted(com_b)
    assert all(c["b"] is None for c in curadas[len(com_b):])
    stats = _ler(RAIZ / "data" / "stats.json")
    assert stats["totais"]["n_questoes"] == len(questoes)
    assert stats["totais"]["n_curadas"] == len(resolucoes)
