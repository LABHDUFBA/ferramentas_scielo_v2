"""
SciELO Brasil — Raspador de XMLs (e PDFs) por área temática.

Uso: python scielo_v2.py
  1. Selecione a área temática
  2. Escolha o tipo de raspagem (1=XML, 2=XML+PDF)
  3. Filtro por ano mínimo (opcional)

Estrutura:
  scielo_v2.py → revistas.py → issue_xml.py → driver_utils.py
                                                   ↳ reports.py
"""

import argparse
import os
import time

from driver_utils import criar_driver, warmup_driver, close_driver
from revistas import revistas
from reports import report_scrape
from logging_utils import configure_logging
from s3_utils import S3Uploader

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

timestr = time.strftime("%Y-%m-%d")
saveMode = ""

AREAS = {
    "1": "1",   # Ciências Agrárias
    "2": "2",   # Ciências Biológicas
    "3": "3",   # Ciências da Saúde
    "4": "4",   # Ciências Exatas e da Terra
    "5": "5",   # Ciências Humanas
    "6": "6",   # Ciências Sociais Aplicadas
    "7": "7",   # Engenharias
    "8": "8",   # Lingüística, Letras e Artes
}

AREAS_NOMES = {
    "1": "Ciências Agrárias",
    "2": "Ciências Biológicas",
    "3": "Ciências da Saúde",
    "4": "Ciências Exatas e da Terra",
    "5": "Ciências Humanas",
    "6": "Ciências Sociais Aplicadas",
    "7": "Engenharias",
    "8": "Lingüística, Letras e Artes",
}

URL_JORNAIS = "https://www.scielo.br/journals/thematic?status=current&lang=pt"


def _positive_int(value, name, minimum=0):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} deve ser um número inteiro") from exc
    if number < minimum:
        raise ValueError(f"{name} deve ser maior ou igual a {minimum}")
    return number


def _parse_args():
    parser = argparse.ArgumentParser(description="Raspador SciELO por área")
    parser.add_argument("--s3-bucket", help="Bucket S3 de destino")
    parser.add_argument("--s3-prefix", default="", help="Prefixo das chaves S3")
    parser.add_argument("--s3-endpoint-url", help="Endpoint S3 compatível (ex.: MinIO)")
    parser.add_argument("--s3-delete-local", action="store_true", help="Apaga cada arquivo local após upload S3 bem-sucedido")
    return parser.parse_args()


def main():
    global saveMode
    args = _parse_args()
    logger = configure_logging()
    uploader = S3Uploader(args.s3_bucket, args.s3_prefix, args.s3_endpoint_url, args.s3_delete_local) if args.s3_bucket else None
    area = os.getenv("SCIELO_AREA", "").strip()

    if area and area not in AREAS:
        raise ValueError("SCIELO_AREA deve ser um valor entre 1 e 8")

    while area not in AREAS:
        print("-=- Definição da área temática -=-\n")
        area = str(input(
            "- Opções:\n"
            "1- Ciências Agrárias\n"
            "2- Ciências Biológicas\n"
            "3- Ciências da Saúde\n"
            "4- Ciências Exatas e da Terra\n"
            "5- Ciências Humanas\n"
            "6- Ciências Sociais Aplicadas\n"
            "7- Engenharias\n"
            "8- Lingüística, Letras e Artes\n"
            "Digite o número correspondente à área temática que deseja raspar: \n"
        ))

    configured_mode = os.getenv("SCIELO_MODE", "").strip()
    if configured_mode:
        saveMode = _positive_int(configured_mode, "SCIELO_MODE", 1)
        if saveMode not in (1, 2):
            raise ValueError("SCIELO_MODE deve ser 1 ou 2")
    while saveMode not in (1, 2):
        print("-=" * 50)
        saveMode = int(input(
            "-=- Definição do tipo de raspagem -=-\n"
            "1- Salvar os XMLs;\n"
            "2- Salvar os XMLs e baixar os PDFs.\n"
            "Tipo de Raspagem (1 ou 2): "
        ))

    # Filtro por ano mínimo
    configured_year = os.getenv("SCIELO_ANO_MINIMO", "").strip()
    if configured_year:
        ano_minimo = _positive_int(configured_year, "SCIELO_ANO_MINIMO")
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
    logger.info(
        "Scrape started",
        extra={"event": "scrape_started", "file_path": diretorio},
    )

    # ── Cria e prepara o driver ──────────────────────────────────────────
    print("\nInicializando navegador...")
    driver = criar_driver()

    print(f"Acessando {URL_JORNAIS} ...")
    if not warmup_driver(driver):
        print("ERRO: Não foi possível carregar o SciELO (bloqueio anti-bot).")
        print("Tente rodar novamente em alguns minutos.")
        close_driver(driver)
        return

    driver.get(URL_JORNAIS)

    try:
        # Aguardar tabela de revistas
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "journals_table_body"))
            )
        except TimeoutException:
            print("ERRO: Não foi possível carregar a lista de revistas.")
            return

        # Clicar no accordion da área
        area_id = AREAS[area]
        area_nome = AREAS_NOMES[area]
        print(f"\nBuscando revistas de: {area_nome}")

        try:
            accordion_btn = driver.find_element(
                By.CSS_SELECTOR, f"#heading-{area_id} .accordion-button"
            )
            if "collapsed" in (accordion_btn.get_attribute("class") or ""):
                driver.execute_script("arguments[0].click();", accordion_btn)
                # Esperar animação
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.ID, f"collapseContent-{area_id}")
                    )
                )
                time.sleep(1)
        except NoSuchElementException:
            print(f"ERRO: Não encontrou o botão da área {area_nome}")
            return

        # Extrair dados das revistas imediatamente (evita StaleElementReference)
        area_box = driver.find_element(By.ID, f"collapseContent-{area_id}")
        journal_anchors = area_box.find_elements(
            By.CSS_SELECTOR, "a.collectionLink, a[class*='collectionLink']"
        )
        if not journal_anchors:
            journal_anchors = area_box.find_elements(
                By.CSS_SELECTOR, "a[href*='/j/']"
            )

        journals_data = []
        for j in journal_anchors:
            try:
                link = j.get_attribute("href")
                try:
                    name = j.find_element(By.CLASS_NAME, "journalTitle").text
                except NoSuchElementException:
                    name = j.text.strip()
                if link:
                    if not link.endswith("/"):
                        link = link + "/"
                    journals_data.append({
                        "name": name, "link": link, "grid": link + "grid"
                    })
            except Exception:
                continue

        print(f"\nEncontradas {len(journals_data)} revistas em {area_nome}\n")

        # Relatório
        report_scrape(diretorio, timestr, area, saveMode)

        # Processar cada revista
        for i, entry in enumerate(journals_data, 1):
            name = entry["name"]
            link = entry["link"]
            link_grid = entry["grid"]

            print(f"\n{'='*60}")
            print(f"[{i}/{len(journals_data)}] {name}")
            print(f"  Link: {link}")
            print(f"  Grid: {link_grid}")

            try:
                revistas(
                    diretorio, link, link_grid, name, saveMode, ano_minimo,
                    driver=driver, uploader=uploader
                )
            except Exception as e:
                print(f"  ✗ ERRO em {name}: {e}")
                # Não aborta — continua para a próxima revista
                continue

    except Exception as e:
        print(f"\nERRO geral: {e}")
        import traceback
        traceback.print_exc()
    finally:
        close_driver(driver)

    print("\nFim da raspagem")
    logger.info("Scrape finished", extra={"event": "scrape_finished", "file_path": diretorio})


if __name__ == "__main__":
    main()
