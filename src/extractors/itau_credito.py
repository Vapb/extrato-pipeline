import re

import pandas as pd

_STRIP_RE        = re.compile(r"\*\*|~~")
_DATE_RE         = re.compile(r"^(\d{2}/\d{2})$")
_VALUE_RE        = re.compile(r"^-?[\d\.]+,\d{2}$")
_VALOR_HEADER_RE = re.compile(r"^VALOR EM R\$\s*(\d{2}/\d{2})$", re.IGNORECASE)
_PARCELA_RE      = re.compile(r"(\d{2}/\d{2})$")   # trailing installment counter

_STOP_MARKERS = {
    "compras parceladas-próximas faturas",
    "compras parceladas- próximas faturas",
    "compras parceladas - próximas faturas",
    "próxima fatura",
    "demais faturas",
    "total para próximas faturas",
}

_SKIP_EXACT = {
    "data", "estabelecimento", "produtos/serviços",
    "valor em r$", "us$ r$", "brl",
    "l", "s", "=",
}

_SKIP_PREFIXES = (
    "lançamentos",
    "total ",
    "titular",
    "pagamento",
    "saldo",
    "dólar",
    "repasse",
    "juros",
    "cet",
    "próxima",
    "demais",
    "esses",
    "o limite",
    "resumo",
)


def _clean(s: str) -> str:
    return _STRIP_RE.sub("", s).strip()


def _norm_val(s: str) -> str:
    """'- 0,03' → '-0,03' (space between minus and digits)."""
    return re.sub(r"^-\s+", "-", s.strip())


def _is_value(s: str) -> bool:
    return bool(_VALUE_RE.match(_norm_val(s)))


def _parse_val(s: str) -> float:
    s = _norm_val(s)
    return float(s.replace(".", "").replace(",", "."))


def _should_skip(s: str) -> bool:
    low = s.lower()
    return (
        len(low) <= 1
        or low in _SKIP_EXACT
        or any(low.startswith(p) for p in _SKIP_PREFIXES)
    )


def _all_cell_parts(text: str) -> list[str]:
    raw: list[str] = []
    for line in text.splitlines():
        if not line.startswith("|") or "<br>" not in line:
            continue
        for col in line.split("|")[1:-1]:
            cleaned = _clean(col)
            if cleaned:
                for p in cleaned.split("<br>"):
                    p = _clean(p)
                    if p:
                        raw.append(p)

    # split "VALOR EM R$ DD/MM" into header token + extracted date
    parts: list[str] = []
    for p in raw:
        m = _VALOR_HEADER_RE.match(p)
        if m:
            parts.append("VALOR EM R$")   # skipped by _SKIP_EXACT
            parts.append(m.group(1))       # standalone date for first transaction
        else:
            parts.append(p)
    return parts


def _split_sections(parts: list[str]) -> tuple[list[str], list[str]]:
    # use startswith so merged strings like "Lançamentos internacionaisVICTOR..."
    # (no <br> between them in some months) are still detected
    try:
        idx = next(
            i for i, p in enumerate(parts)
            if p.lower().startswith("lançamentos internacionais")
        )
        return parts[:idx], parts[idx + 1:]
    except StopIteration:
        return parts, []


def _parse_transaction(tx_parts: list[str]) -> tuple[str, float | None, str | None, str]:
    desc, valor, categoria = "", None, None
    for p in tx_parts:
        if _is_value(p) and valor is None:
            valor = _parse_val(p)
        elif valor is None:
            if not _DATE_RE.match(p) and not _should_skip(p) and not desc:
                desc = p
        else:
            if not _DATE_RE.match(p) and not _is_value(p) and not _should_skip(p):
                if not categoria and len(p) < 50:
                    categoria = p

    # extract trailing installment counter from description ("AOMORI - LO04/10" → "04/10")
    parcela = "1/1"
    if desc:
        m = _PARCELA_RE.search(desc)
        if m:
            parcela = m.group(1)
            desc = desc[:m.start()].strip()

    return desc, valor, categoria, parcela


