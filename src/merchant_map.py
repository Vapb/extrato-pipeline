"""
Fluxo de atualização do merchant_map.json a partir dos JSONs gold.

Comportamento:
  - Se merchant_map.json não existe → cria com esqueleto padrão
  - Se existe → adiciona/atualiza entradas:
      * Entrada nova → adiciona (mesmo que Pendente)
      * Entrada com valor real no merchant_map → mantém (não sobrescreve)
      * Entrada Pendente no merchant_map + valor real no gold → atualiza

Uso:
    python src/merchant_map.py
    python src/merchant_map.py --owner person1
    python src/merchant_map.py --month 2026-01
"""
import argparse
import json
import re
from pathlib import Path

_INSTALLMENT_RE = re.compile(r"\s*\d{2}/\d{2}$")

GOLD_ROOT         = Path("data/gold")
MERCHANT_MAP_PATH = Path("data/merchant_map.json")

_DEFAULT_CATEGORIAS = [
    "Restaurante",
    "Mercado",
    "Casa",
    "Gatos",
    "Bernardo",
    "Assinatura",
    "Saude",
    "Investimento",
    "Recebimento",
    "Transferencia",
    "Cartao",
    "Outro",
]


def _skeleton() -> dict:
    return {
        "_meta": {
            "descricao": "Mapeamento de lançamentos bancários → categoria + nome simplificado",
            "formato_chave": "substring do nome_original (case-insensitive)",
            "uso": "match por substring — se a chave estiver contida no nome_original, o mapeamento é aplicado",
        },
        "categorias_validas": _DEFAULT_CATEGORIAS,
        "mapeamentos": {},
    }


def _is_real(val: dict | None) -> bool:
    """True se a entrada tem valores reais (não Pendente/null)."""
    if not val:
        return False
    return val.get("nome_simplificado") not in (None, "Pendente")


def _match_real(nome_original: str, mappings: dict) -> bool:
    """True se nome_original já está coberto por uma entrada real no merchant_map."""
    low = nome_original.lower()
    return any(key.lower() in low and _is_real(val) for key, val in mappings.items())


def update(owner_filter: str | None = None, month_filter: str | None = None) -> None:
    if MERCHANT_MAP_PATH.exists():
        merchant = json.loads(MERCHANT_MAP_PATH.read_text(encoding="utf-8"))
        mode = "atualizado"
    else:
        merchant = _skeleton()
        mode = "criado"
        print(f"merchant_map.json nao encontrado — criando novo em {MERCHANT_MAP_PATH}")

    mappings = merchant.setdefault("mapeamentos", {})

    candidates: dict[str, dict] = {}
    conflicts:  dict[str, list] = {}

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

            if not nome_orig:
                continue

            key = _INSTALLMENT_RE.sub("", nome_orig).strip()
            if not key:
                continue

            # já coberto por valor real no merchant_map → não toca
            if _match_real(key, mappings):
                continue

            val = {"nome_simplificado": nome_simpl, "categoria": categoria, "_source": f"{owner}/{month}"}

            if key not in candidates:
                candidates[key] = val
            elif candidates[key]["nome_simplificado"] != nome_simpl or candidates[key]["categoria"] != categoria:
                existing = candidates[key]
                # valor real vence Pendente
                if existing["nome_simplificado"] == "Pendente" and nome_simpl != "Pendente":
                    candidates[key] = val
                elif nome_simpl == "Pendente":
                    pass  # mantém o que já temos (real ou Pendente)
                else:
                    # dois valores reais distintos → conflito
                    conflicts.setdefault(key, [existing]).append(val)

    for key in conflicts:
        candidates.pop(key, None)
        print(f"  [CONFLITO] {key!r} tem valores distintos entre meses — resolva manualmente")

    if not candidates:
        print("Nenhuma entrada nova. merchant_map.json nao alterado.")
        if mode == "criado":
            MERCHANT_MAP_PATH.write_text(
                json.dumps(merchant, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Esqueleto salvo em {MERCHANT_MAP_PATH}")
        return

    added = updated = 0
    for key, val in sorted(candidates.items()):
        existing = mappings.get(key)
        if existing and not _is_real(existing) and _is_real(val):
            mappings[key] = val
            print(f"  ~ {key!r}  Pendente -> {val['nome_simplificado']!r}  ({val['categoria']})")
            updated += 1
        elif key not in mappings:
            mappings[key] = val
            status = val['nome_simplificado']
            print(f"  + {key!r}  ->  {status!r}  ({val['categoria']})")
            added += 1

    MERCHANT_MAP_PATH.write_text(
        json.dumps(merchant, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nmerchant_map.json {mode}: {added} adicionado(s), {updated} atualizado(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Atualiza merchant_map.json a partir dos JSONs gold"
    )
    parser.add_argument("--owner", help="Filtrar por owner (ex: person1, person2)")
    parser.add_argument("--month", help="Filtrar por mês (ex: 2026-01)")
    args = parser.parse_args()
    update(owner_filter=args.owner, month_filter=args.month)


if __name__ == "__main__":
    main()
