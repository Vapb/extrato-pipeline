"""
Bronze layer: PDF → Markdown (data/markdown/) → DataFrame → CSV (data/bronze/)
Estrutura esperada: data/raw_data/{owner}/{bank}/{account_type}/*.pdf
"""
import argparse
import re
from pathlib import Path

import pandas as pd
import pymupdf4llm

from extractors import itau_credito, itau_debito, santander_debito

LANDING_ROOT  = Path("data/raw_data")
MARKDOWN_ROOT = Path("data/markdown")
BRONZE_ROOT   = Path("data/bronze")

# each extractor receives (text: str, competencia: str) and returns a DataFrame
EXTRACTORS = {
    ("itau",      "credito"): itau_credito.parse_markdown,
    ("itau",      "debito"):  itau_debito.parse_markdown,
    ("santander", "debito"):  santander_debito.parse_markdown,
}


def _competencia_from_path(path: Path) -> str:
    m = re.search(r"(20\d{2})_(\d{2})", path.stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


def _pdf_to_markdown(pdf_path: Path, md_path: Path) -> str:
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")
    md = pymupdf4llm.to_markdown(str(pdf_path))
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    return md


def _save(df: pd.DataFrame, owner: str, bank: str, account_type: str) -> None:
    df = df.copy()
    if "competencia" not in df.columns:
        df["competencia"] = pd.to_datetime(df["data"], dayfirst=True).dt.strftime("%Y-%m")

    for comp, group in df.groupby("competencia"):
        year_month = comp.replace("-", "_")
        out = BRONZE_ROOT / owner / bank / account_type / f"{year_month}_{bank}_{account_type}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        g = group.copy()
        g["data"] = pd.to_datetime(g["data"], dayfirst=True).dt.strftime("%d/%m/%Y")
        g.to_csv(out, index=False, sep=";", encoding="utf-8-sig")
        total = group["valor"].sum()
        print(f"  -> {out}  ({len(group)} linhas | R$ {total:,.2f})")


def run(owner_filter: str | None = None) -> None:
    pdfs = sorted(LANDING_ROOT.glob("*/*/*/*.pdf"))
    if not pdfs:
        print(f"[WARN] Nenhum PDF encontrado em {LANDING_ROOT}")
        return

    for pdf in pdfs:
        parts    = pdf.relative_to(LANDING_ROOT).parts
        owner, bank, account_type = parts[0], parts[1], parts[2]

        if owner_filter and owner != owner_filter:
            continue

        key = (bank, account_type)
        if key not in EXTRACTORS:
            print(f"[SKIP] Sem extractor para {bank}/{account_type} ({pdf.name})")
            continue

        comp    = _competencia_from_path(pdf)
        md_path = MARKDOWN_ROOT / owner / bank / account_type / pdf.with_suffix(".md").name

        text = _pdf_to_markdown(pdf, md_path)
        df = EXTRACTORS[key](text, comp)
        if df.empty:
            print(f"  [WARN] Sem transações: {pdf.name}")
            continue
        _save(df, owner, bank, account_type)


def main():
    parser = argparse.ArgumentParser(description="Bronze layer — PDF → Markdown → CSV")
    parser.add_argument("--owner", help="Processar só um owner (ex: victor, ana)")
    args = parser.parse_args()
    run(owner_filter=args.owner)


if __name__ == "__main__":
    main()
