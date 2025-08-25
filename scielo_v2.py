from revistas import revistas
from reports import report_scrape
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

timestr = time.strftime("%Y-%m-%d")
saveMode = ""


def main():
    global saveMode
    while saveMode not in (1, 2):
        url = "https://www.scielo.br/journals/thematic?status=current&lang=pt"

        print("-=- Definição da área temática -=-\n")
        area = str(
            input(
                "- Opções:\n"
                "1- Ciências Agrárias\n"
                "2- Ciências Biológicas\n"
                "3- Ciências da Saúde\n"
                "4- Ciências Exatas e da Terra\n"
                "5- Ciências Humanas\n"
                "6- Ciências Sociais Aplicadas\n"
                "7- Engenharias\n"
                "8- Linguística, Letras e Artes\n"
                "Digite o número correspondente à área temática que deseja raspar: \n"
            )
        )
        print("-=" * 50)
        saveMode = int(
            input(
                "-=- Definição do tipo de raspagem -=-\n"
                "1- Salvar os XMLs;\n"
                "2- Salvar os XMLs e baixar os PDFs.\n"
                "Tipo de Raspagem (1 ou 2): "
            )
        )

        # Opção de filtrar (ou não) por ano
        print("-=" * 50)
        filtrar = input(
                "-=- Definição de filtro por ano -=-\n"
                "Deseja filtrar por ano mínimo? (s/n): ").strip().lower()
        if filtrar == "s":
            ano_input = input("Filtrar edições a partir de qual ano? [2023]: ").strip()
            try:
                ano_minimo = int(ano_input) if ano_input else 2023
            except ValueError:
                print("Ano inválido. Iniciando sem filtro de ano.")
                ano_minimo = 0
        else:
            # 0 = sem filtro (qualquer ano será >= 0)
            ano_minimo = 0

        diretorio = os.path.join("scielo", timestr)
        if not os.path.exists(diretorio):
            os.makedirs(diretorio)

        firefox_options = Options()
        firefox_options.add_argument("-lang=pt-BR")
        firefox_options.add_argument("--headless")
        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--start-maximized")

        driver = webdriver.Firefox(options=firefox_options)
        driver.get(url)

        # Aceitar cookies, se aparecer banner
        try:
            driver.find_element(By.CLASS_NAME, "alert-cookie-notification")
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (
                        By.CSS_SELECTOR,
                        "a#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, "
                        "div.alert-cookie-notification a",
                    )
                )
            ).click()
        except Exception:
            pass

        journal_table = driver.find_element(By.ID, "journals_table_body")
        tematica = journal_table.find_element(By.ID, f"heading-{area}")
        print(f"\n-=- {tematica.text} -=-")

        _ = tematica.find_element(By.XPATH, "following-sibling::div").find_element(
            By.TAG_NAME, "table"
        )
        time.sleep(1)
        area_box = driver.find_element(By.ID, f"collapseContent-{area}")
        journal_list = area_box.find_elements(By.CLASS_NAME, "collectionLink ")

        report_scrape(diretorio, timestr, area, saveMode)
        for journal in journal_list:
            link = journal.get_attribute("href")
            link_final = link + "grid"
            name = journal.find_element(By.CLASS_NAME, "journalTitle").text
            revistas(diretorio, link, link_final, name, saveMode, ano_minimo)

        print("Fim da raspagem")


if __name__ == "__main__":
    main()
