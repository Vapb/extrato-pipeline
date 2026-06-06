import re
import csv
import argparse
import logging

from pathlib import Path
from collections import defaultdict

import pdfplumber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


LINE_REGEX = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?[\d\.]+,\d{2})$")


IGNORED_TERMS = ["SALDO DO DIA"]


def should_ignore_line(line: str) -> bool:
    line_upper = line.upper()
    return any(term in line_upper for term in IGNORED_TERMS)

''
def parse_pdf(pdf_path: str):
    logger.info(f"Abrindo PDF: {pdf_path}")
    
    transactions = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            logger.info(f"Processando página " f"{page_number}/{total_pages}")
            text = page.extract_text()

            if not text:
                logger.warning(f"Página {page_number} sem texto")
                continue

            lines = text.split("\n")
            for line in lines:
                line = line.strip()

                if not line or should_ignore_line(line):
                    continue

                match = LINE_REGEX.match(line)

                if not match:
                    continue

                data, descricao, valor = match.groups()

                valor_float = float(valor.replace(".", "").replace(",", "."))

                transactions.append(
                    {
                        "data": data,
                        "descricao": descricao.strip(),
                        "valor": valor_float,
                    }
                )

    logger.info(f"Total de transações extraídas: " f"{len(transactions)}")

    return transactions


def split_transactions_by_month(transactions):
    grouped = defaultdict(list)

    for transaction in transactions:
        data = transaction["data"]
        _, month, year = data.split("/")
        key = f"{year}_{month}"
        grouped[key].append(transaction)

    return grouped


def person_from_path(path: Path) -> str:
    parts = Path(path).resolve().parts
    try:
        idx = next(i for i, p in enumerate(parts) if p == "raw_data")
        return parts[idx + 1]
    except (StopIteration, IndexError):
        raise ValueError(
            f"Estrutura de caminho inválida: {path}\n"
            "Esperado: raw_data/{pessoa}/banco/modalidade/arquivo.pdf"
        )


def write_monthly_csvs(grouped_transactions, bank, account_type, person):
    for year_month, transactions in grouped_transactions.items():

        output_dir = Path(f"data/bronze/{person}/{bank}/{account_type}")

        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{year_month}_{bank}_{account_type}.csv"

        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:

            writer = csv.DictWriter(csvfile, fieldnames=["data", "descricao", "valor"])

            writer.writeheader()
            writer.writerows(transactions)

        logger.info(f"CSV salvo: {output_path} " f"({len(transactions)} transações)")


def main():

    parser = argparse.ArgumentParser(
        description=("Parser Itaú Débito " "PDF -> Bronze CSV")
    )

    parser.add_argument("pdf", help="Caminho do PDF")

    args = parser.parse_args()

    pdf_path = Path(args.pdf)

    if not pdf_path.exists():
        logger.error(f"Arquivo não encontrado: " f"{pdf_path}")
        raise FileNotFoundError(f"Arquivo não encontrado: " f"{pdf_path}")

    person = person_from_path(pdf_path)
    transactions = parse_pdf(pdf_path)
    grouped_transactions = split_transactions_by_month(transactions)
    write_monthly_csvs(grouped_transactions, bank="itau", account_type="debito", person=person)

    logger.info("Processo finalizado")


if __name__ == "__main__":
    main()