def _extract_fatura_total(parts: list[str]) -> float | None:
    for i, p in enumerate(parts):
        if "total dos lançamentos atuais" in p.lower():
            if i + 1 < len(parts) and _is_value(parts[i + 1]):
                return abs(_parse_val(parts[i + 1]))
    return None


def _extract_iof_total(parts: list[str]) -> float | None:
    for i, p in enumerate(parts):
        if "total lançamentos inter" in p.lower():
            if i + 1 < len(parts) and _is_value(parts[i + 1]):
                return _parse_val(parts[i + 1])
    return None


def _norm_desc(desc: str) -> str:
    """Strip trailing installment counter 'DD/MM' for deduplication."""
    return re.sub(r"\s*\d{2}/\d{2}\s*$", "", desc).strip()


def _parse_section(parts: list[str], year: str, comp: str, secao: str) -> list[dict]:
    records: list[dict] = []
    i = 0
    current_secao = secao

    while i < len(parts):
        p = parts[i]

        if p.lower() in _STOP_MARKERS:
            break

        # switch to "servico" when the services sub-section starts
        if "produtos e serviços" in p.lower() and "data" not in p.lower():
            current_secao = "servico"
            i += 1
            continue

        if not _DATE_RE.match(p):
            i += 1
            continue

        date = f"{p}/{year}"
        i += 1

        # collect tokens until the NEXT date — but only break on date if we
        # already have a value (installment counters like 02/10 also look like dates)
        tx_parts: list[str] = []
        while i < len(parts):
            token = parts[i]
            if token.lower() in _STOP_MARKERS:
                i = len(parts)
                break
            # section-change marker: let outer loop handle it
            if "produtos e serviços" in token.lower() and "data" not in token.lower():
                break
            has_value = any(_is_value(t) for t in tx_parts)
            if _DATE_RE.match(token) and has_value:
                break
            tx_parts.append(token)
            i += 1

        desc, valor, categoria, parcela = _parse_transaction(tx_parts)

        if desc and valor is not None:
            records.append({
                "competencia": comp,
                "data":        date,
                "descricao":   desc,
                "categoria":   categoria,
                "valor":       -valor,
                "secao":       current_secao,
                "parcela":     parcela,
            })

    return records


def parse_markdown(text: str, competencia: str) -> pd.DataFrame:
    year      = competencia[:4]
    all_parts = _all_cell_parts(text)
    nac_parts, inter_parts = _split_sections(all_parts)

    nac_records   = _parse_section(nac_parts,   year, competencia, "nacional")
    inter_records = _parse_section(inter_parts, year, competencia, "internacional")

    # use BRL+IOF total when there is exactly one international purchase
    inter_purchases = [r for r in inter_records if r["secao"] == "internacional"]
    iof_total = _extract_iof_total(inter_parts)
    if iof_total is not None and len(inter_purchases) == 1:
        inter_purchases[0]["valor"] = -iof_total

    records = nac_records + inter_records

    # some months pack current + next-month installments in the same block before
    # the stop marker (e.g. April). detect this by comparing against the fatura
    # total: if the parsed sum diverges by more than 1%, deduplicate via
    # normalised description (strips installment counter like "06/10" → same key).
    fatura_total = _extract_fatura_total(all_parts)
    parsed_total = abs(sum(r["valor"] for r in records))
    if fatura_total and parsed_total > 0 and abs(parsed_total / fatura_total - 1.0) > 0.01:
        # description is already clean (installment stripped), so use it directly
        seen: set = set()
        deduped: list[dict] = []
        for r in records:
            key = (r["data"], r["descricao"], r["valor"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        records = deduped

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["data_dt"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.sort_values("data_dt").drop(columns="data_dt").reset_index(drop=True)
    return df
