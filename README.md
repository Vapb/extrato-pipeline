# extrato-pipeline

Converte extratos bancários em PDF em JSONs estruturados e categorizados por mês.

## Arquitetura

```
PDF → Markdown → Bronze → Silver → Gold
```

```
data/
  raw_data/{owner}/{bank}/{account_type}/*.pdf   ← entrada (gitignored)
  bronze/{owner}/{bank}/{account_type}/*.csv     ← um CSV por conta/mês
  silver/{owner}/*.csv                           ← schema unificado
  gold/{owner}/{YYYY-MM}.json                    ← saída final
  merchant_map.json                              ← mapeamento de merchants
```

## Comandos

```bash
# Pipeline completo
python src/pipeline.py

# Filtros
python src/pipeline.py --owner person1
python src/pipeline.py --layer bronze|silver|gold
python src/pipeline.py --layer gold --owner person1 --month 2026-01

# Re-aplicar merchant_map sem reler o silver
python src/pipeline.py --layer apply-map --owner person1 --month 2026-01
```

> `--month` só filtra gold e apply-map. Bronze e silver processam todos os meses do owner.

## Fluxo de enriquecimento

```bash
python src/pipeline.py --layer gold    # gera JSONs (novos lançamentos = "Pendente")
python src/merchant_map.py             # registra todos no merchant_map
# editar merchant_map.json — trocar "Pendente" por valores reais
python src/pipeline.py --layer apply-map   # propaga para os JSONs gold
```

`apply-map` só atualiza entradas ainda com `"Pendente"` — valores preenchidos manualmente são preservados.

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

## merchant_map.json

Chave = substring do `nome_original` (case-insensitive). `_source` registra qual arquivo gold introduziu a entrada.

```json
{
  "mapeamentos": {
    "AOMORI TIJUCA": {
      "nome_simplificado": "Aomori",
      "categoria": "Restaurante",
      "_source": "person1/2026-01"
    }
  }
}
```

## Adicionar novo banco

1. Criar `src/extractors/{banco}_{tipo}.py` com `parse_markdown(text: str, competencia: str) -> pd.DataFrame`
2. Registrar no dict `EXTRACTORS` em `src/bronze.py`

## Dependências

```bash
pip install pymupdf4llm pandas
```
