# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the pipeline

```bash
# Scripts por camada
bash scripts/10_bronze.sh [--owner X]
bash scripts/20_silver.sh [--owner X]
bash scripts/30_gold.sh   [--owner X] [--month YYYY-MM]
bash scripts/40_sync_map.sh [--owner X] [--month YYYY-MM]

# Pipeline completa (bronze → silver → gold)
bash scripts/00_full.sh [--owner X] [--month YYYY-MM]

# Ou direto via Python
python src/pipeline.py --owner person1 --layer bronze
```

Run from the **project root** — all paths are relative (`data/`, `src/`).

## Architecture

Medallion pipeline: **PDF → Markdown → Bronze → Silver**

```
data/raw_data/{owner}/{bank}/{account_type}/*.pdf   ← source PDFs (gitignored)
data/markdown/{owner}/{bank}/{account_type}/*.md    ← cached Markdown (gitignored)
data/bronze/{owner}/{bank}/{account_type}/*.csv     ← extracted, one file per month per account type
data/silver/{owner}/*.csv                           ← unified schema, debito+credito merged per bank/month
```

### `src/bronze.py` — PDF → Bronze
Discovers all PDFs under `data/raw_data/`, converts each to Markdown via `pymupdf4llm` (cached in `data/markdown/`), routes to the right extractor, and writes CSVs to `data/bronze/`. Adding a new bank requires: (1) creating an extractor in `src/extractors/`, (2) registering it in the `EXTRACTORS` dict in `bronze.py`.

### `src/extractors/` — Markdown parsers
Each extractor exposes a single function `parse_markdown(text: str, competencia: str) -> pd.DataFrame`. No file I/O — pure text-in, DataFrame-out.

- **`itau_debito.py`** — simplest: matches clean table rows `|DD/MM/YYYY|desc|**value**||`
- **`santander_debito.py`** — `<br>`-separated cells, two-column PDF layout, `last_date` carry-forward for dateless rows, stops at `SALDO EM` closing balance
- **`itau_credito.py`** — most complex; see quirks below

### `src/gold.py` — Silver → Gold
Lê todos os silver CSVs de um owner/mês, aplica `data/merchant_maps/` por substring match, e escreve um JSON consolidado em `data/gold/{owner}/{YYYY-MM}.json`.

**Fluxo de enriquecimento manual:**
```bash
bash scripts/30_gold.sh --month 2026-02      # gera JSON (Pendente onde sem match)
# editar manualmente os Pendente no JSON gold
bash scripts/40_sync_map.sh --month 2026-02  # propaga preenchimentos → merchant_maps/2026-02.json
bash scripts/30_gold.sh --month 2026-02      # regenera: entradas agora auto-preenchidas
```

`40_sync_map.sh` só escreve entradas reais (não Pendente) e ignora entradas cujo `nome_original` bate em `data/merchant_maps/nao_mapear.json`.

**Estrutura dos merchant maps:**
```
data/merchant_maps/
  nao_mapear.json      ← substrings globais a nunca auto-mapear (editado manualmente)
  2026-01.json         ← entradas reais extraídas do gold de janeiro
  2026-02.json         ← entradas reais extraídas do gold de fevereiro
  ...
```
O gold lê todos os arquivos `YYYY-MM.json` em ordem cronológica; mês mais recente ganha. Quando a mesma chave aparece com valores diferentes entre meses, o sync loga `[DUP]`.

### `src/silver.py` — Bronze → Silver
Groups bronze CSVs by `(owner, bank, competencia)`, merges debito+credito for the same bank/month, normalises to the unified schema, and outputs one CSV per bank per month.

**Silver schema:** `owner, bank, account_type, competencia, data (YYYY-MM-DD), descricao, valor, categoria, secao, parcela, moeda`

Columns absent in a source (e.g. `parcela` for debito, `secao` for santander) are filled with `None`.

---

## Itaú Crédito parser — key quirks

The PDF layout makes this extractor non-trivial. Understand these before touching it:

**`_all_cell_parts`** flattens all `<br>`-separated content from every Markdown table cell into a flat list, then splits `"VALOR EM R$ DD/MM"` header tokens so the embedded date becomes a standalone entry (needed to recover the first transaction whose date is fused with the column header).

**`_split_sections`** divides the flat list into `(nac_parts, inter_parts)` at the first token that `startswith("lançamentos internacionais")`. Uses `startswith` because some months merge the header with the cardholder name (`"Lançamentos internacionaisPERSON A P..."`) with no `<br>`.

**`_parse_section`** walks the parts list date-by-date. The inner `tx_parts` collector only breaks on a new date **if a value has already been found** — this prevents installment counters like `02/10` (which match `DD/MM`) from prematurely ending transaction collection.

**Stop markers** — multiple spelling variants exist across months:
```python
"compras parceladas-próximas faturas"
"compras parceladas - próximas faturas"   # some months have spaces around the dash
"próxima fatura" / "demais faturas"
```

**Deduplication** — some faturas (e.g. April) list both current and next-month installments in the same block before the stop marker. This is detected by comparing the parsed sum against `"Total dos lançamentos atuais"` from the PDF: if they diverge by >1%, dedup by `(data, descricao, valor)`. The description is already clean (installment counter stripped into `parcela` column), so no normalisation step is needed.

**IOF** — international transactions carry a USD value; the correct BRL+IOF total is extracted from `"Total lançamentos inter. em R$"` and overrides the valor when there is exactly one international transaction.

**`parcela` column** — trailing `DD/NN` suffix is stripped from the establishment name and stored separately (e.g. `"AOMORI TIJUCA - LO04/10"` → `descricao="AOMORI TIJUCA - LO"`, `parcela="04/10"`). Single-payment transactions get `"1/1"`.
