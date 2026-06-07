"""
Ponto de entrada principal do pipeline extrato.
Uso:
    python src/pipeline.py                  # bronze + silver, todos os owners
    python src/pipeline.py --owner person   # só um owner
    python src/pipeline.py --layer bronze   # só uma camada
"""
import argparse

import bronze
import silver


def main():
    parser = argparse.ArgumentParser(description="extrato-pipeline")
    parser.add_argument("--owner", help="Filtrar por owner (ex: person1, person2)")
    parser.add_argument("--layer", choices=["bronze", "silver"], help="Rodar só uma camada")
    args = parser.parse_args()

    if args.layer in (None, "bronze"):
        print("=== Bronze ===")
        bronze.run(owner_filter=args.owner)

    if args.layer in (None, "silver"):
        print("\n=== Silver ===")
        silver.run(owner_filter=args.owner)


if __name__ == "__main__":
    main()
