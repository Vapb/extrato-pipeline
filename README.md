# extrato-pipeline

Converte extratos bancários em PDF em JSONs estruturados e categorizados por mês.

## Fluxograma

### Pipeline principal

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  raw_data/   │         │   bronze/    │         │   silver/    │         │    gold/     │
│    *.pdf     │───────▶│    *.csv     │────────▶│    *.csv     │────────▶│   *.json     │
└──────────────┘         └──────────────┘         └──────────────┘         └──────────────┘
                          10_bronze.sh              20_silver.sh              30_gold.sh
```

`bash scripts/00_full.sh [--owner X] [--month YYYY-MM]` roda as três camadas em sequência.

### Ciclo de enriquecimento manual

```
                     ┌────────────────────────────────────────┐
                     │             gold/*.json                │
                     │                                        │
                     │  ✓  mapeados  — nome + categoria ok    │
                     │  ~  pendente  — nome ok, sem categoria │
                     │  ✗  faltando  — sem mapeamento         │
                     └─────────────────┬──────────────────────┘
                                       │
                                1. editar JSON
                                (pendente / faltando)
                                       │
                                       ▼
                     ┌────────────────────────────────────────┐
                     │          merchant_maps/                │
                     │          YYYY-MM.json                  │◀── 40_sync_map.sh
                     └─────────────────┬──────────────────────┘
                                       │
                                2. regenerar gold
                                  30_gold.sh
                                       │
                                       ▼
                     ┌────────────────────────────────────────┐
                     │             gold/*.json                │
                     │       (entradas auto-preenchidas)      │
                     └────────────────────────────────────────┘
```

## Estrutura de dados

```
data/
  raw_data/{owner}/{bank}/{account_type}/*.pdf   ← entrada (gitignored)
  bronze/{owner}/{bank}/{account_type}/*.csv     ← um CSV por conta/mês
  silver/{owner}/*.csv                           ← schema unificado
  gold/{owner}/{YYYY-MM}.json                    ← saída final
  merchant_maps/
    nao_mapear.json                              ← substrings a nunca auto-mapear
    {YYYY-MM}.json                               ← mapeamentos por mês
```

## Comandos

```bash
# Pipeline completa
bash scripts/00_full.sh
bash scripts/00_full.sh --owner person
bash scripts/00_full.sh --owner person --month 2026-02

# Camadas individuais
bash scripts/10_bronze.sh [--owner X]
bash scripts/20_silver.sh [--owner X]
bash scripts/30_gold.sh   [--owner X] [--month YYYY-MM]
bash scripts/40_sync_map.sh [--owner X] [--month YYYY-MM]
```

> `--month` só filtra gold e sync_map. Bronze e silver processam todos os meses do owner.

## Schema do Gold

```json
{
  "meta": { "periodo": { "inicio": "2026-01-01", "fim": "2026-01-31" }, "gerado_em": "2026-06-14" },
  "lancamentos": [
    {
      "data": "2026-01-05",
      "nome_original": "AOMORI TIJUCA - LO",
      "nome_simplificado": "Aomori",
      "categoria": "Restaurante",
      "valor": -220.08,
      "origem": "Itaú Crédito",
      "situacao": "parcelado",
      "parcela_atual": 3,
      "parcelas_total": 10
    }
  ]
}
```

Lançamentos ordenados por `data`, depois `nome_original`. Crédito à vista tem `situacao: "avista"` sem campos de parcela. Débito não tem `situacao`.

## merchant_maps/

Cada arquivo `YYYY-MM.json` contém os mapeamentos extraídos do gold daquele mês. Chave = substring do `nome_original` (case-insensitive). Ao aplicar, todos os arquivos são lidos em ordem cronológica — mês mais recente prevalece.

```json
{
  "mes": "2026-01",
  "mapeamentos": {
    "AOMORI TIJUCA": {
      "nome_simplificado": "Aomori",
      "categoria": "Restaurante"
    }
  }
}
```

`nao_mapear.json` lista substrings que nunca devem ser auto-mapeadas (marketplaces, farmácias, iFood — cada compra é única).

## Adicionar novo banco

1. Criar `src/extractors/{banco}_{tipo}.py` com `parse_markdown(text: str, competencia: str) -> pd.DataFrame`
2. Registrar no dict `EXTRACTORS` em `src/bronze.py`

## Dependências

```bash
pip install pymupdf4llm pandas
```
