"""
Ponto de entrada principal do pipeline extrato.
Uso:
    python src/pipeline.py                     # bronze + silver + gold, todos os owners
    python src/pipeline.py --owner person1     # só um owner
    python src/pipeline.py --layer bronze      # só uma camada
    python src/pipeline.py --layer gold --month 2026-01  # gold de um mês específico
"""
import argparse

import bronze
import gold
import silver


def main():
    parser = argparse.ArgumentParser(description="extrato-pipeline")
    parser.add_argument("--owner", help="Filtrar por owner (ex: person1, person2)")
    parser.add_argument("--layer", choices=["bronze", "silver", "gold", "apply-map"], help="Rodar só uma camada (apply-map re-aplica merchant_map sem reler o silver)")
    parser.add_argument("--month", help="Filtrar por mês no gold/apply-map (ex: 2026-01)")
    args = parser.parse_args()

    if args.layer == "apply-map":
        print("=== Apply Merchant Map ===")
        gold.apply_map(owner_filter=args.owner, month_filter=args.month)
        return

    if args.layer in (None, "bronze"):
        print("=== Bronze ===")
        bronze.run(owner_filter=args.owner, month_filter=args.month)

    if args.layer in (None, "silver"):
        print("\n=== Silver ===")
        silver.run(owner_filter=args.owner, month_filter=args.month)

    if args.layer in (None, "gold"):
        print("\n=== Gold ===")
        gold.run(owner_filter=args.owner, month_filter=args.month)


if __name__ == "__main__":
    main()
