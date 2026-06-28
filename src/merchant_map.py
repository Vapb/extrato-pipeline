"""
Sincroniza gold CSVs → merchant_maps/YYYY-MM.csv

Só escreve entradas reais (não Pendente).
Detecta quando a mesma chave aparece com valores diferentes em meses distintos.

Uso:
    python src/merchant_map.py
    python src/merchant_map.py --owner person1
    python src/merchant_map.py --month 2026-01
"""
import argparse
import re
from pathlib import Path

import pandas as pd

GOLD_ROOT         = Path("data/gold")
MERCHANT_MAPS_DIR = Path("data/merchant_maps")

_INSTALLMENT_RE = re.compile(r"\s*\d{2}/\d{2}$")


def _load_month_map(month: str) -> dict:
    csv_path = MERCHANT_MAPS_DIR / f"{month}.csv"
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", keep_default_na=False)
    return {
        str(r["nome_original"]): {
            "nome_simplificado": str(r["nome_simplificado"]),
            "categoria": str(r["categoria"]),
        }
        for _, r in df.iterrows()
        if str(r.get("nome_original", ""))
    }


def _save_month_map(month: str, mapeamentos: dict) -> None:
    MERCHANT_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    rows = [
        {"nome_original": k, "nome_simplificado": v["nome_simplificado"], "categoria": v["categoria"]}
        for k, v in sorted(mapeamentos.items())
    ]
    pd.DataFrame(rows, columns=["nome_original", "nome_simplificado", "categoria"]).to_csv(
        MERCHANT_MAPS_DIR / f"{month}.csv", sep=";", index=False, encoding="utf-8-sig"
    )


def _is_real(entry: dict | None) -> bool:
    if not entry:
        return False
    simpl = entry.get("nome_simplificado", "")
    cat   = entry.get("categoria", "")
    return (
        simpl not in ("", "Pendente")
        and not simpl.endswith("()")
        and cat not in ("", "Pendente")
    )


def update(owner_filter: str | None = None, month_filter: str | None = None) -> None:
    by_month: dict[str, dict[str, dict]] = {}

    for csv_path in sorted(GOLD_ROOT.glob("*/*.csv")):
        owner = csv_path.parent.name
        if owner_filter and owner != owner_filter:
            continue
        month = csv_path.stem
        if month_filter and month != month_filter:
            continue

        df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", keep_default_na=False)
        for _, entry in df.iterrows():
            nome_orig  = str(entry.get("nome_original", ""))
            nome_simpl = str(entry.get("nome_simplificado", "")) or "Pendente"
            categoria  = str(entry.get("categoria", "")) or "Pendente"

            val = {"nome_simplificado": nome_simpl, "categoria": categoria}
            if not nome_orig or not _is_real(val):
                continue

            key = _INSTALLMENT_RE.sub("", nome_orig).strip()
            if key:
                by_month.setdefault(month, {})[key] = val

    if not by_month:
        print("Nenhuma entrada real encontrada nos gold CSVs.")
        return

    all_existing: dict[str, dict] = {
        path.stem: _load_month_map(path.stem)
        for path in sorted(MERCHANT_MAPS_DIR.glob("????-??.csv"))
    }

    total_added = total_updated = 0

    for month, new_entries in sorted(by_month.items()):
        existing_map = all_existing.get(month, {})
        added = updated = 0

        for key, val in sorted(new_entries.items()):
            for other_month, other_map in all_existing.items():
                if other_month == month:
                    continue
                other_val = other_map.get(key)
                if other_val and other_val != val and _is_real(other_val):
                    print(
                        f"  [DUP] {key!r}: {other_val['nome_simplificado']!r} ({other_month})"
                        f" vs {val['nome_simplificado']!r} ({month})"
                    )

            existing = existing_map.get(key)
            if existing is None:
                existing_map[key] = val
                print(f"  + [{month}] {key!r}  ->  {val['nome_simplificado']!r}  ({val['categoria']})")
                added += 1
            elif not _is_real(existing):
                existing_map[key] = val
                print(f"  ~ [{month}] {key!r}  {existing.get('nome_simplificado')!r} -> {val['nome_simplificado']!r}  ({val['categoria']})")
                updated += 1

        if added or updated:
            _save_month_map(month, existing_map)
            all_existing[month] = existing_map
            print(f"  merchant_maps/{month}.csv: {added} adicionado(s), {updated} atualizado(s)\n")
            total_added   += added
            total_updated += updated

    if total_added or total_updated:
        print(f"Total: {total_added} adicionado(s), {total_updated} atualizado(s)")
    else:
        print("Nenhuma entrada nova. merchant_maps/ não alterado.")


def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza gold CSVs → merchant_maps/YYYY-MM.csv"
    )
    parser.add_argument("--owner", help="Filtrar por owner (ex: victor, ana)")
    parser.add_argument("--month", help="Filtrar por mês (ex: 2026-01)")
    args = parser.parse_args()
    update(owner_filter=args.owner, month_filter=args.month)


if __name__ == "__main__":
    main()
