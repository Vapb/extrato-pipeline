"""
Sincroniza gold JSONs → merchant_maps/YYYY-MM.json

Só escreve entradas reais (não Pendente). Entradas em nao_mapear.json são ignoradas.
Detecta quando a mesma chave aparece com valores diferentes em meses distintos.

Uso:
    python src/merchant_map.py
    python src/merchant_map.py --owner person1
    python src/merchant_map.py --month 2026-01
"""
import argparse
import json
import re
from pathlib import Path

GOLD_ROOT         = Path("data/gold")
MERCHANT_MAPS_DIR = Path("data/merchant_maps")

_INSTALLMENT_RE = re.compile(r"\s*\d{2}/\d{2}$")


def _load_month_map(month: str) -> dict:
    path = MERCHANT_MAPS_DIR / f"{month}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("mapeamentos", {})
    return {}


def _save_month_map(month: str, mapeamentos: dict) -> None:
    MERCHANT_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    path = MERCHANT_MAPS_DIR / f"{month}.json"
    path.write_text(
        json.dumps({"mes": month, "mapeamentos": mapeamentos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update(owner_filter: str | None = None, month_filter: str | None = None) -> None:
    # Coleta entradas reais dos gold JSONs, agrupadas por mês
    by_month: dict[str, dict[str, dict]] = {}

    for json_path in sorted(GOLD_ROOT.glob("*/*.json")):
        owner = json_path.parent.name
        if owner_filter and owner != owner_filter:
            continue
        month = json_path.stem
        if month_filter and month != month_filter:
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))
        for entry in data.get("lancamentos", []):
            nome_orig  = entry.get("nome_original", "")
            nome_simpl = entry.get("nome_simplificado") or "Pendente"
            categoria  = entry.get("categoria") or "Pendente"

            if not nome_orig or nome_simpl == "Pendente" or categoria == "Pendente":
                continue

            key = _INSTALLMENT_RE.sub("", nome_orig).strip()
            if not key:
                continue

            by_month.setdefault(month, {})[key] = {
                "nome_simplificado": nome_simpl,
                "categoria": categoria,
            }

    if not by_month:
        print("Nenhuma entrada real encontrada nos gold JSONs.")
        return

    # Carrega todos os mapas existentes para detecção de conflitos
    all_existing: dict[str, dict] = {
        path.stem: json.loads(path.read_text(encoding="utf-8")).get("mapeamentos", {})
        for path in sorted(MERCHANT_MAPS_DIR.glob("????-??.json"))
    }

    total_added = total_updated = 0

    for month, new_entries in sorted(by_month.items()):
        existing_map = _load_month_map(month)
        added = updated = 0

        for key, val in sorted(new_entries.items()):
            # Detecta conflito com outros meses
            for other_month, other_map in all_existing.items():
                if other_month == month:
                    continue
                other_val = other_map.get(key)
                if other_val and other_val != val:
                    print(
                        f"  [DUP] {key!r}: {other_val['nome_simplificado']!r} ({other_month})"
                        f" vs {val['nome_simplificado']!r} ({month})"
                    )

            existing = existing_map.get(key)
            simpl = (existing or {}).get("nome_simplificado") or ""
            cat   = (existing or {}).get("categoria") or ""
            existing_is_pendente = existing is None or (
                simpl in (None, "Pendente") or simpl.endswith("()")
                or cat in (None, "Pendente")
            )
            if existing is None:
                existing_map[key] = val
                print(f"  + [{month}] {key!r}  ->  {val['nome_simplificado']!r}  ({val['categoria']})")
                added += 1
            elif existing_is_pendente and existing != val:
                existing_map[key] = val
                print(f"  ~ [{month}] {key!r}  {existing.get('nome_simplificado')!r} -> {val['nome_simplificado']!r}  ({val['categoria']})")
                updated += 1

        if added or updated:
            _save_month_map(month, existing_map)
            print(f"  merchant_maps/{month}.json: {added} adicionado(s), {updated} atualizado(s)\n")
            total_added   += added
            total_updated += updated

    if total_added or total_updated:
        print(f"Total: {total_added} adicionado(s), {total_updated} atualizado(s)")
    else:
        print("Nenhuma entrada nova. merchant_maps/ não alterado.")


def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza gold JSONs → merchant_maps/YYYY-MM.json"
    )
    parser.add_argument("--owner", help="Filtrar por owner (ex: victor, ana)")
    parser.add_argument("--month", help="Filtrar por mês (ex: 2026-01)")
    args = parser.parse_args()
    update(owner_filter=args.owner, month_filter=args.month)


if __name__ == "__main__":
    main()
