# extrato-pipeline

Pipeline de processamento de extratos bancários em PDF. Converte PDFs de múltiplos bancos em JSONs estruturados e categorizados por mês.

---

## Arquitetura

Arquitetura medallion em quatro camadas:

```
PDF → Markdown → Bronze → Silver → Gold
```

| Camada | Entrada | Saída | Responsabilidade |
|--------|---------|-------|-----------------|
| Bronze | PDFs raw | CSVs por conta/mês | Extração e parsing dos PDFs |
| Silver | CSVs bronze | CSVs normalizados | Schema unificado, limpeza de descrições |
| Gold | CSVs silver | JSONs por owner/mês | Consolidação, enriquecimento via merchant_map |

---

## Estrutura de pastas

```
data/
  raw_data/{owner}/{bank}/{account_type}/*.pdf   ← PDFs de entrada (gitignored)
  markdown/{owner}/{bank}/{account_type}/*.md    ← cache de Markdown (gitignored)
  bronze/{owner}/{bank}/{account_type}/*.csv     ← um CSV por conta por mês
  silver/{owner}/*.csv                           ← schema unificado, débito+crédito fundidos
  gold/{owner}/{YYYY-MM}.json                    ← JSON final enriquecido

data/merchant_map.json                           ← mapeamento de merchants (editável)

src/
  pipeline.py          ← ponto de entrada principal
  bronze.py            ← camada bronze
  silver.py            ← camada silver
  gold.py              ← camada gold + apply_map
  merchant_map.py      ← sync gold → merchant_map
  extractors/
    itau_debito.py
    itau_credito.py
    santander_debito.py
```

---

## Como rodar

Execute sempre a partir da raiz do projeto.

### Pipeline completo

```bash
python src/pipeline.py
```

### Filtros disponíveis

```bash
# Só um owner
python src/pipeline.py --owner person1

# Só uma camada
python src/pipeline.py --layer bronze
python src/pipeline.py --layer silver
python src/pipeline.py --layer gold

# Gold de um mês específico
python src/pipeline.py --layer gold --owner person1 --month 2026-01

# Owner e mês juntos (bronze e silver processam todos os meses do owner)
python src/pipeline.py --owner person1 --month 2026-01
```

### Re-aplicar merchant_map sem reler o silver

```bash
python src/pipeline.py --layer apply-map
python src/pipeline.py --layer apply-map --owner person1 --month 2026-01
```

---

## Fluxo de enriquecimento (merchant_map)

O `merchant_map.json` mapeia nomes originais de lançamentos para nome simplificado e categoria. O fluxo é iterativo:

```
1. Gerar gold  —  lançamentos novos saem com "Pendente"
   python src/pipeline.py --layer gold

2. Sincronizar gold → merchant_map  —  registra todos os merchants, inclusive Pendentes
   python src/merchant_map.py

3. Editar merchant_map.json  —  preencher os "Pendente" com valores reais

4. Re-aplicar merchant_map nos JSONs gold  —  sem reler silver
   python src/pipeline.py --layer apply-map
```

### Comportamento do apply_map

- Só atualiza entradas onde `nome_simplificado` ou `categoria` ainda é `"Pendente"`
- Valores preenchidos manualmente no gold **não são sobrescritos**
- O merchant_map nunca escreve `"Pendente"` sobre um valor já preenchido

### Estrutura do merchant_map.json

```json
{
  "categorias_validas": ["Restaurante", "Mercado", "Casa", ...],
  "mapeamentos": {
    "AOMORI TIJUCA": {
      "nome_simplificado": "Aomori",
      "categoria": "Restaurante",
      "_source": "person1/2026-01"
    },
    "ANUIDADE DIFERENCI": {
      "nome_simplificado": "Pendente",
      "categoria": "Pendente",
      "_source": "person1/2026-01"
    }
  }
}
```

- **Chave**: substring do `nome_original` (case-insensitive). Match: `chave in nome_original`.
- **`_source`**: `owner/YYYY-MM` do arquivo gold que introduziu o registro.
- Entradas com valor real no merchant_map nunca são sobrescritas pelo sync.
- Entradas Pendente são promovidas quando o gold traz valor real para o mesmo merchant.

---

## Schema do Gold (JSON de saída)

Arquivo: `data/gold/{owner}/{YYYY-MM}.json`

```json
{
  "meta": {
    "periodo": { "inicio": "2026-01-01", "fim": "2026-01-31" },
    "gerado_em": "2026-06-14"
  },
  "categorias_validas": ["Restaurante", "Mercado", ...],
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
    },
    {
      "data": "2026-01-10",
      "nome_original": "PIX TRANSF JOAO",
      "nome_simplificado": "João",
      "categoria": "Transferencia",
      "valor": -500.0,
      "origem": "Itaú PIX"
    }
  ]
}
```

Os lançamentos são ordenados por `data` e, em caso de empate, por `nome_original`.

