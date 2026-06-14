"""
Gold layer: silver CSVs → JSON consolidado por owner/mês.
Saída: data/gold/{owner}/{YYYY-MM}.json

Fluxo de enriquecimento:
  1. run()            — silver → gold (nome_simplificado/categoria = null)
  2. apply_map()      — lê gold existente e aplica merchant_map.json
  run() chama apply_map() no final, então pipeline.py --layer gold faz os dois.
  pipeline.py --layer apply-map executa apenas a fase 2 (sem reler o silver).
"""
import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

SILVER_ROOT       = Path("data/silver")
GOLD_ROOT         = Path("data/gold")
MERCHANT_MAP_PATH = Path("data/merchant_map.json")


def _load_merchant_map() -> dict:
    if not MERCHANT_MAP_PATH.exists():
        return {"mapeamentos": {}, "categorias_validas": []}
    with MERCHANT_MAP_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _match(nome_original: str, mappings: dict) -> tuple[str | None, str | None]:
    low = nome_original.lower()
    for key, val in mappings.items():
        if key.lower() in low:
            return val.get("nome_simplificado"), val.get("categoria")
    return None, None


_BANK_DISPLAY = {"itau": "Itaú", "santander": "Santander"}


def _origem(bank: str, account_type: str, descricao: str) -> str:
    display = _BANK_DISPLAY.get(bank, bank.capitalize())
    desc    = descricao.upper()
    if account_type == "credito":
        return f"{display} Crédito"
    if bank == "itau":
        if desc.startswith("RSHOP"):      return "Itaú Débito"
        if desc.startswith("PIX TRANSF"): return "Itaú PIX"
        if desc.startswith("PIX QRS"):    return "Itaú Online"
        return "Itaú"
    if bank == "santander":
        if desc.startswith("PIX ENVIADO"): return "Santander PIX"
        return "Santander"
    return display


def _situacao_fields(parcela, account_type: str) -> dict:
    if account_type != "credito" or pd.isna(parcela):
        return {}
    p = str(parcela).strip()
    if not p or p == "1/1":
        return {"situacao": "avista"}
    try:
        atual_s, total_s = p.split("/")
        return {"situacao": "parcelado", "parcela_atual": int(atual_s), "parcelas_total": int(total_s)}
    except ValueError:
        return {"situacao": "avista"}


def _build_month(month: str, frames: list[pd.DataFrame], categorias: list) -> dict:
    """Fase 1: silver → gold com nome_simplificado/categoria = null."""
    df = pd.concat(frames, ignore_index=True).sort_values(["data", "descricao"]).reset_index(drop=True)
    lancamentos = []
    for _, row in df.iterrows():
        descricao    = str(row["descricao"]) if pd.notna(row["descricao"]) else ""
        parcela      = row.get("parcela")
        account_type = str(row["account_type"])
        entry: dict = {
            "data":              str(row["data"]),
            "nome_original":     descricao,
            "nome_simplificado": "Pendente",
            "categoria":         "Pendente",
            "valor":             round(float(row["valor"]), 2),
            "origem":            _origem(str(row["bank"]), account_type, descricao),
        }
        entry.update(_situacao_fields(parcela, account_type))
        lancamentos.append(entry)

    year, mon = month.split("-")
    fim = pd.Period(month, freq="M").end_time.date().isoformat()
    return {
        "meta": {
            "periodo":   {"inicio": f"{year}-{mon}-01", "fim": fim},
            "gerado_em": date.today().isoformat(),
        },
        "categorias_validas": categorias,
        "lancamentos": lancamentos,
    }


def apply_map(owner_filter: str | None = None, month_filter: str | None = None) -> None:
    """Fase 2: aplica merchant_map.json nos JSONs gold existentes no disco."""
    merchant = _load_merchant_map()
    mappings = merchant.get("mapeamentos", {})
    if not mappings:
        return

    for json_path in sorted(GOLD_ROOT.glob("*/*.json")):
        owner = json_path.parent.name
        if owner_filter and owner != owner_filter:
            continue
        month = json_path.stem
        if month_filter and month != month_filter:
            continue

        data = json.loads(json_path.read_text(encoding="utf-8"))
        updated = 0
        for entry in data.get("lancamentos", []):
            needs_simpl = entry.get("nome_simplificado") in (None, "Pendente")
            needs_cat   = entry.get("categoria") in (None, "Pendente")
            if not needs_simpl and not needs_cat:
                continue
            nome_simpl, categoria = _match(entry.get("nome_original", ""), mappings)
            if needs_simpl and nome_simpl not in (None, "Pendente"):
                entry["nome_simplificado"] = nome_simpl
                updated += 1
            if needs_cat and categoria not in (None, "Pendente"):
                entry["categoria"] = categoria

        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(e["valor"] for e in data["lancamentos"])
        print(f"  [map] {json_path}  ({updated} mapeados | R$ {total:,.2f})")


def run(owner_filter: str | None = None, month_filter: str | None = None) -> None:
    merchant   = _load_merchant_map()
    categorias = merchant.get("categorias_validas", [])

    groups: dict = {}
    for csv_path in sorted(SILVER_ROOT.glob("*/*.csv")):
        owner = csv_path.parent.name
        if owner_filter and owner != owner_filter:
            continue
        stem = csv_path.stem.split("_")
        if len(stem) < 3:
            continue
        month = f"{stem[0]}-{stem[1]}"
        if month_filter and month != month_filter:
            continue
        groups.setdefault((owner, month), []).append(csv_path)

    if not groups:
        print("[WARN] Nenhum CSV silver encontrado")
        return

    for (owner, month), csv_paths in sorted(groups.items()):
        frames = [pd.read_csv(p, sep=";", encoding="utf-8-sig") for p in csv_paths]
        data   = _build_month(month, frames, categorias)
        out    = GOLD_ROOT / owner / f"{month}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(e["valor"] for e in data["lancamentos"])
        print(f"  -> {out}  ({len(data['lancamentos'])} lançamentos | R$ {total:,.2f})")

    apply_map(owner_filter, month_filter)


def main():
    parser = argparse.ArgumentParser(description="Gold layer — silver CSVs → JSON consolidado")
    parser.add_argument("--owner", help="Filtrar por owner (ex: person1, person2)")
    parser.add_argument("--month", help="Filtrar por mês (ex: 2026-01)")
    args = parser.parse_args()
    run(owner_filter=args.owner, month_filter=args.month)


if __name__ == "__main__":
    main()
