"""Monta o banco de questões de Matemática do ENEM a partir dos caches.

Entradas (fora do repo, em GABARITA_CACHE):
  enemdev/{ano}.json      — transcrição das questões (fetch_enemdev.py)
  inep/itens_mt_{ano}.json — itens de MT dos microdados do INEP (fetch_inep_itens.py), opcional
Entradas (no repo):
  taxonomia/assuntos.json, taxonomia/matriz-mt.json
  data/resolucoes/{id}.json — curadoria manual (resolução, dicas, erros comuns, verificação SymPy)
  data/correcoes_transcricao.json — erros de digitação da transcrição corrigidos à mão, com evidência

Saídas:
  data/questoes/matematica/{ano}.json — questões completas (schema/questao.schema.json)
  data/index.json   — lista compacta para busca
  data/stats.json   — estatísticas e registro do casamento com os microdados
  data/curadas.json — trilha inicial: questões curadas ordenadas por dificuldade

Uso: uv run python scripts/build.py [anos...]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict

from comum import ANOS_PADRAO, DIR_CACHE_ENEMDEV, DIR_CACHE_INEP, DIR_DATA, DIR_QUESTOES, DIR_RESOLUCOES, DIR_TAXONOMIA, gravar_json, ler_json

URL_PROVAS_INEP = "https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enem/provas-e-gabaritos"
URL_MICRODADOS = "https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip"
INTERVALO_MT = (136, 180)  # numeração de Matemática no 2º dia (caderno azul) desde 2009
LIMIAR_CASAMENTO = 0.90    # fração mínima de gabaritos coincidentes para aceitar o casamento INEP↔enem.dev
MAX_ASSUNTOS = 3
# Limiares de dificuldade usados quando o banco ainda não tem b suficiente para calcular tercis.
LIMIARES_PADRAO = {"facil_max": 0.5, "media_max": 1.5}
MIN_B_PARA_TERCIS = 90


# ---------------------------------------------------------------- utilidades de texto
def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", t)


def dificuldade_por_b(b: float | None, limiares: dict) -> str | None:
    """facil se b < facil_max; media se facil_max ≤ b < media_max; dificil se b ≥ media_max."""
    if b is None:
        return None
    if b < limiares["facil_max"]:
        return "facil"
    if b < limiares["media_max"]:
        return "media"
    return "dificil"


def tercis_de_b(valores: list[float]) -> dict:
    """Limiares de dificuldade = tercis do parâmetro b das questões de MT do banco (arredondados a 2 casas).
    Com poucos valores, cai nos limiares padrão."""
    bs = sorted(valores)
    if len(bs) < MIN_B_PARA_TERCIS:
        return dict(LIMIARES_PADRAO, metodo="limiares padrão (poucas questões com TRI para calcular tercis)")
    t1 = bs[len(bs) // 3]
    t2 = bs[(2 * len(bs)) // 3]
    return {"facil_max": round(t1, 2), "media_max": round(t2, 2), "metodo": f"tercis de tri.b das {len(bs)} questões de MT com TRI no banco", "n": len(bs)}


# ---------------------------------------------------------------- taxonomia
class Taxonomia:
    def __init__(self) -> None:
        self.assuntos = ler_json(DIR_TAXONOMIA / "assuntos.json")["assuntos"]
        matriz = ler_json(DIR_TAXONOMIA / "matriz-mt.json")
        self.competencia_de = {h["id"]: h["competencia"] for h in matriz["habilidades"]}
        self.ids = {a["id"] for a in self.assuntos}
        self._kw = {a["id"]: [normalizar(k) for k in a["palavras_chave"]] for a in self.assuntos}

    def classificar(self, texto: str, habilidade: str | None) -> list[str]:
        """Heurística: pontua cada assunto por palavras-chave (com peso para termos longos)
        e dá bônus quando a habilidade oficial está entre as do assunto."""
        t = normalizar(texto)
        pontos: dict[str, float] = {}
        for a in self.assuntos:
            s = 0.0
            for k in self._kw[a["id"]]:
                n = len(re.findall(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z])", t)) if k.isalnum() or " " in k else t.count(k)
                if n:
                    s += (1.0 if len(k) <= 3 else 1.0 + 0.15 * len(k.split())) * min(n, 3)
            if habilidade and habilidade in a["habilidades"]:
                s += 1.5 if s else 0.75
            if s:
                pontos[a["id"]] = s
        if not pontos:
            return []
        ordenados = sorted(pontos.items(), key=lambda kv: -kv[1])
        melhor = ordenados[0][1]
        return [k for k, v in ordenados[:MAX_ASSUNTOS] if v >= max(1.0, 0.4 * melhor)]

    def habilidade_heuristica(self, assuntos: list[str]) -> str | None:
        for a in self.assuntos:
            if assuntos and a["id"] == assuntos[0]:
                return a["habilidades"][0]
        return None


# ---------------------------------------------------------------- enem.dev → schema
def normalizar_questoes_enemdev(ano: int, brutas: list[dict], stats: dict) -> list[dict]:
    por_numero: dict[int, dict] = {}
    descartadas = []
    for q in brutas:
        n = q["index"]
        if not (INTERVALO_MT[0] <= n <= INTERVALO_MT[1]):
            descartadas.append({"numero": n, "motivo": "fora do intervalo 136–180 (provável erro de disciplina na transcrição)"})
            continue
        if n in por_numero:
            atual = por_numero[n]
            if (q.get("context") or "") == (atual.get("context") or ""):
                descartadas.append({"numero": n, "motivo": "duplicata idêntica na API"})
                continue
            # mantém a versão com mais texto
            if len(q.get("context") or "") <= len(atual.get("context") or ""):
                descartadas.append({"numero": n, "motivo": "duplicata com menos texto"})
                continue
            descartadas.append({"numero": n, "motivo": "duplicata com menos texto (versão anterior)"})
        por_numero[n] = q
    stats["descartadas_enemdev"] = descartadas

    questoes = []
    for n in sorted(por_numero):
        q = por_numero[n]
        contexto = (q.get("context") or "").strip()
        comando = (q.get("alternativesIntroduction") or "").strip()
        enunciado = "\n\n".join(p for p in (contexto, comando) if p)
        imagens = list(q.get("files") or [])
        for url in re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", contexto):
            if url not in imagens:
                imagens.append(url)
        alternativas = []
        for alt in q["alternatives"]:
            alternativas.append({"letra": alt["letter"], "texto": (alt.get("text") or "").strip(), "imagem": alt.get("file")})
        depende_img = bool(imagens) or any(a["imagem"] for a in alternativas)
        questoes.append(
            {
                "id": f"enem-{ano}-{n}",
                "ano": ano,
                "dia": 2,
                "caderno": "azul",
                "numero": n,
                "area": "matematica",
                "enunciado": enunciado,
                "imagens": imagens,
                "alternativas": alternativas,
                "gabarito": q["correctAlternative"],
                "gabarito_fonte": "transcricao",
                "anulada": False,
                "habilidade": None,
                "habilidade_origem": None,
                "competencia": None,
                "assuntos": [],
                "classificacao": "heuristica",
                "tri": None,
                "dificuldade_estimada": None,
                "fonte": {
                    "orgao": "INEP",
                    "prova": f"ENEM {ano}, 2º dia, caderno azul (aplicação regular), questão {n}",
                    "url_oficial": URL_PROVAS_INEP,
                    "transcricao": "enem.dev",
                    "transcricao_url": f"https://api.enem.dev/v1/exams/{ano}/questions/{n}",
                    "microdados_url": None,
                    "microdados_espelho_url": None,
                },
                "qualidade": {
                    "enunciado_vazio": not contexto,
                    "alternativas_incompletas": len(alternativas) < 5,
                    "depende_de_imagem": depende_img,
                    "observacoes": [],
                },
            }
        )
    return questoes


# ---------------------------------------------------------------- correções manuais de transcrição
def aplicar_correcoes_transcricao(questoes: list[dict], stats: dict) -> None:
    """Aplica data/correcoes_transcricao.json (erros de digitação da enem.dev com evidência documentada).
    Só altera texto (enunciado/alternativas); o gabarito vem do INEP em casar_inep."""
    caminho = DIR_DATA / "correcoes_transcricao.json"
    aplicadas = []
    if not caminho.exists():
        stats["correcoes_transcricao"] = aplicadas
        return
    por_id = {q["id"]: q for q in questoes}
    for c in ler_json(caminho)["correcoes"]:
        q = por_id.get(c["id"])
        if q is None:
            continue
        partes = c["campo"].split(".")
        if partes[0] == "alternativas" and len(partes) == 3:
            alvo = next((a for a in q["alternativas"] if a["letra"] == partes[1]), None)
            chave = partes[2]
        elif partes == ["enunciado"]:
            alvo, chave = q, "enunciado"
        else:
            raise ValueError(f"correção com campo desconhecido: {c['campo']}")
        if alvo is None or alvo.get(chave) != c["de"]:
            raise ValueError(f"{c['id']}: texto atual de {c['campo']} não é o esperado pela correção ({alvo.get(chave) if alvo else None!r})")
        alvo[chave] = c["para"]
        q["qualidade"]["observacoes"].append(f"transcrição corrigida em {c['campo']}: {c['de']!r} → {c['para']!r}. Motivo: {c['motivo']}")
        aplicadas.append({"id": c["id"], "campo": c["campo"]})
    stats["correcoes_transcricao"] = aplicadas


# ---------------------------------------------------------------- INEP ↔ enem.dev
def casar_inep(ano: int, questoes: list[dict], stats: dict) -> None:
    """Escolhe o caderno AZUL da aplicação regular cujo gabarito melhor bate com a transcrição
    e, se bater em ≥ 90% dos itens, copia TRI, habilidade, gabarito oficial e flag de anulação.

    Cores vêm normalizadas do cache ('Azul'/'AZUL' → 'AZUL'). Em 2017 os microdados numeram
    Matemática de 1 a 45; o deslocamento (+135) é detectado e registrado. Empates entre cadernos
    azuis (reaplicação, versão digital) são resolvidos a favor do não digital de menor CO_PROVA.
    """
    caminho = DIR_CACHE_INEP / f"itens_mt_{ano}.json"
    registro = {
        "disponivel": caminho.exists(), "fonte": None, "casado": False, "co_prova": None, "cor": None, "deslocamento_posicao": 0,
        "n_comparaveis": 0, "taxa_gabarito": None, "n_divergentes": 0, "divergencias": [], "n_com_tri": 0, "n_tri_corrigidos": 0,
        "n_tri_descartados": 0, "n_anuladas": 0, "n_habilidade_inep": 0, "observacao": None,
    }
    stats["inep"] = registro
    if not caminho.exists():
        registro["observacao"] = "microdados do INEP não disponíveis no cache (download falhou ou não foi executado); tri = null"
        return
    dados = ler_json(caminho)
    registro["fonte"] = dados.get("fonte")
    por_numero = {q["numero"]: q for q in questoes}
    candidatos: dict[str, list[dict]] = defaultdict(list)
    for it in dados["itens"]:
        candidatos[it["co_prova"]].append(it)
    melhor = None
    for co_prova, itens in candidatos.items():
        posicoes = {it["posicao"] for it in itens}
        # 2017: microdados numeram MT de 1 a 45 → desloca para 136–180
        desloc = INTERVALO_MT[0] - 1 if max(posicoes) <= INTERVALO_MT[1] - INTERVALO_MT[0] + 1 else 0
        pos = {}
        for it in itens:
            pos.setdefault(it["posicao"] + desloc, it)  # cadernos com posição repetida (ledor) ficam com o 1º
        comparaveis = [(n, q) for n, q in por_numero.items() if n in pos and not pos[n]["anulado"] and pos[n]["gabarito"] in "ABCDE"]
        if not comparaveis:
            continue
        acertos = sum(1 for n, q in comparaveis if pos[n]["gabarito"] == q["gabarito"])
        taxa = acertos / len(comparaveis)
        cor = itens[0]["cor"]
        digital = any(it.get("versao_digital") for it in itens)
        chave = (cor == "AZUL", taxa, len(comparaveis), not digital, -int(co_prova) if co_prova.isdigit() else 0)
        if melhor is None or chave > melhor[0]:
            melhor = (chave, co_prova, cor, taxa, pos, len(comparaveis) - acertos, desloc, len(comparaveis))
    if melhor is None:
        registro["observacao"] = "nenhum caderno comparável"
        return
    _, co_prova, cor, taxa, pos, divergentes, desloc, n_comp = melhor
    registro.update(co_prova=co_prova, cor=cor, taxa_gabarito=round(taxa, 4), n_divergentes=divergentes, deslocamento_posicao=desloc, n_comparaveis=n_comp)
    if taxa < LIMIAR_CASAMENTO:
        registro["observacao"] = f"gabarito do caderno {co_prova} ({cor}) bateu em só {taxa:.0%} dos itens (<{LIMIAR_CASAMENTO:.0%}); casamento descartado, tri = null"
        return
    registro["casado"] = True
    fonte_tri = dados.get("fonte") or f"INEP, microdados do ENEM {ano} (ITENS_PROVA)"
    for n, q in sorted(por_numero.items()):
        it = pos.get(n)
        if not it:
            q["qualidade"]["observacoes"].append("posição não encontrada nos microdados do INEP")
            continue
        q["anulada"] = bool(it["anulado"])
        registro["n_anuladas"] += int(q["anulada"])
        if it["habilidade"]:
            q["habilidade"] = f"H{it['habilidade']}"
            q["habilidade_origem"] = "inep"
            registro["n_habilidade_inep"] += 1
        if it["gabarito"] in "ABCDE" and not it["anulado"]:
            if it["gabarito"] != q["gabarito"]:
                q["qualidade"]["observacoes"].append(
                    f"gabarito da transcrição enem.dev ({q['gabarito']}) difere do TX_GABARITO oficial do INEP ({it['gabarito']}); prevalece o INEP"
                )
                registro["divergencias"].append({"id": q["id"], "transcricao": q["gabarito"], "inep": it["gabarito"]})
                q["gabarito"] = it["gabarito"]
            q["gabarito_fonte"] = "inep"
        elif it["anulado"]:
            q["qualidade"]["observacoes"].append("item anulado pelo INEP (IN_ITEM_ABAN=1); gabarito mantido da transcrição")
        if it["a"] is not None and it["b"] is not None and it["c"] is not None:
            q["tri"] = {"a": it["a"], "b": it["b"], "c": it["c"], "corrigido": bool(it.get("tri_corrigido")), "fonte": fonte_tri}
            registro["n_com_tri"] += 1
            registro["n_tri_corrigidos"] += int(bool(it.get("tri_corrigido")))
            if it.get("tri_corrigido"):
                q["qualidade"]["observacoes"].append(
                    "parâmetros TRI do espelho tinham o decimal quebrado (ex.: a=" + str((it.get("tri_bruto") or {}).get("a")) + "); corrigidos pela reinserção do ponto após o primeiro dígito"
                )
        elif it.get("tri_descartado"):
            registro["n_tri_descartados"] += 1
            q["qualidade"]["observacoes"].append(f"parâmetros TRI descartados: {it['tri_descartado']}")
        q["fonte"]["microdados_url"] = URL_MICRODADOS.format(ano=ano)
        q["fonte"]["microdados_espelho_url"] = dados.get("url_espelho")
    registro["observacao"] = f"caderno {co_prova} ({cor}) casado: gabarito bateu em {taxa:.0%} de {n_comp} itens comparáveis"


# ---------------------------------------------------------------- curadoria
def aplicar_resolucoes(questoes: list[dict], tax: Taxonomia, stats: dict) -> None:
    n = 0
    for q in questoes:
        caminho = DIR_RESOLUCOES / f"{q['id']}.json"
        if not caminho.exists():
            continue
        r = ler_json(caminho)
        if r["gabarito"] != q["gabarito"]:
            q["qualidade"]["observacoes"].append(f"curadoria indica gabarito {r['gabarito']}, transcrição/INEP {q['gabarito']}")
        q["assuntos"] = list(r["assuntos"])
        q["classificacao"] = "revisada"
        if q["habilidade_origem"] != "inep":
            q["habilidade"] = r["habilidade"]
            q["habilidade_origem"] = "revisada"
        q["resolucao"] = r
        n += 1
    stats["n_curadas"] = n


def ordem_curada(q: dict) -> tuple:
    b = (q.get("tri") or {}).get("b")
    nivel = q["resolucao"].get("nivel_curador", 3)
    # com TRI, ordena por b; sem TRI, pelo nível atribuído na curadoria (1 = mais fácil)
    return (0, b, nivel) if b is not None else (1, nivel, q["ano"], q["numero"])


# ---------------------------------------------------------------- principal
def construir(anos: list[int]) -> dict:
    tax = Taxonomia()
    stats_total = {
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fontes": {
            "texto": "INEP (provas oficiais do ENEM), transcrição comunitária via https://api.enem.dev/v1",
            "tri_habilidade": "INEP, microdados do ENEM (ITENS_PROVA_{ano}.csv); CSVs obtidos do espelho público Zenodo record 18801899 (https://zenodo.org/records/18801899)",
            "matriz": "INEP, Matriz de Referência do ENEM",
        },
        "anos": {},
        "totais": {},
    }
    todas: list[dict] = []
    for ano in anos:
        caminho = DIR_CACHE_ENEMDEV / f"{ano}.json"
        if not caminho.exists():
            print(f"{ano}: sem cache do enem.dev, pulando (rode fetch_enemdev.py)", file=sys.stderr)
            continue
        stats = {}
        questoes = normalizar_questoes_enemdev(ano, ler_json(caminho)["questoes_matematica"], stats)
        aplicar_correcoes_transcricao(questoes, stats)
        casar_inep(ano, questoes, stats)
        for q in questoes:
            texto = q["enunciado"] + " " + " ".join(a["texto"] for a in q["alternativas"])
            q["assuntos"] = tax.classificar(texto, q["habilidade"] if q["habilidade_origem"] == "inep" else None)
            if q["habilidade"] is None:
                h = tax.habilidade_heuristica(q["assuntos"])
                if h:
                    q["habilidade"], q["habilidade_origem"] = h, "heuristica"
        aplicar_resolucoes(questoes, tax, stats)
        for q in questoes:
            q["competencia"] = tax.competencia_de.get(q["habilidade"]) if q["habilidade"] else None
        stats.update(
            n_questoes=len(questoes),
            n_com_tri=sum(1 for q in questoes if q["tri"]),
            n_com_imagem=sum(1 for q in questoes if q["qualidade"]["depende_de_imagem"]),
            n_enunciado_vazio=sum(1 for q in questoes if q["qualidade"]["enunciado_vazio"]),
            n_sem_assunto=sum(1 for q in questoes if not q["assuntos"]),
            numeros_faltantes=[n for n in range(INTERVALO_MT[0], INTERVALO_MT[1] + 1) if n not in {q["numero"] for q in questoes}],
        )
        stats_total["anos"][str(ano)] = stats
        todas.extend(questoes)
        print(f"{ano}: {len(questoes)} questões, {stats['n_com_tri']} com TRI, {stats['n_curadas']} curadas, INEP: {stats['inep']['observacao']}")

    # dificuldade_estimada pelos tercis de b do banco inteiro (só depois de casar todos os anos)
    limiares = tercis_de_b([q["tri"]["b"] for q in todas if q["tri"]])
    stats_total["limiares_dificuldade"] = limiares
    for q in todas:
        q["dificuldade_estimada"] = dificuldade_por_b((q["tri"] or {}).get("b"), limiares)
    for ano in anos:
        do_ano = [q for q in todas if q["ano"] == ano]
        if do_ano:
            gravar_json(DIR_QUESTOES / f"{ano}.json", do_ano)
            stats_total["anos"][str(ano)]["por_dificuldade"] = dict(Counter(q["dificuldade_estimada"] or "sem_tri" for q in do_ano))

    indice = [
        {"id": q["id"], "ano": q["ano"], "numero": q["numero"], "assuntos": q["assuntos"], "habilidade": q["habilidade"],
         "b": (q["tri"] or {}).get("b"), "dificuldade_estimada": q["dificuldade_estimada"], "curada": "resolucao" in q,
         "depende_de_imagem": q["qualidade"]["depende_de_imagem"]}
        for q in todas
    ]
    gravar_json(DIR_DATA / "index.json", indice)

    curadas = sorted((q for q in todas if "resolucao" in q), key=ordem_curada)
    gravar_json(
        DIR_DATA / "curadas.json",
        {
            "descricao": "Trilha inicial do Gabarita: questões reais do ENEM com resolução revisada, ordenadas da mais fácil para a mais difícil (parâmetro b da TRI quando disponível; senão, nível atribuído na curadoria).",
            "ordenacao": "tri.b crescente (questões com TRI primeiro); sem TRI, nivel_curador crescente",
            "limiares_dificuldade": limiares,
            "questoes": [
                {"ordem": i + 1, "id": q["id"], "ano": q["ano"], "numero": q["numero"], "assuntos": q["assuntos"], "habilidade": q["habilidade"],
                 "b": (q["tri"] or {}).get("b"), "dificuldade_estimada": q["dificuldade_estimada"], "nivel_curador": q["resolucao"].get("nivel_curador"),
                 "resumo": q["resolucao"].get("resumo"), "depende_de_imagem": q["qualidade"]["depende_de_imagem"]}
                for i, q in enumerate(curadas)
            ],
        },
    )

    por_assunto = Counter(a for q in todas for a in q["assuntos"])
    por_assunto_curadas = Counter(a for q in curadas for a in q["assuntos"])
    por_hab = Counter(q["habilidade"] for q in todas if q["habilidade"])
    stats_total["totais"] = {
        "anos_cobertos": sorted({q["ano"] for q in todas}),
        "n_questoes": len(todas),
        "n_com_tri": sum(1 for q in todas if q["tri"]),
        "n_curadas": len(curadas),
        "n_com_imagem": sum(1 for q in todas if q["qualidade"]["depende_de_imagem"]),
        "n_enunciado_vazio": sum(1 for q in todas if q["qualidade"]["enunciado_vazio"]),
        "n_sem_assunto": sum(1 for q in todas if not q["assuntos"]),
        "n_anuladas": sum(1 for q in todas if q["anulada"]),
        "n_tri_corrigidos": sum(1 for q in todas if q["tri"] and q["tri"].get("corrigido")),
        "n_divergencias_gabarito": sum(len(s["inep"]["divergencias"]) for s in stats_total["anos"].values()),
        "gabarito_fonte": dict(Counter(q["gabarito_fonte"] for q in todas)),
        "habilidade_origem": dict(Counter(q["habilidade_origem"] or "nenhuma" for q in todas)),
        "por_assunto": dict(por_assunto.most_common()),
        "por_assunto_curadas": dict(por_assunto_curadas.most_common()),
        "por_habilidade": dict(sorted(por_hab.items(), key=lambda kv: int(kv[0][1:]))),
        "por_dificuldade": dict(Counter(q["dificuldade_estimada"] or "sem_tri" for q in todas)),
    }
    gravar_json(DIR_DATA / "stats.json", stats_total)
    return stats_total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("anos", nargs="*", type=int, default=ANOS_PADRAO)
    args = p.parse_args(argv)
    t = construir(args.anos)["totais"]
    print(f"\nTotal: {t['n_questoes']} questões, {t['n_com_tri']} com TRI, {t['n_curadas']} curadas, {t['n_sem_assunto']} sem assunto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
