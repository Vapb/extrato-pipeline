"""
Gold layer: silver CSVs → CSV consolidado por owner/mês.
Saída: data/gold/{owner}/{YYYY-MM}.csv

Fluxo de enriquecimento:
  1. run()            — silver → gold (nome_simplificado/categoria = Pendente)
  2. apply_map()      — lê gold existente e aplica merchant_map.json
  run() chama apply_map() no final, então pipeline.py --layer gold faz os dois.
  pipeline.py --layer apply-map executa apenas a fase 2 (sem reler o silver).
"""
import argparse
import json
from pathlib import Path

import pandas as pd

import metadata

SILVER_ROOT       = Path("data/silver")
GOLD_ROOT         = Path("data/gold")
MERCHANT_MAPS_DIR = Path("data/merchant_maps")

SEP = ";"
GOLD_COLS = [
    "data", "nome_original", "nome_simplificado", "categoria",
    "valor", "origem", "situacao", "parcela_atual", "parcelas_total",
]
_PENDING = {"Pendente", ""}


def _load_merchant_maps() -> dict:
    """Merge todos os mapas mensais em ordem cronológica; mês mais recente ganha."""
    if not MERCHANT_MAPS_DIR.exists():
        return {}
    merged: dict[str, dict] = {}
    for path in sorted(MERCHANT_MAPS_DIR.glob("????-??.json")):
        merged.update(json.loads(path.read_text(encoding="utf-8")).get("mapeamentos", {}))
    return merged


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


def _read_gold(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path, sep=SEP, encoding="utf-8-sig", keep_default_na=False,
        dtype={"parcela_atual": str, "parcelas_total": str},
    )


def _write_gold(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=SEP, index=False, encoding="utf-8-sig")


def _json_to_df(json_path: Path) -> pd.DataFrame:
    """Migração única: converte gold JSON legado para DataFrame compatível com o CSV."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rows = []
    for e in data.get("lancamentos", []):
        rows.append({
            "data":              e.get("data", ""),
            "nome_original":     e.get("nome_original", ""),
            "nome_simplificado": e.get("nome_simplificado") or "Pendente",
            "categoria":         e.get("categoria") or "Pendente",
            "valor":             str(e.get("valor", "")),
            "origem":            e.get("origem", ""),
            "situacao":          e.get("situacao", ""),
            "parcela_atual":     str(e["parcela_atual"]) if "parcela_atual" in e else "",
            "parcelas_total":    str(e["parcelas_total"]) if "parcelas_total" in e else "",
        })
    return pd.DataFrame(rows, columns=GOLD_COLS) if rows else pd.DataFrame(columns=GOLD_COLS)


def _build_month(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Fase 1: silver → gold com nome_simplificado/categoria = Pendente."""
    df = pd.concat(frames, ignore_index=True).sort_values(["data", "descricao"]).reset_index(drop=True)
    rows = []
    for _, row in df.iterrows():
        descricao    = str(row["descricao"]) if pd.notna(row["descricao"]) else ""
        parcela      = row.get("parcela")
        account_type = str(row["account_type"])
        sit = _situacao_fields(parcela, account_type)
        rows.append({
            "data":              str(row["data"]),
            "nome_original":     descricao,
            "nome_simplificado": "Pendente",
            "categoria":         "Pendente",
            "valor":             round(float(row["valor"]), 2),
            "origem":            _origem(str(row["bank"]), account_type, descricao),
            "situacao":          sit.get("situacao", ""),
            "parcela_atual":     sit.get("parcela_atual", ""),
            "parcelas_total":    sit.get("parcelas_total", ""),
        })
    return pd.DataFrame(rows, columns=GOLD_COLS)


