"""
SciELO Brasil — Raspador de XMLs (e PDFs) por revista individual.

Uso: python scielo_rev_v2.py
  Digite a abreviação da revista (ex: asoc, alm, ccrh)
  Escolha o tipo de raspagem e filtro de ano

Estrutura:
  scielo_rev_v2.py → revistas.py → issue_xml.py → driver_utils.py
                                                    ↳ reports.py
"""

import argparse
import os
import time

from driver_utils import criar_driver, warmup_driver, close_driver
from revistas import revistas
from reports import report_scrape_rev
from logging_utils import configure_logging
from s3_utils import S3Uploader

timestr = time.strftime("%Y-%m-%d")
saveMode = ""


def _parse_args():
    parser = argparse.ArgumentParser(description="Raspador SciELO por revista")
    parser.add_argument("--s3-bucket", help="Bucket S3 de destino")
    parser.add_argument("--s3-prefix", default="", help="Prefixo das chaves S3")
    parser.add_argument("--s3-endpoint-url", help="Endpoint S3 compatível (ex.: MinIO)")
    parser.add_argument("--s3-delete-local", action="store_true", help="Apaga cada arquivo local após upload S3 bem-sucedido")
    return parser.parse_args()


def _env_mode_and_year():
    mode_value = os.getenv("SCIELO_MODE", "").strip()
    year_value = os.getenv("SCIELO_ANO_MINIMO", "").strip()
    if mode_value:
        try:
            mode = int(mode_value)
        except ValueError as exc:
            raise ValueError("SCIELO_MODE deve ser 1 ou 2") from exc
        if mode not in (1, 2):
            raise ValueError("SCIELO_MODE deve ser 1 ou 2")
    else:
        mode = None
    if year_value:
        try:
            year = int(year_value)
        except ValueError as exc:
            raise ValueError("SCIELO_ANO_MINIMO deve ser um inteiro >= 0") from exc
        if year < 0:
            raise ValueError("SCIELO_ANO_MINIMO deve ser um inteiro >= 0")
    else:
        year = None
    return mode, year


def main():
    global saveMode
    args = _parse_args()
    logger = configure_logging()
    uploader = S3Uploader(args.s3_bucket, args.s3_prefix, args.s3_endpoint_url, args.s3_delete_local) if args.s3_bucket else None
    env_mode, env_year = _env_mode_and_year()

    print("-=- Definição da(s) revista(s) -=-\n")
    rev_list = []
    while True:
        abbrev = input("Digite a abreviação da revista que deseja raspar: ").strip()
        if abbrev:
            rev_list.append(abbrev)
        resp = input("Deseja inserir outra? [S/N] ").strip().lower()
        if resp in ("n", "nao", "não", "no"):
            print("-=" * 50)
            break

    saveMode = env_mode or ""
    while saveMode not in (1, 2):
        saveMode = int(input(
            "-=- Definição do tipo de raspagem -=-\n"
            "1- Salvar os XMLs;\n"
            "2- Salvar os XMLs e baixar os PDFs.\n"
            "Tipo de Raspagem (1 ou 2): "
        ))

    if env_year is not None:
        ano_minimo = env_year
    else:
        print("-=" * 50)
        filtrar = input(
            "-=- Definição de filtro por ano -=-\n"
            "Deseja filtrar por ano mínimo? (s/n): "
        ).strip().lower()
        if filtrar == "s":
            ano_input = input("Filtrar edições a partir de qual ano? [2023]: ").strip()
            try:
                ano_minimo = int(ano_input) if ano_input else 2023
            except ValueError:
                print("Ano inválido. Iniciando sem filtro de ano.")
                ano_minimo = 0
        else:
            ano_minimo = 0

    diretorio = os.path.join("scielo", timestr)
    os.makedirs(diretorio, exist_ok=True)
    logger.info("Scrape started", extra={"event": "scrape_started", "file_path": diretorio})

    report_scrape_rev(diretorio, timestr, rev_list, saveMode)

    print("\nInicializando navegador...")
    driver = criar_driver()
    try:
        if not warmup_driver(driver):
            print("ERRO: Não foi possível carregar o SciELO (bloqueio anti-bot).")
            return

        for i, revista in enumerate(rev_list, 1):
            link = f"https://www.scielo.br/j/{revista}/"
            link_grid = link + "grid"

            print(f"\n[{i}/{len(rev_list)}] {revista}")
            print(f"  Link: {link}")

            try:
                revistas(
                    diretorio, link, link_grid, revista, saveMode, ano_minimo,
                    driver=driver, uploader=uploader
                )
            except Exception as e:
                print(f"  ✗ ERRO em {revista}: {e}")
                continue
    finally:
        close_driver(driver)

    print("\nFim da raspagem")
    logger.info("Scrape finished", extra={"event": "scrape_finished", "file_path": diretorio})


if __name__ == "__main__":
    main()
