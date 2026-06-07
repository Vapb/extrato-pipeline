import re

import pandas as pd

_STRIP_RE  = re.compile(r"\*\*|~~")
_ROW_RE    = re.compile(r"^\|([^|]+)\|\|$")         # |content|| — [^|] prevents matching multi-column rows
_DATE_RE   = re.compile(r"^(\d{2}/\d{2})\s*$")
_VALUE_RE  = re.compile(r"^(\d[\d\.]*,\d{2})(-?)$")

_SKIP_DESC = {"saldo em", "descrição", "movimentação", "conta corrente", "---"}


def _clean(s: str) -> str:
    return _STRIP_RE.sub("", s).strip()


def _extract_value(parts: list[str]) -> tuple[float | None, bool]:
    """Returns (valor, is_negative) scanning left-to-right through parts."""
    for i, p in enumerate(parts):
        m = _VALUE_RE.match(p)
        if m:
            valor = float(m.group(1).replace(".", "").replace(",", "."))
            neg = m.group(2) == "-"
            # strikethrough format: value and dash are separate parts
            if not neg and i + 1 < len(parts) and parts[i + 1] == "-":
                neg = True
            return valor, neg
    return None, False


def _build_desc(parts: list[str]) -> str:
    """Collects description tokens before the first numeric value."""
    desc_parts = []
    for p in parts:
        if _VALUE_RE.match(p):
            break
        if p not in ("-", "") and not re.match(r"^\d{6,}$", p):
            desc_parts.append(p)
    return " ".join(desc_parts).strip()


def parse_markdown(text: str, competencia: str) -> pd.DataFrame:
    year = competencia[:4]
    records: list[dict] = []
    last_date: str | None = None

    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue

        # stop at closing balance ("SALDO EM DD/MM") — only after some records exist
        first_part = _clean(m.group(1).split("<br>")[0])
        if first_part.lower().startswith("saldo em") and records:
            break

        cell  = m.group(1)
        parts = [_clean(p) for p in cell.split("<br>") if _clean(p)]
        if not parts:
            continue

        # determine date and remaining parts
        dm = _DATE_RE.match(parts[0])
        if dm:
            last_date    = f"{dm.group(1)}/{year}"
            data_parts   = parts[1:]
        else:
            data_parts   = parts

        if not data_parts or last_date is None:
            continue

        valor, neg = _extract_value(data_parts)

        if valor is None:
            # description continuation — append to last record
            extra = " ".join(p for p in data_parts if p not in ("-",) and re.search(r"[A-Za-zÀ-ÿ]", p))
            if records and extra:
                records[-1]["descricao"] += " " + extra
            continue

        desc = _build_desc(data_parts)

        if not desc or any(desc.lower().startswith(s) for s in _SKIP_DESC):
            continue

        records.append({
            "competencia": competencia,
            "data":        last_date,
            "descricao":   desc,
            "valor":       -valor if neg else valor,
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["data_dt"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.sort_values("data_dt").drop(columns="data_dt").reset_index(drop=True)
    return df
