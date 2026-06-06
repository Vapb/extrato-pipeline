import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

VALUE_RE  = re.compile(r"-?[\d\.]+,\d{2}")
DATE_RE   = re.compile(r"^\d{2}/\d{2}$")
COL_SPLIT = 355

SKIP_LEFT  = ["data estabelecimento", "lançamentos inter", "total para", "lançamentos produtos"]
SKIP_RIGHT = [
    "data estabelecimento", "data produtos", "titular", "lançamentos produtos",
    "dólar de conversão", "total transações", "repasse de iof",
    "próxima fatura", "demais faturas", "total para", "continua", "lançamentos inter",
]


def br_float(s: str) -> float:
    neg = s.strip().startswith("-")
    s = re.sub(r"[^\d,]", "", s).replace(",", ".")
    return (-1 if neg else 1) * float(s) if s else 0.0


def last_value(line: str) -> float | None:
    if m := re.search(r"-\s+([\d\.]+,\d{2})$", line):
        return -br_float(m.group(1))
    nums = VALUE_RE.findall(line)
    return br_float(nums[-1]) if nums else None


def group_rows(words: list, height: float, tol: int = 3) -> dict:
    rows: dict = defaultdict(list)
    for w in words:
        if w["top"] <= height:
            rows[round(w["top"] / tol) * tol].append(w)
    return {k: sorted(v, key=lambda x: x["x0"]) for k, v in sorted(rows.items())}


def _competencia_from_path(path: Path) -> str:
    if m := re.search(r"(20\d{2})_(\d{2})", path.stem):
        return f"{m.group(1)}-{m.group(2)}"
    raise ValueError(f"Não foi possível detectar ano/mês em: {path.stem}")


def _contains(pattern: str, text: str) -> bool:
    return pattern in text or pattern.replace(" ", "") in text.replace(" ", "")


def _flush(current: dict | None, records: list) -> None:
    if current:
        records.append(current)


def _make_record(comp, date_token, year, line, ws_tail, secao) -> dict:
    nums = VALUE_RE.findall(line)
    desc = " ".join(w["text"] for w in ws_tail)
    for n in nums:
        desc = desc.replace(n, "").strip()
    desc = re.sub(r"\s*\d{2}/\d{2}\s*$", "", desc).strip().strip("-").strip()
    val = last_value(line)
    return dict(competencia=comp, data=f"{date_token}/{year}",
                descricao=desc, categoria=None,
                valor=-val if val is not None else None, secao=secao)


def _parse_national(rows: dict, comp: str) -> list[dict]:
    year, records, current = comp[:4], [], None
    section = "nacional"

    for ws in rows.values():
        left = [w for w in ws if 140 <= w["x0"] < COL_SPLIT]
        if not left:
            continue
        line = " ".join(w["text"] for w in left)
        low = line.lower()

        if _contains("compras parceladas", low):
            _flush(current, records); current = None; break

        if _contains("lançamentos no cartão", low):
            _flush(current, records); current = None; continue

        if _contains("produtos e serviços", low) and not _contains("data produtos", low):
            _flush(current, records); current = None; section = "servico"; continue

        if any(_contains(s, low) for s in SKIP_LEFT):
            _flush(current, records); current = None; continue

        if DATE_RE.match(left[0]["text"]) and left[0]["x0"] < 175:
            _flush(current, records)
            current = _make_record(comp, left[0]["text"], year, line, left[1:], section)
        elif current and line.strip() and not any(s in low for s in ["total", "continua", "titular"]):
            if current["categoria"] is None:
                current["categoria"] = line.strip()

    _flush(current, records)
    return records


def _parse_international(rows: dict, comp: str) -> list[dict]:
    year, records, current = comp[:4], [], None
    section, iof_total = "pre", None

    for ws in rows.values():
        right = [w for w in ws if w["x0"] >= COL_SPLIT]
        if not right:
            continue
        line = " ".join(w["text"] for w in right)
        low = line.lower()

        if "total lançamentos inter" in low:
            if nums := VALUE_RE.findall(line):
                iof_total = br_float(nums[-1])
            continue

        if section == "pre":
            if "lançamentos internacionais" in low:
                section = "internacional"
            continue

        if "produtos e serviços" in low and "data" not in low:
            _flush(current, records); current = None; section = "servico"; continue

        if "compras parceladas" in low or "total dos lançamentos" in low:
            _flush(current, records); break

        if any(s in low for s in SKIP_RIGHT):
            continue

        if DATE_RE.match(right[0]["text"]) and right[0]["x0"] < 430:
            _flush(current, records)
            current = _make_record(comp, right[0]["text"], year, line, right[1:], section)
        elif current and line.strip() and current["categoria"] is None:
            current["categoria"] = line.strip()

    _flush(current, records)

    inter = [r for r in records if r["secao"] == "internacional"]
    if iof_total is not None and len(inter) == 1:
        inter[0]["valor"] = -iof_total

    return records


def process_pdf(pdf_path: Path) -> pd.DataFrame:
    comp = _competencia_from_path(pdf_path)
    nac, inter = [], []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[1:]:
            rows = group_rows(page.extract_words(), page.height)
            nac.extend(_parse_national(rows, comp))
            inter.extend(_parse_international(rows, comp))

    records = nac + inter
    print(f"  {pdf_path.name}: nacionais={len(nac)} inter/serviço={len(inter)} total={len(records)}")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["data_dt"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.sort_values("data_dt").drop(columns="data_dt").reset_index(drop=True)
    return df
