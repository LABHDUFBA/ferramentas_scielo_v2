"""
SciELO Brasil — Raspador de XMLs (e PDFs) por revista individual.

Uso: python scielo_rev_v2.py
  Digite a abreviação da revista (ex: asoc, alm, ccrh)
  Escolha o tipo de raspagem e filtro de ano

Estrutura:
  scielo_rev_v2.py → revistas.py → issue_xml.py → driver_utils.py
                                                    ↳ reports.py
"""

import os
import time

from driver_utils import criar_driver, warmup_driver
from revistas import revistas
from reports import report_scrape_rev

timestr = time.strftime("%Y-%m-%d")
saveMode = ""


def main():
    global saveMode

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

    saveMode = ""
    while saveMode not in (1, 2):
        saveMode = int(input(
            "-=- Definição do tipo de raspagem -=-\n"
            "1- Salvar os XMLs;\n"
            "2- Salvar os XMLs e baixar os PDFs.\n"
            "Tipo de Raspagem (1 ou 2): "
        ))

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

    report_scrape_rev(diretorio, timestr, rev_list, saveMode)

    print("\nInicializando navegador...")
    driver = criar_driver()

    if not warmup_driver(driver):
        print("ERRO: Não foi possível carregar o SciELO (bloqueio anti-bot).")
        driver.quit()
        return

    for i, revista in enumerate(rev_list, 1):
        link = f"https://www.scielo.br/j/{revista}/"
        link_grid = link + "grid"

        print(f"\n[{i}/{len(rev_list)}] {revista}")
        print(f"  Link: {link}")

        try:
            revistas(
                diretorio, link, link_grid, revista, saveMode, ano_minimo,
                driver=driver
            )
        except Exception as e:
            print(f"  ✗ ERRO em {revista}: {e}")
            continue

    driver.quit()
    print("\nFim da raspagem")


if __name__ == "__main__":
    main()