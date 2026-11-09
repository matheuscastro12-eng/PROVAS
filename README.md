# PROVAS — banco de questões de Matemática do ENEM (Gabarita)

Banco de questões objetivas de **Matemática e suas Tecnologias** do ENEM (2009–2023) usado pelo app **Gabarita**, a IDE agêntica de estudo para o ENEM. Cada questão vem com metadados pedagógicos (habilidade e competência oficiais da Matriz de Referência, assuntos de uma taxonomia própria, gabarito oficial do INEP, parâmetros TRI dos microdados) e, para a trilha inicial do tutor, uma curadoria com resolução passo a passo, dicas em três níveis, análise dos distratores e verificação em SymPy.

Somente material público e oficial do INEP, sempre com a fonte citada. Tudo em pt-BR.

## Fontes e direitos

| O quê | Fonte | Como citamos |
|---|---|---|
| Texto das questões, alternativas e imagens | Provas oficiais do ENEM (INEP), transcritas pela comunidade em [enem.dev](https://enem.dev) e servidas pela API pública `https://api.enem.dev/v1` | `fonte.orgao = "INEP"`, `fonte.prova = "ENEM {ano}, 2º dia, caderno azul (aplicação regular), questão {n}"`, `fonte.url_oficial` (página de provas e gabaritos do INEP) e `fonte.transcricao_url` (URL da questão na enem.dev) |
| Gabarito oficial, parâmetros TRI (a, b, c), habilidade oficial e itens anulados | Microdados do ENEM (INEP): `ITENS_PROVA_{ano}.csv` de `https://download.inep.gov.br/microdados/microdados_enem_{ano}.zip`. Como o host do INEP estava inacessível no ambiente de geração, os CSVs de 2009–2023 foram obtidos do espelho público **Zenodo record 18801899** — *Microdados Oficiais do ENEM (2009-2023) - Relação Itens e Prova*, <https://zenodo.org/records/18801899> | `gabarito_fonte = "inep"`, `tri.fonte = "INEP, microdados do ENEM {ano} (ITENS_PROVA), espelho Zenodo record 18801899"`, `fonte.microdados_url` (zip oficial) e `fonte.microdados_espelho_url` (Zenodo) |
| Matriz de Referência (7 competências, 30 habilidades) | INEP, *Matriz de Referência ENEM* (`enem_matriz_de_referencia_v1.pdf`) | `taxonomia/matriz-mt.json` reproduz o texto oficial |

As provas do ENEM são documentos públicos do INEP/MEC. A transcrição da enem.dev é um projeto comunitário aberto; mantemos a atribuição em cada questão. O espelho do Zenodo redistribui, sem alteração declarada, os CSVs oficiais do INEP (ver a limitação sobre decimais abaixo). As resoluções, dicas, taxonomia e código deste repositório são obra própria.

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
  fetch_inep_itens.py      lê ITENS_PROVA_{ano}.csv (zip do INEP ou CSVs de um espelho), filtra SG_AREA='MT'
                           e valida/corrige os parâmetros TRI
  build.py                 casa transcrição × microdados, aplica correções de transcrição, classifica assuntos,
                           incorpora a curadoria, calcula os tercis de dificuldade e gera data/
  validate.py              valida schemas, ids, gabaritos, faixas TRI, taxonomia e executa as verificações SymPy
  verificar_sympy.py       executa o bloco `verificacao` de uma resolução
  comum.py                 caminhos e utilidades
data/
  questoes/matematica/{ano}.json   questões completas (uma lista por ano)
  index.json               lista compacta: id, ano, numero, assuntos, habilidade, b, dificuldade_estimada, curada
  stats.json               estatísticas, limiares de dificuldade e registro do casamento com os microdados, por ano
  curadas.json             trilha inicial: curadas ordenadas da mais fácil para a mais difícil (tri.b)
  resolucoes/{id}.json     curadoria (resolução, dicas, erros comuns, conceitos, verificação SymPy)
  correcoes_transcricao.json  erros de digitação da transcrição corrigidos à mão, com evidência
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
  "gabarito": "D", "gabarito_fonte": "inep",   // "inep" (TX_GABARITO oficial) | "transcricao" (só enem.dev)
  "anulada": false,                            // IN_ITEM_ABAN = 1 nos microdados
  "habilidade": "H19", "habilidade_origem": "inep",   // "inep" | "heuristica" | "revisada"
  "competencia": "C5",
  "assuntos": ["funcao-afim"], "classificacao": "revisada",  // "heuristica" | "revisada"
  "tri": {"a": 1.97, "b": 0.86, "c": 0.14, "corrigido": false,
          "fonte": "INEP, microdados do ENEM 2023 (ITENS_PROVA), espelho Zenodo record 18801899"},
  "dificuldade_estimada": "facil",   // tercis de b do banco (limiares em stats.json); null sem TRI
  "fonte": {"orgao": "INEP", "prova": "ENEM 2023, 2º dia, caderno azul (aplicação regular), questão 162",
            "url_oficial": "https://www.gov.br/inep/…/provas-e-gabaritos", "transcricao": "enem.dev",
            "transcricao_url": "https://api.enem.dev/v1/exams/2023/questions/162",
            "microdados_url": "https://download.inep.gov.br/microdados/microdados_enem_2023.zip",
            "microdados_espelho_url": "https://zenodo.org/records/18801899"},
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
# microdados do INEP → cache inep/itens_mt_{ano}.json. Três caminhos:
uv run python scripts/fetch_inep_itens.py 2019 2020 2021 2022 2023          # baixa os zips do INEP
uv run python scripts/fetch_inep_itens.py 2022 --csv /caminho/ITENS_PROVA_2022.csv   # um CSV já baixado
uv run python scripts/fetch_inep_itens.py --csv-dir /workspace/gabarita/cache/zenodo \
    --espelho "Zenodo record 18801899"         # CSVs 2009–2023 do espelho (o que gerou o banco atual)
uv run python scripts/build.py                 # gera data/
uv run python scripts/validate.py              # valida tudo (inclui as verificações SymPy)
uv run pytest                                  # testes
```

`build.py` é idempotente: refaça a curadoria editando `data/resolucoes/{id}.json` e rode `build.py` de novo. Para adicionar uma questão à trilha, crie o arquivo de resolução (obedecendo `schema/resolucao.schema.json`) e reconstrua.

### Validação dos parâmetros TRI (`fetch_inep_itens.py`)

Faixas plausíveis para o modelo logístico de 3 parâmetros na escala do INEP: **a ∈ (0, 6]**, **b ∈ [−6, 6]**, **c ∈ [0, 1)**.

- Valor dentro da faixa: aceito como está.
- Valor fora da faixa **com o padrão de decimal quebrado do espelho** (um inteiro formatado com separador de milhar, como `141.931` no lugar de `1.41931` ou `250.064` no lugar de `2.50064`): corrigido pela reinserção do ponto decimal após o primeiro dígito, **só se o resultado cair na faixa**. A questão recebe `tri.corrigido = true` e uma observação em `qualidade.observacoes`. Isso ocorreu apenas em **2009** (a e b ≥ 1 de todos os cadernos; c e os valores < 1 estavam intactos), em 40 questões do caderno azul.
- Qualquer outro valor fora da faixa (valores publicados assim pelo INEP, como `b = 17,62` com `a = 0,10` em 2013, ou `a = 6,20` em 2017): os três parâmetros viram `null` e o motivo fica em `qualidade.observacoes` ("parâmetros TRI descartados: …"). São 9 questões.

### Como o casamento com os microdados funciona

Para cada ano, `build.py` agrupa os itens de MT por `CO_PROVA`, normaliza a cor (`Azul`/`AZUL` → `AZUL`), prefere cadernos azuis e escolhe o caderno cujo `TX_GABARITO` mais coincide com o `correctAlternative` da transcrição (posição `CO_POSICAO` = número da questão; em 2017 os microdados numeram Matemática de 1 a 45 e o deslocamento +135 é detectado e registrado). Empates entre cadernos azuis (reaplicação, versão digital) vão para o não digital de menor `CO_PROVA`. O casamento só é aceito se os gabaritos baterem em **≥ 90 %** dos itens comparáveis (não anulados); caso contrário é descartado e registrado em `data/stats.json` (`anos.{ano}.inep`). Quando aceito:

- `TX_GABARITO` → `gabarito` e `gabarito_fonte = "inep"`. **O gabarito oficial prevalece**; divergências ficam em `qualidade.observacoes` e em `stats.json → anos.{ano}.inep.divergencias`.
- `NU_PARAM_A/B/C` → `tri` (validados como acima), `CO_HABILIDADE` → `habilidade` (`habilidade_origem = "inep"`), `IN_ITEM_ABAN` → `anulada` (item anulado fica com `tri = null` e `gabarito_fonte = "transcricao"`, pois o INEP publica `X`).

### Correções de transcrição

`data/correcoes_transcricao.json` lista erros de digitação da enem.dev corrigidos à mão, cada um com texto original, texto corrigido, motivo e evidência; `build.py` só aplica a correção se o texto atual for exatamente o esperado e registra a mudança em `qualidade.observacoes`. Hoje há uma: em `enem-2020-140` a alternativa C dizia "3 caixas do tipo A e 1 caixa do tipo B" (15 peças, incompatível com o gabarito oficial C); a prova traz "… e **2** caixas do tipo B" (18 peças, R$ 159,00).

### Dificuldade estimada

`dificuldade_estimada` deriva de `tri.b` pelos **tercis do parâmetro b das questões de MT com TRI no banco**, recalculados a cada `build.py` e gravados em `stats.json → limiares_dificuldade` (geração atual: `facil` se b < 1,56; `media` se 1,56 ≤ b < 2,33; `dificil` se b ≥ 2,33, sobre 614 questões). Os limiares são relativos ao próprio ENEM de Matemática: um item "fácil" aqui ainda tem b positivo na escala (0,1) do INEP, porque Matemática é a área mais difícil da prova para a população de participantes. A trilha `data/curadas.json` ordena pelo `b` crescente (as poucas curadas sem TRI, se houver, vão para o fim por `nivel_curador`).

### Classificação de assuntos

Heurística por palavras-chave (`taxonomia/assuntos.json`) com bônus quando a habilidade oficial pertence ao assunto; até 3 assuntos por questão, marcados `classificacao = "heuristica"`. Nas curadas a classificação é manual (`"revisada"`). A habilidade é sempre a oficial do INEP (`habilidade_origem = "inep"`) nesta geração; em 27 curadas a habilidade proposta pela curadoria diferia da oficial e prevaleceu a oficial (a proposta continua em `resolucao.habilidade` para auditoria).

## Estatísticas (geração atual)

| Indicador | Valor |
|---|---|
| Anos cobertos | 2009–2023 (15 edições, caderno azul da aplicação regular) |
| Questões | 636 |
| Questões com TRI | **614** (22 sem: 13 anuladas pelo INEP + 9 com parâmetros implausíveis descartados) |
| Questões com TRI corrigido (decimal do espelho) | 40 (todas de 2009) |
| Gabarito confirmado pelo INEP | 623 (`gabarito_fonte = "inep"`); 13 anuladas mantêm o da transcrição |
| Divergências de gabarito enem.dev × INEP (prevaleceu o INEP) | 6: enem-2010-139 (A→B), enem-2012-165 (E→C), enem-2021-139 (A→E), enem-2021-145 (A→C), enem-2021-152 (D→E), enem-2022-143 (A→D) |
| Habilidade oficial (`habilidade_origem = "inep"`) | 636 |
| Dificuldade (tercis de b: 1,56 e 2,33) | fácil 204 · média 204 · difícil 206 · sem TRI 22 |
| Questões curadas (trilha inicial) | 59 (fácil 19 · média 21 · difícil 19; todas com TRI) |
| Questões que dependem de imagem | 419 |
| Questões com enunciado vazio na transcrição | 54 |
| Questões sem assunto atribuído pela heurística | 84 |

Casamento com os microdados, por ano (caderno azul escolhido, itens comparáveis e taxa de coincidência do gabarito):

| Ano | CO_PROVA | Questões | Comparáveis | Gabarito igual | Divergências | Com TRI | TRI corrigidos | TRI descartados | Anuladas |
|---|---|---|---|---|---|---|---|---|---|
| 2009 | 63 | 42 | 40 | 100 % | 0 | 40 | 40 | 0 | 2 |
| 2010 | 99 | 45 | 42 | 98 % | 1 | 42 | 0 | 0 | 3 |
| 2011 | 131 | 38 | 38 | 100 % | 0 | 38 | 0 | 0 | 0 |
| 2012 | 151 | 42 | 42 | 98 % | 1 | 42 | 0 | 0 | 0 |
| 2013 | 181 | 42 | 42 | 100 % | 0 | 40 | 0 | 2 | 0 |
| 2014 | 209 | 45 | 44 | 100 % | 0 | 43 | 0 | 1 | 1 |
| 2015 | 245 | 42 | 42 | 100 % | 0 | 41 | 0 | 1 | 0 |
| 2016 | 303 | 45 | 45 | 100 % | 0 | 44 | 0 | 1 | 0 |
| 2017 | 403 (posições 1–45, +135) | 43 | 43 | 100 % | 0 | 41 | 0 | 2 | 0 |
| 2018 | 459 | 42 | 41 | 100 % | 0 | 41 | 0 | 0 | 1 |
| 2019 | 515 | 44 | 43 | 100 % | 0 | 42 | 0 | 1 | 1 |
| 2020 | 587 | 40 | 39 | 100 % | 0 | 39 | 0 | 0 | 1 |
| 2021 | 899 | 42 | 42 | 93 % | 3 | 42 | 0 | 0 | 0 |
| 2022 | 1075 | 44 | 42 | 98 % | 1 | 41 | 0 | 1 | 2 |
| 2023 | 1211 | 40 | 38 | 100 % | 0 | 38 | 0 | 0 | 2 |

Em 2009 a transcrição corresponde ao caderno 63 (100 % dos gabaritos) e não aos cadernos 77–80 (12 %), que não têm `CO_HABILIDADE`.

Curadas por assunto (uma questão pode ter mais de um): porcentagem 13 · equação do 1º grau 11 · razão e proporção 10 · gráficos e tabelas 8 · grandezas/unidades/escalas 6 · sequências/PA 6 · estatística básica 6 · probabilidade 6 · função afim 5 · análise combinatória 5 · leitura de gráfico de função 3 · geometria plana 3 · regra de três 3 · equação do 2º grau 3 · função quadrática 2 (além de números e operações 3 e matemática financeira 1, como assuntos secundários). Todos os 15 assuntos de foco têm curadas. Dos 59 itens, 50 não dependem de imagem; os 9 restantes usam tabelas ou gráficos simples cujos dados estão transcritos em `dados_da_imagem`.

Números completos (por ano, por assunto, por habilidade, divergências) em `data/stats.json`.

## Limitações conhecidas

1. **Microdados via espelho.** O host `download.inep.gov.br` recusou todas as conexões a partir do ambiente de geração (erro TLS `unexpected EOF`; registro em `cache/inep/status.json`). Os CSVs `ITENS_PROVA_{ano}.csv` vieram do espelho público Zenodo record 18801899. Em 2009 o espelho traz os decimais de a e b quebrados (`270.316` por `2.70316`); corrigimos só o padrão inequívoco e marcamos `tri.corrigido = true` (ver *Validação dos parâmetros TRI*). Ao obter os zips oficiais, basta rodar `fetch_inep_itens.py` sem `--espelho` e reconstruir: os testes acusam se algum valor divergir das faixas.
2. **22 questões sem TRI.** 13 foram anuladas pelo INEP (`anulada = true`, sem parâmetros) e 9 têm parâmetros publicados fora das faixas plausíveis (b entre 6,3 e 17,6 com discriminação muito baixa, ou a > 6); essas ficam com `tri = null`, `dificuldade_estimada = null` e o motivo em `qualidade.observacoes`.
3. **Questões com imagem.** 419 das 636 questões dependem de figura, gráfico ou tabela em imagem (hospedada pela enem.dev). O texto não descreve a imagem; o tutor deve exibi-la. Na curadoria priorizamos questões sem imagem.
4. **Transcrição incompleta.** 54 questões vieram sem o texto-base (`qualidade.enunciado_vazio = true`, concentradas em 2014–2016) e 3 têm só 4 alternativas transcritas. Faltam na API alguns números por ano (ex.: 2011 e 2020/2023 têm 38–40 questões; a lista está em `stats.json → anos.{ano}.numeros_faltantes`). A API repete a questão 150 em quase todos os anos (duplicata removida) e, em 2021 e 2023, rotula como matemática itens 94 e 128–132 que são de outras áreas (descartados).
5. **Gabaritos.** O gabarito é o oficial do INEP em 623 questões. Os dois casos antes suspeitos foram resolvidos: `enem-2020-140` tem gabarito oficial C e o erro estava na alternativa C transcrita (corrigida, ver *Correções de transcrição*); `enem-2022-145` tem gabarito oficial E (400 000 moedas: a quantidade a inserir é medida em relação ao pacote básico, 500 000 − 100 000). As 6 divergências listadas acima seguem o INEP; a transcrição dessas questões ainda pode ter outros erros (texto ou ordem das alternativas) que só a conferência com o PDF oficial elimina.
6. **Classificação heurística.** Fora das 59 curadas, os assuntos são estimativas por palavras-chave; servem para busca e filtros, não como rótulo definitivo. A habilidade, ao contrário, é oficial.
7. **Numeração.** O `numero` segue o caderno azul da aplicação regular (Matemática = 136–180 no 2º dia), que é o que a transcrição usa; outras cores têm ordem diferente.

## Licença e uso

Dados do INEP: públicos, cite a origem. Código, taxonomia e resoluções: uso interno do Gabarita (defina a licença do repositório antes de publicar).
