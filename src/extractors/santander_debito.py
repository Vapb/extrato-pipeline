import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

DATE_RE  = re.compile(r"^\d{2}/\d{2}$")
VALUE_RE = re.compile(r"\d[\d\.]*,\d{2}-?$")

DATE_MAX = 50
DESC_MAX = 295
VAL_MIN  = 408
BAL_MIN  = 508

SKIP_DESC     = {"descrição", "movimentação", "conta corrente"}
SKIP_PREFIXES = ("resumo -", "extrato")


def _parse_value(s: str | None) -> float | None:
    if not s:
        return None
    s = s.strip()
    if not VALUE_RE.search(s):
        return None
    neg = s.endswith("-")
    cleaned = re.sub(r"[^\d,]", "", s).replace(",", ".")
    return (-1 if neg else 1) * float(cleaned) if cleaned else None


def _group_rows(words: list, height: float, tol: int = 3) -> dict:
    rows: dict = defaultdict(list)
    for w in words:
        if w["top"] <= height:
            rows[round(w["top"] / tol) * tol].append(w)
    return {k: sorted(v, key=lambda x: x["x0"]) for k, v in sorted(rows.items())}


def _competencia_from_path(path: Path) -> str:
    if m := re.search(r"(20\d{2})_(\d{2})", path.stem):
        return f"{m.group(1)}-{m.group(2)}"
    raise ValueError(f"Não foi possível detectar ano/mês em: {path.stem}")


def _should_skip(desc: str) -> bool:
    low = desc.lower()
    return low in SKIP_DESC or any(low.startswith(p) for p in SKIP_PREFIXES)


def process_pdf(pdf_path: Path) -> pd.DataFrame:
    comp = _competencia_from_path(pdf_path)
    year = comp[:4]
    records = []
    current: dict | None = None
    last_date: str | None = None
    done = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if done:
                break
            rows = _group_rows(page.extract_words(), page.height)

            for ws in rows.values():
                date_ws = [w for w in ws if w["x0"] < DATE_MAX]
                desc_ws = [w for w in ws if DATE_MAX <= w["x0"] < DESC_MAX]
                val_ws  = [w for w in ws if VAL_MIN  <= w["x0"] < BAL_MIN]

                date_text = date_ws[0]["text"] if date_ws and DATE_RE.match(date_ws[0]["text"]) else None
                desc_text = " ".join(w["text"] for w in desc_ws).strip()
                val_text  = next((w["text"] for w in reversed(val_ws) if VALUE_RE.search(w["text"])), None)

                if not desc_text:
                    continue

                # closing balance marks end of transactions
                if desc_text.lower().startswith("saldo em") and (records or current):
                    if current:
                        records.append(current)
                    current = None
                    done = True
                    break

                if _should_skip(desc_text):
                    continue

                if date_text:
                    if current:
                        records.append(current)
                    last_date = date_text
                    valor = _parse_value(val_text)
                    current = {
                        "competencia": comp,
                        "data":        f"{date_text}/{year}",
                        "descricao":   desc_text,
                        "valor":       valor,
                    } if valor else None

                elif val_text:
                    if current:
                        records.append(current)
                    current = {
                        "competencia": comp,
                        "data":        f"{last_date}/{year}" if last_date else None,
                        "descricao":   desc_text,
                        "valor":       _parse_value(val_text),
                    }

                elif current and re.search(r"[A-Za-zÀ-ÿ]", desc_text):
                    current["descricao"] += " " + desc_text

    if current:
        records.append(current)

    total = sum(r["valor"] for r in records if r["valor"])
    print(f"  {pdf_path.name}: transações={len(records)} saldo=R${total:,.2f}")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["data_dt"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.sort_values("data_dt").drop(columns="data_dt").reset_index(drop=True)
    return df