### Campos dos lançamentos

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `data` | `YYYY-MM-DD` | Data do lançamento |
| `nome_original` | string | Nome cru vindo do extrato |
| `nome_simplificado` | string \| `"Pendente"` | Nome legível do merchant |
| `categoria` | string \| `"Pendente"` | Categoria do gasto |
| `valor` | float | Negativo = débito, positivo = crédito/estorno |
| `origem` | string | Banco + tipo da conta (ver tabela abaixo) |
| `situacao` | `"avista"` \| `"parcelado"` | Apenas em transações de crédito |
| `parcela_atual` | int | Apenas se `situacao = "parcelado"` |
| `parcelas_total` | int | Apenas se `situacao = "parcelado"` |

### Valores de `origem`

| Valor | Condição |
|-------|----------|
| `"Itaú Débito"` | Itaú débito, transação RSHOP |
| `"Itaú PIX"` | Itaú débito, PIX TRANSF |
| `"Itaú Online"` | Itaú débito, PIX QRS |
| `"Itaú Crédito"` | Qualquer transação de crédito Itaú |
| `"Santander PIX"` | Santander débito, PIX ENVIADO |
| `"Santander"` | Demais Santander |

---

## Schema do Silver (CSV intermediário)

Arquivo: `data/silver/{owner}/{YYYY_MM}_{bank}.csv`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `owner` | string | Dono do extrato |
| `bank` | string | `itau`, `santander` |
| `account_type` | string | `debito`, `credito` |
| `competencia` | `YYYY-MM` | Mês de referência do extrato |
| `data` | `YYYY-MM-DD` | Data do lançamento |
| `descricao` | string | Descrição limpa |
| `valor` | float | Valor (negativo = gasto) |
| `categoria` | string \| null | Categoria extraída do PDF (raro) |
| `secao` | string \| null | `nacional`, `internacional`, `servico` (crédito Itaú) |
| `parcela` | string \| null | `"04/10"` = parcela 4 de 10; `"1/1"` = à vista |
| `moeda` | string | Sempre `BRL` |

### Limpeza de descrições no silver

| Banco / Conta | Problema | Correção |
|--------------|----------|----------|
| Itaú débito RSHOP | Sufixo `DDMM` no final | `"RSHOP SABOR A KILO2001"` → `"RSHOP SABOR A KILO"` |
| Itaú débito PIX/outros | Sufixo `DD/MM` no final | `"PIX TRANSF OTAVIO 02/01"` → `"PIX TRANSF OTAVIO"` |
| Itaú crédito | Sufixo `DD/NN` de parcela no final | `"ANUIDADE DIFERENCI 01/12"` → `"ANUIDADE DIFERENCI"` |

### Normalização de datas no silver

Transações de crédito podem trazer datas de meses anteriores (parcelamentos iniciados antes da competência). O silver normaliza: qualquer data anterior ao início da competência vira `YYYY-MM-01` do mês da competência.

Exemplo: competência `2026-01`, data `2025-11-19` → `2026-01-01`.

---

## Extractors (Bronze)

Cada extractor é um módulo em `src/extractors/` que expõe uma única função:

```python
def parse_markdown(text: str, competencia: str) -> pd.DataFrame
```

Entrada: texto Markdown gerado pelo `pymupdf4llm`. Saída: DataFrame com as transações. Sem I/O — puro texto-in, DataFrame-out.

### Extractors disponíveis

| Arquivo | Banco | Conta |
|---------|-------|-------|
| `itau_debito.py` | Itaú | Débito |
| `itau_credito.py` | Itaú | Crédito |
| `santander_debito.py` | Santander | Débito |

### Como adicionar um novo banco

1. Criar `src/extractors/{banco}_{tipo}.py` com a função `parse_markdown`
2. Registrar no dicionário `EXTRACTORS` em `src/bronze.py`

---

## Itaú Crédito — quirks do parser

O parser `src/extractors/itau_credito.py` tem lógica não trivial por causa do layout do PDF.

### Ano das transações

O PDF lista apenas `DD/MM`. Se o mês da transação for **maior** que o mês da competência, o lançamento pertence ao ano anterior.

```
Fatura: 2026-01  |  Lançamento: 19/11  →  11 > 1  →  19/11/2025
Fatura: 2026-01  |  Lançamento: 05/01  →  01 = 1  →  05/01/2026
```

### Parcelas

O sufixo `DD/NN` no final do nome do estabelecimento é separado para a coluna `parcela`:

```
"AOMORI TIJUCA - LO04/10"  →  descricao="AOMORI TIJUCA - LO"  parcela="04/10"
```

Transações à vista recebem `parcela="1/1"`.

### Seções nacionais vs. internacionais

O PDF é dividido em lançamentos nacionais e internacionais. A seção detectada é armazenada no campo `secao` (`nacional`, `internacional`, `servico`).

### Deduplicação entre faturas

Algumas faturas listam parcelas do mês atual e do mês seguinte antes do marcador de corte. O parser compara a soma calculada com `"Total dos lançamentos atuais"` do PDF: se divergir mais de 1%, deduplica por `(data, descricao, valor)`.

### IOF em transações internacionais

Quando há exatamente uma transação internacional, o valor total BRL+IOF é extraído de `"Total lançamentos inter. em R$"` e sobrepõe o valor individual da transação.

---

## Dependências

```bash
pip install pymupdf4llm pandas
```
