import re
from pathlib import Path

import pandas as pd

# |DD/MM/YYYY|description|**value**||  — transaction row
_ROW_RE  = re.compile(r"^\|(\d{2}/\d{2}/\d{4})\|(.+?)\|\*\*(-?[\d\.,]+)\*\*\|\|")
_SKIP    = {"SALDO DO DIA"}


def parse_markdown(text: str, competencia: str = "") -> pd.DataFrame:
    records = []
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        date, desc, valor_str = m.group(1), m.group(2).strip(), m.group(3)
        if desc.upper() in _SKIP:
            continue
        records.append({
            "data":      date,
            "descricao": desc,
            "valor":     float(valor_str.replace(".", "").replace(",", ".")),
        })
    return pd.DataFrame(records) if records else pd.DataFrame()
