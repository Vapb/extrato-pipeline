import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

DATE_RE  = re.compile(r"^\d{2}/\d{2}$")
VALUE_RE = re.compile(r"\d[\d\.]*,\d{2}-?$")

# limites de coluna (x0)
DATE_MAX = 50      # data:  x0 < 50
DESC_MAX = 295     # desc:  50 <= x0 < 295
VAL_MIN  = 408     # valor: 408 <= x0 < 508
BAL_MIN  = 508     # saldo: x0 >= 508  (ignorado)

SKIP_DESC = {"descrição", "movimentação", "conta corrente"}
SKIP_PREFIXES = ("resumo -", "extrato")


def parse_value(s: str | None) -> float | None:
    if not s:
        return None
    s = s.strip()
    if not VALUE_RE.search(s):
        return None
    neg = s.endswith("-")
    cleaned = re.sub(r"[^\d,]", "", s).replace(",", ".")
    return (-1 if neg else 1) * float(cleaned) if cleaned else None


def group_rows(words: list, height: float, tol: int = 3) -> dict:
    rows: dict = defaultdict(list)
    for w in words:
        if w["top"] <= height:
            rows[round(w["top"] / tol) * tol].append(w)
    return {k: sorted(v, key=lambda x: x["x0"]) for k, v in sorted(rows.items())}


def competencia_from_path(path: Path) -> str:
    if m := re.search(r"(20\d{2})_(\d{2})", path.stem):
        return f"{m.group(1)}-{m.group(2)}"
    raise ValueError(f"Não foi possível detectar ano/mês em: {path.stem}")


def _should_skip(desc: str) -> bool:
    low = desc.lower()
    return low in SKIP_DESC or any(low.startswith(p) for p in SKIP_PREFIXES)


def process_pdf(pdf_path: Path) -> pd.DataFrame:
    comp = competencia_from_path(pdf_path)
    year = comp[:4]
    records = []
    current: dict | None = None
    last_date: str | None = None

    done = False
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if done:
                break
            rows = group_rows(page.extract_words(), page.height)

            for ws in rows.values():
                date_ws = [w for w in ws if w["x0"] < DATE_MAX]
                desc_ws = [w for w in ws if DATE_MAX <= w["x0"] < DESC_MAX]
                val_ws  = [w for w in ws if VAL_MIN  <= w["x0"] < BAL_MIN]

                date_text = date_ws[0]["text"] if date_ws and DATE_RE.match(date_ws[0]["text"]) else None
                desc_text = " ".join(w["text"] for w in desc_ws).strip()
                val_text  = next((w["text"] for w in reversed(val_ws) if VALUE_RE.search(w["text"])), None)

                if not desc_text:
                    continue

                # "SALDO EM DD/MM" marks the closing balance — end of transaction data.
                # Guard against the opening-balance line from the prior month that
                # appears before any transactions (records and current both empty).
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
                    valor = parse_value(val_text)
                    if valor:
                        current = {
                            "competencia": comp,
                            "data": f"{date_text}/{year}",
                            "descricao": desc_text,
                            "valor": valor,
                        }
                    else:
                        current = None   # comprovante sem movimento (INTERNET BANKING, etc.)

                elif val_text:
                    # linha sem data mas com valor próprio (REMUNERACAO, etc.)
                    if current:
                        records.append(current)
                    current = {
                        "competencia": comp,
                        "data": f"{last_date}/{year}" if last_date else None,
                        "descricao": desc_text,
                        "valor": parse_value(val_text),
                    }

                elif current:
                    # continuação de descrição (nome do destinatário PIX, CNPJ, etc.)
                    if re.search(r"[A-Za-zÀ-ÿ]", desc_text):
                        current["descricao"] += " " + desc_text

    if current:
        records.append(current)

    n = len(records)
    total = sum(r["valor"] for r in records if r["valor"])
    print(f"{pdf_path.name}  transações: {n} | saldo líquido: R$ {total:,.2f}")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["data_dt"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.sort_values("data_dt").drop(columns="data_dt").reset_index(drop=True)
    return df


def save_csv(df: pd.DataFrame, pdf_path: Path) -> Path:
    out = Path(f"data/bronze/santander/debito/{pdf_path.stem}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df_out = df.copy()
    df_out["data"] = pd.to_datetime(df_out["data"], dayfirst=True).dt.strftime("%d/%m/%Y")
    df_out.to_csv(out, index=False, sep=";", encoding="utf-8-sig")
    return out


def main():
    parser = argparse.ArgumentParser(description="Extrai extratos Santander Débito (PDF -> CSV)")
    parser.add_argument("pdfs", nargs="+", help="Um ou mais PDFs de extrato Santander")
    args = parser.parse_args()

    frames = []
    for raw in args.pdfs:
        path = Path(raw)
        if not path.exists():
            print(f"[WARN] Não encontrado: {path}"); continue
        df = process_pdf(path)
        if df.empty:
            print(f"[WARN] Sem transações: {path.name}"); continue
        out = save_csv(df, path)
        print(f"  -> {out}")
        frames.append(df)

    if len(frames) > 1:
        total = pd.concat(frames, ignore_index=True)
        print(f"\nTotal geral: {len(total)} registros")


if __name__ == "__main__":
    main()
