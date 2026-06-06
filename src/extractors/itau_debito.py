import re
from pathlib import Path

import pandas as pd
import pdfplumber

LINE_REGEX    = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?[\d\.]+,\d{2})$")
IGNORED_TERMS = ["SALDO DO DIA"]


def _should_ignore(line: str) -> bool:
    return any(term in line.upper() for term in IGNORED_TERMS)


def process_pdf(pdf_path: Path) -> pd.DataFrame:
    records = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = line.strip()
                if not line or _should_ignore(line):
                    continue
                m = LINE_REGEX.match(line)
                if not m:
                    continue
                data, descricao, valor = m.groups()
                records.append({
                    "data":      data,
                    "descricao": descricao.strip(),
                    "valor":     float(valor.replace(".", "").replace(",", ".")),
                })

    print(f"  {pdf_path.name}: transações={len(records)}")
    return pd.DataFrame(records) if records else pd.DataFrame()