def _extract_manual(prev: pd.DataFrame) -> dict[tuple, dict]:
    """Extrai edições manuais (não-Pendente) de um gold anterior para preservar no rerun."""
    manual: dict[tuple, dict] = {}
    for _, e in prev.iterrows():
        simpl = str(e.get("nome_simplificado", ""))
        cat   = str(e.get("categoria", ""))
        to_keep = {}
        if simpl not in _PENDING:
            to_keep["nome_simplificado"] = simpl
        if cat not in _PENDING:
            to_keep["categoria"] = cat
        if not to_keep:
            continue
        try:
            valor_key = round(float(e["valor"]), 2)
        except (ValueError, TypeError):
            continue
        manual[(str(e["data"]), str(e["nome_original"]), valor_key)] = to_keep
    return manual


def apply_map(owner_filter: str | None = None, month_filter: str | None = None) -> None:
    """Fase 2: aplica merchant_maps/ nos CSVs gold existentes no disco."""
    mappings = _load_merchant_maps()
    if not mappings:
        return

    for csv_path in sorted(GOLD_ROOT.glob("*/*.csv")):
        owner = csv_path.parent.name
        if owner_filter and owner != owner_filter:
            continue
        month = csv_path.stem
        if month_filter and month != month_filter:
            continue

        df = _read_gold(csv_path)
        for i, row in df.iterrows():
            needs_simpl = str(row.get("nome_simplificado", "")) in _PENDING
            needs_cat   = str(row.get("categoria", "")) in _PENDING
            if not needs_simpl and not needs_cat:
                continue
            nome_simpl, categoria = _match(str(row.get("nome_original", "")), mappings)
            if needs_simpl and nome_simpl and nome_simpl not in _PENDING:
                df.at[i, "nome_simplificado"] = nome_simpl
            if needs_cat and categoria and categoria not in _PENDING:
                df.at[i, "categoria"] = categoria

        _write_gold(df, csv_path)

        mapeado = pendente = faltando = 0
        for _, row in df.iterrows():
            simpl = str(row.get("nome_simplificado", ""))
            cat   = str(row.get("categoria", ""))
            if simpl in _PENDING:
                faltando += 1
            elif cat in _PENDING:
                pendente += 1
            else:
                mapeado += 1

        total  = pd.to_numeric(df["valor"], errors="coerce").sum()
        n_pend = faltando + pendente
        print(f"  [map] {csv_path}  ({mapeado} mapeados | {pendente} pendente | {faltando} faltando | R$ {total:,.2f})")
        metadata.update(
            layer="gold", owner=owner, month=month,
            n_linhas=len(df), total_valor=float(total), n_pendente=n_pend,
        )


def run(owner_filter: str | None = None, month_filter: str | None = None) -> None:
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
        frames = [pd.read_csv(p, sep=SEP, encoding="utf-8-sig") for p in csv_paths]
        df     = _build_month(frames)
        out    = GOLD_ROOT / owner / f"{month}.csv"

        # Preserva edições manuais do gold existente por (data, nome_original, valor).
        # Fallback para JSON na primeira execução após migração.
        prev = None
        if out.exists():
            prev = _read_gold(out)
        elif (json_out := out.with_suffix(".json")).exists():
            prev = _json_to_df(json_out)

        if prev is not None:
            manual = _extract_manual(prev)
            for i, entry in df.iterrows():
                key = (str(entry["data"]), str(entry["nome_original"]), round(float(entry["valor"]), 2))
                if key in manual:
                    for col, val in manual[key].items():
                        df.at[i, col] = val

        _write_gold(df, out)
        total    = pd.to_numeric(df["valor"], errors="coerce").sum()
        n_pend   = int(df["categoria"].isin(_PENDING).sum())
        print(f"  -> {out}  ({len(df)} lançamentos | R$ {total:,.2f})")
        metadata.update(
            layer="gold", owner=owner, month=month,
            n_linhas=len(df), total_valor=float(total), n_pendente=n_pend,
        )

    apply_map(owner_filter, month_filter)


def main():
    parser = argparse.ArgumentParser(description="Gold layer — silver CSVs → CSV consolidado")
    parser.add_argument("--owner", help="Filtrar por owner (ex: person1, person2)")
    parser.add_argument("--month", help="Filtrar por mês (ex: 2026-01)")
    args = parser.parse_args()
    run(owner_filter=args.owner, month_filter=args.month)


if __name__ == "__main__":
    main()
