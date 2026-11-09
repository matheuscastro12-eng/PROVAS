# PROVAS — banco de questões de Matemática do ENEM (Gabarita)

Banco de questões objetivas de **Matemática e suas Tecnologias** do ENEM (2009–2023) usado pelo app **Gabarita**, a IDE agêntica de estudo para o ENEM. Cada questão vem com metadados pedagógicos (habilidade e competência da Matriz de Referência, assuntos de uma taxonomia própria, gabarito oficial, parâmetros TRI quando publicados) e, para a trilha inicial do tutor, uma curadoria com resolução passo a passo, dicas em três níveis, análise dos distratores e verificação em SymPy.

Somente material público e oficial do INEP, sempre com a fonte citada. Tudo em pt-BR.

## Fontes e direitos

| O quê | Fonte | Como citamos |
|---|---|---|
| Texto das questões, alternativas, imagens e gabarito | Provas oficiais do ENEM (INEP), transcritas pela comunidade em [enem.dev](https://enem.dev) e servidas pela API pública `https://api.enem.dev/v1` | `fonte.orgao = "INEP"`, `fonte.prova = "ENEM {ano}, 2º dia, caderno azul (aplicação regular), questão {n}"`, `fonte.url_oficial` (página de provas e gabaritos do INEP) e `fonte.transcricao_url` (URL da questão na enem.dev) |
| Parâmetros TRI (a, b, c), habilidade oficial e itens anulados | Microdados do ENEM (INEP): `ITENS_PROVA_{ano}.csv` dentro de `https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip` | `fonte.microdados_url` e `tri` (ver limitação abaixo) |
| Matriz de Referência (7 competências, 30 habilidades) | INEP, *Matriz de Referência ENEM* (`enem_matriz_de_referencia_v1.pdf`) | `taxonomia/matriz-mt.json` reproduz o texto oficial |

As provas do ENEM são documentos públicos do INEP/MEC. A transcrição da enem.dev é um projeto comunitário aberto; mantemos a atribuição em cada questão. As resoluções, dicas, taxonomia e código deste repositório são obra própria.

## Estrutura

```
schema/
  questao.schema.json      JSON Schema (draft 2020-12) de uma questão
  resolucao.schema.json    JSON Schema de uma resolução curada
taxonomia/
  matriz-mt.json           Competências C1–C7 e habilidades H1–H30 de Matemática (texto oficial)
  assuntos.json            24 assuntos (15 de foco inicial), com habilidades, descrição e palavras-chave
scripts/                   Python 3 (uv)
  fetch_enemdev.py         baixa as questões de matemática da API enem.dev para o cache
  fetch_inep_itens.py      baixa os microdados do INEP, extrai só ITENS_PROVA_{ano}.csv e filtra SG_AREA='MT'
  build.py                 casa transcrição × microdados, classifica assuntos, incorpora a curadoria e gera data/
  validate.py              valida schemas, ids, gabaritos, taxonomia e executa as verificações SymPy
  verificar_sympy.py       executa o bloco `verificacao` de uma resolução
  comum.py                 caminhos e utilidades
data/
  questoes/matematica/{ano}.json   questões completas (uma lista por ano)
  index.json               lista compacta: id, ano, numero, assuntos, habilidade, b, dificuldade_estimada, curada
  stats.json               estatísticas e registro do casamento com os microdados, por ano
  curadas.json             trilha inicial: curadas ordenadas da mais fácil para a mais difícil
  resolucoes/{id}.json     curadoria (resolução, dicas, erros comuns, conceitos, verificação SymPy)
tests/                     pytest
```

### Formato de uma questão (resumo)

```jsonc
{
  "id": "enem-2023-162",            // enem-{ano}-{numero do caderno azul}
  "ano": 2023, "dia": 2, "caderno": "azul", "numero": 162, "area": "matematica",
  "enunciado": "… markdown; imagens como ![](url) …",
  "imagens": ["https://enem.dev/…png"],
  "alternativas": [{"letra": "A", "texto": "Y = 250x", "imagem": null}, …],
  "gabarito": "D", "anulada": false,
  "habilidade": "H19", "habilidade_origem": "revisada",   // "inep" | "heuristica" | "revisada"
  "competencia": "C5",
  "assuntos": ["funcao-afim"], "classificacao": "revisada",  // "heuristica" | "revisada"
  "tri": null,                       // {"a","b","c"} quando os microdados do INEP estão disponíveis
  "dificuldade_estimada": null,      // facil (b<0,5) | media (0,5≤b<1,5) | dificil (b≥1,5) | null
  "fonte": {"orgao": "INEP", "prova": "ENEM 2023, 2º dia, caderno azul (aplicação regular), questão 162",
            "url_oficial": "https://www.gov.br/inep/…/provas-e-gabaritos", "transcricao": "enem.dev",
            "transcricao_url": "https://api.enem.dev/v1/exams/2023/questions/162", "microdados_url": null},
  "qualidade": {"enunciado_vazio": false, "alternativas_incompletas": false, "depende_de_imagem": false, "observacoes": []},
  "resolucao": { … }                 // só nas curadas (schema/resolucao.schema.json)
}
```

### Formato de uma resolução curada

`resolucao` (markdown + LaTeX `$…$`, passo a passo) · `dicas.dica1/2/3` (conceitual → caminho → quase a conta) · `erros_comuns[]` (por que cada distrator atrai) · `conceitos[]` · `verificacao.codigo_sympy` (define `resultado`) e `verificacao.resultado_esperado` · `nivel_curador` (1 = mais fácil) · `dados_da_imagem` (transcrição textual de tabela/gráfico quando a questão depende de imagem).

## Como regenerar

Pré-requisitos: Python ≥ 3.11 e [uv](https://docs.astral.sh/uv/). O cache de downloads fica **fora** do repositório, em `/workspace/gabarita/cache` (ou `GABARITA_CACHE`); zips e CSVs brutos do INEP nunca são versionados.

```bash
uv sync                                        # instala requests, sympy, jsonschema, pytest
uv run python scripts/fetch_enemdev.py         # questões 2009–2023 (cache enemdev/{ano}.json)
uv run python scripts/fetch_inep_itens.py      # microdados 2019–2023 → cache inep/itens_mt_{ano}.json
#   ou, com um CSV já baixado:  uv run python scripts/fetch_inep_itens.py 2022 --csv /caminho/ITENS_PROVA_2022.csv
uv run python scripts/build.py                 # gera data/
uv run python scripts/validate.py              # valida tudo (inclui as verificações SymPy)
uv run pytest                                  # testes
```

`build.py` é idempotente: refaça a curadoria editando `data/resolucoes/{id}.json` e rode `build.py` de novo. Para adicionar uma questão à trilha, crie o arquivo de resolução (obedecendo `schema/resolucao.schema.json`) e reconstrua.

### Como o casamento com os microdados funciona

Para cada ano, `build.py` agrupa os itens de MT por `CO_PROVA`, prefere cadernos `TX_COR = AZUL` e escolhe o caderno cujo `TX_GABARITO` mais coincide com o `correctAlternative` da transcrição (posição `CO_POSICAO` = número da questão). O casamento só é aceito se os gabaritos baterem em **≥ 90 %** dos itens comparáveis; caso contrário é descartado e registrado em `data/stats.json` (`anos.{ano}.inep`). Quando aceito, copiam-se `NU_PARAM_A/B/C` → `tri`, `CO_HABILIDADE` → `habilidade` (`habilidade_origem = "inep"`) e `IN_ITEM_ABAN` → `anulada`; divergências pontuais de gabarito ficam em `qualidade.observacoes` e prevalece o INEP.

### Classificação de assuntos

Heurística por palavras-chave (`taxonomia/assuntos.json`) com bônus quando a habilidade oficial pertence ao assunto; até 3 assuntos por questão, marcados `classificacao = "heuristica"`. Nas curadas a classificação é manual (`"revisada"`), assim como a habilidade (`habilidade_origem = "revisada"`). Sem microdados, a habilidade das demais questões é inferida do primeiro assunto (`"heuristica"`) e deve ser tratada como estimativa.

## Estatísticas (geração atual)

| Indicador | Valor |
|---|---|
| Anos cobertos | 2009–2023 (15 edições, caderno azul) |
| Questões | 636 |
| Questões com TRI | **0** (ver limitações) |
| Questões curadas (trilha inicial) | 59 |
| Questões que dependem de imagem | 419 |
| Questões com enunciado vazio na transcrição | 54 |
| Questões sem assunto atribuído pela heurística | 84 |

Curadas por assunto (uma questão pode ter mais de um): porcentagem 13 · equação do 1º grau 11 · razão e proporção 10 · gráficos e tabelas 8 · grandezas/unidades/escalas 6 · sequências/PA 6 · estatística básica 6 · probabilidade 6 · função afim 5 · análise combinatória 5 · leitura de gráfico de função 3 · geometria plana 3 · regra de três 3 · equação do 2º grau 3 · função quadrática 2 (além de números e operações 3 e matemática financeira 1, como assuntos secundários). Todos os 15 assuntos de foco têm curadas. Dos 59 itens, 50 não dependem de imagem; os 9 restantes usam tabelas ou gráficos simples cujos dados estão transcritos em `dados_da_imagem`.

Números completos (por ano, por assunto, por habilidade) em `data/stats.json`.

## Limitações conhecidas

1. **Sem parâmetros TRI nem habilidade oficial nesta geração.** O host `download.inep.gov.br` recusou todas as conexões a partir do ambiente em que o banco foi gerado (erro TLS `unexpected EOF`, em várias tentativas, com `curl`, `requests` e um buscador externo; a página `gov.br/inep` responde normalmente). Por isso `tri = null` e `dificuldade_estimada = null` em todas as questões, e a habilidade é estimada (`habilidade_origem = "heuristica"`) fora das curadas. Nenhum parâmetro foi inventado. O script `fetch_inep_itens.py` está pronto (parser testado com o layout oficial do CSV) e o registro das tentativas fica em `cache/inep/status.json`; basta rodá-lo de uma rede com acesso ao INEP (ou passar `--csv`) e reconstruir. A ordem da trilha (`data/curadas.json`) usa `tri.b` quando existir; sem TRI, usa `nivel_curador`.
2. **Questões com imagem.** 419 das 636 questões dependem de figura, gráfico ou tabela em imagem (hospedada pela enem.dev). O texto não descreve a imagem; o tutor deve exibi-la. Na curadoria priorizamos questões sem imagem.
3. **Transcrição incompleta.** 54 questões vieram sem o texto-base (`qualidade.enunciado_vazio = true`, concentradas em 2014–2016) e 3 têm só 4 alternativas transcritas. Faltam na API alguns números por ano (ex.: 2011 e 2020/2023 têm 38–40 questões; a lista está em `stats.json → anos.{ano}.numeros_faltantes`). A API repete a questão 150 em quase todos os anos (duplicata removida) e, em 2021 e 2023, rotula como matemática itens 94 e 128–132 que são de outras áreas (descartados).
4. **Gabaritos suspeitos na transcrição.** Em `enem-2020-140` (porcelanato) e `enem-2022-145` (gemas e moedas) a resolução não leva ao `correctAlternative` informado pela enem.dev; essas questões foram mantidas no banco com o gabarito da transcrição, mas deixadas fora da curadoria até conferência com o gabarito oficial do INEP (o casamento com os microdados corrige isso automaticamente quando disponível).
5. **Classificação heurística.** Fora das 59 curadas, assuntos e habilidade são estimativas por palavras-chave; servem para busca e filtros, não como rótulo definitivo.
6. **Numeração.** O `numero` segue o caderno azul da aplicação regular (Matemática = 136–180 no 2º dia), que é o que a transcrição usa; outras cores têm ordem diferente.

## Licença e uso

Dados do INEP: públicos, cite a origem. Código, taxonomia e resoluções: uso interno do Gabarita (defina a licença do repositório antes de publicar).
