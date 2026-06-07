import argparse
import re
from pathlib import Path

import pandas as pd

BRONZE_ROOT = Path("data/bronze")
SILVER_ROOT = Path("data/silver")

SILVER_COLS = [
    "owner", "bank", "account_type", "competencia",
    "data", "descricao", "valor",
    "categoria", "secao", "parcela", "moeda",
]


def _normalize(df: pd.DataFrame, owner: str, bank: str, account_type: str, comp: str) -> pd.DataFrame:
    df = df.copy()

    df["owner"]        = owner
    df["bank"]         = bank
    df["account_type"] = account_type
    df["moeda"]        = "BRL"

    if "competencia" not in df.columns:
        df["competencia"] = comp

    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")

    if "categoria" not in df.columns:
        df["categoria"] = None
    if "secao" not in df.columns:
        df["secao"] = None
    if "parcela" not in df.columns:
        df["parcela"] = None

    return df[SILVER_COLS]


def run(owner_filter: str | None = None) -> None:
    # agrupa todos os CSVs bronze por (owner, bank, competencia) para mesclar debito+credito
    groups: dict = {}

    for csv_path in sorted(BRONZE_ROOT.glob("*/*/*/*.csv")):
        parts = csv_path.relative_to(BRONZE_ROOT).parts
        owner, bank, account_type = parts[0], parts[1], parts[2]

        if owner_filter and owner != owner_filter:
            continue

        m = re.match(r"(\d{4})_(\d{2})", csv_path.stem)
        if not m:
            print(f"[SKIP] Nome inesperado: {csv_path.name}")
            continue
        comp = f"{m.group(1)}-{m.group(2)}"

        groups.setdefault((owner, bank, comp), []).append((csv_path, account_type))

    if not groups:
        print(f"[WARN] Nenhum CSV encontrado em {BRONZE_ROOT}")
        return

    for (owner, bank, comp), sources in sorted(groups.items()):
        frames = []
        for csv_path, account_type in sources:
            df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig")
            frames.append(_normalize(df, owner, bank, account_type, comp))

        merged = pd.concat(frames, ignore_index=True).sort_values("data").reset_index(drop=True)

        year_month = comp.replace("-", "_")
        out = SILVER_ROOT / owner / f"{year_month}_{bank}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(out, index=False, sep=";", encoding="utf-8-sig")
        total = merged["valor"].sum()
        print(f"  -> {out}  ({len(merged)} linhas | R$ {total:,.2f})")


def main():
    parser = argparse.ArgumentParser(description="Silver layer — normaliza CSVs bronze")
    parser.add_argument("--owner", help="Processar só um owner (ex: person1, person2)")
    args = parser.parse_args()
    run(owner_filter=args.owner)


if __name__ == "__main__":
    main()
