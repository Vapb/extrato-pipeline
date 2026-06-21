# extrato-pipeline

Converte extratos bancários em PDF em CSVs estruturados e categorizados por mês.

## Pipeline principal

```mermaid
flowchart LR
    U["👤 Usuário\norganiza PDFs\nem raw_data/"]
    B["🥉 bronze.sh\nPDF → Markdown → CSV"]
    S["🥈 silver.sh\nAgrupa e normaliza"]
    G["🥇 gold.sh\nEnriquece e consolida"]

    U --> B --> S --> G
```

## Lógica do gold

```mermaid
flowchart TD
    START([gold.sh]) --> EG{Gold do mês\njá existe?}

    %% Caminho: gold NÃO existe
    EG -- Não --> EM{merchant_map\nexiste?}

    EM -- "Nenhum" --> GN[Gera gold\ncom tudo Pendente]
    GN --> CN[Cria merchant_map\ndo mês com Pendentes]

    EM -- "Só meses\nanteriores" --> LP[Lê maps passados\nem ordem cronológica\nMais recente prevalece]
    LP --> DUP{Inconsistência\nentre meses?}
    DUP -- Sim --> LOG[Loga DUP\nUsa registro mais recente]
    DUP -- Não --> AP
    LOG --> AP[Matches → preenchidos\nSem match → Pendente no gold]

    EM -- "Do mês atual" --> GM[Gera gold\nusando o map do mês]
    GM --> PM[Sem match → Pendente\nno gold e no map]

    %% Caminho: gold JÁ existe
    EG -- Sim --> EM2{merchant_map\ndo mês existe?}

    EM2 -- Não --> CR[Cria merchant_map\ndo mês a partir\ndo gold existente]

    EM2 -- Sim --> AT[Atualiza merchant_map\nPendentes no map que já\nestão preenchidos no gold\nsão atualizados]
```

## Ciclo de enriquecimento manual

```mermaid
flowchart LR
    G1["30_gold.sh\n--month 2026-04"]
    ED["✏️ Editar CSV\nmanualmente\nExcel / Sheets"]
    SM["40_sync_map.sh\n--month 2026-04"]
    G2["30_gold.sh\n--month 2026-04"]

    G1 -->|"gera gold com\nPendentes"| ED
    ED -->|"propaga preenchimentos\n→ merchant_maps/"| SM
    SM -->|"regenera gold\nauto-preenchido"| G2
```

> `40_sync_map.sh` ignora entradas Pendente e substrings listadas em `nao_mapear.csv`.

---

## Estrutura de dados

```
data/
  raw_data/{owner}/{bank}/{account_type}/*.pdf     ← entrada (gitignored)
  markdown/{owner}/{bank}/{account_type}/*.md      ← cache intermediário (gitignored)
  bronze/{owner}/{bank}/{account_type}/*.csv       ← um CSV por conta/mês
  silver/{owner}/*.csv                             ← schema unificado
  gold/{owner}/{YYYY-MM}.csv                       ← saída final enriquecida
  merchant_maps/
    nao_mapear.csv                                 ← substrings a nunca auto-mapear
    {YYYY-MM}.csv                                  ← mapeamentos por mês
```

## Comandos

```bash
# Pipeline completa
bash scripts/00_full.sh [--owner X] [--month YYYY-MM]

# Camadas individuais
bash scripts/10_bronze.sh [--owner X]
bash scripts/20_silver.sh [--owner X]
bash scripts/30_gold.sh   [--owner X] [--month YYYY-MM]
bash scripts/40_sync_map.sh [--owner X] [--month YYYY-MM]
```

> `--month` só filtra gold e sync_map. Bronze e silver processam todos os meses do owner.

---

## Schemas

### Gold (`data/gold/{owner}/{YYYY-MM}.csv`)

| coluna | descrição |
|---|---|
| `data` | data da transação (YYYY-MM-DD) |
| `nome_original` | nome exato do extrato |
| `nome_simplificado` | nome legível (ou `Pendente`) |
| `categoria` | categoria de gasto (ou `Pendente`) |
| `valor` | valor em BRL (negativo = despesa) |
| `origem` | banco e tipo de conta |
| `situacao` | `avista`, `parcelado` ou vazio (débito) |
| `parcela_atual` | número da parcela atual |
| `parcelas_total` | total de parcelas |

### merchant_maps (`data/merchant_maps/{YYYY-MM}.csv`)

| coluna | descrição |
|---|---|
| `nome_original` | substring do nome original (case-insensitive) |
| `nome_simplificado` | nome simplificado a aplicar (ou `Pendente`) |
| `categoria` | categoria a aplicar (ou `Pendente`) |

---

## Adicionar novo banco

1. Criar `src/extractors/{banco}_{tipo}.py` com `parse_markdown(text: str, competencia: str) -> pd.DataFrame`
2. Registrar no dict `EXTRACTORS` em `src/bronze.py`

## Dependências

```bash
pip install pymupdf4llm pandas
```
