"""
Atualiza data/metadata.csv com stats de cada materialização do pipeline.
Cada chamada a update() sobrescreve só a linha correspondente (layer+owner+bank+account_type+month).
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

METADATA_PATH = Path("data/metadata.csv")
SEP = ";"
COLS = [
    "layer", "owner", "bank", "account_type", "month",
    "n_linhas", "total_valor", "n_pendente", "gerado_em",
]


def update(
    *,
    layer: str,
    owner: str,
    month: str,
    n_linhas: int,
    total_valor: float,
    bank: str = "",
    account_type: str = "",
    n_pendente: int | None = None,
) -> None:
    if METADATA_PATH.exists():
        df = pd.read_csv(METADATA_PATH, sep=SEP, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=COLS)

    row = {
        "layer":        layer,
        "owner":        owner,
        "bank":         bank,
        "account_type": account_type,
        "month":        month,
        "n_linhas":     str(n_linhas),
        "total_valor":  f"{total_valor:.2f}",
        "n_pendente":   "" if n_pendente is None else str(n_pendente),
        "gerado_em":    datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    mask = (
        (df["layer"] == layer) &
        (df["owner"] == owner) &
        (df["bank"] == bank) &
        (df["account_type"] == account_type) &
        (df["month"] == month)
    )

    if mask.any():
        for col, val in row.items():
            df.loc[mask, col] = val
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    (
        df.sort_values(["month", "owner", "layer", "bank", "account_type"])
          .to_csv(METADATA_PATH, sep=SEP, index=False, encoding="utf-8-sig")
    )
