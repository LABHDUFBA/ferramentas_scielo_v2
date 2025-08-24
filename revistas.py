import time
import re
from issue_xml import *
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def _ano_da_edicao(href: str) -> int | None:
    """Extrai o ano do href de uma edição da SciELO (ex.: .../i/2015.v18n1/ -> 2015)."""
    if not href:
        return None
    m = re.search(r"/i/((19|20)\d{2})", href)
    return int(m.group(1)) if m else None


def revistas(diretorio, link, link_journal, journal_name, saveMode, ano_minimo: int = 2023):
    """
    Acessa a revista e processa apenas edições com ano >= ano_minimo.
    Se encontrar uma edição com ano < ano_minimo, pula para a próxima revista.
    Se a revista não tiver nenhuma edição publicada (sem issueList/table), apenas registra e segue.
    """
    firefox_options = Options()
    firefox_options.add_argument("-lang=pt-BR")
    firefox_options.add_argument("--headless")
    firefox_options.add_argument("--no-sandbox")
    firefox_options.add_argument("--start-maximized")
    driver = webdriver.Firefox(options=firefox_options)
    driver.get(link_journal)

    # Aceitar cookies (quando existir)
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[7]/a"))
        ).click()
    except Exception:
        pass

    time.sleep(1)

    alterar = re.sub(r"[(,.:\(\)<>?/\\|@+)]", "", journal_name)
    pasta = re.sub(r"\s+", "_", alterar)

    try:
        issue_box = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "issueList"))
        )
    except TimeoutException:
        print(f"ℹ️ {journal_name}: nenhum 'issueList' encontrado (revista sem edições). Pulando.")
        driver.quit()
        return

    try:
        issue_table = issue_box.find_element(By.TAG_NAME, "table")
    except NoSuchElementException:
        print(f"ℹ️ {journal_name}: não há tabela de edições disponível. Pulando.")
        driver.quit()
        return

    anchors = issue_table.find_elements(By.TAG_NAME, "a")
    issue_links = [a.get_attribute("href") for a in anchors if "/i/" in (a.get_attribute("href") or "")]
    if not issue_links:
        print(f"ℹ️ {journal_name}: sem links de edições. Pulando.")
        driver.quit()
        return

    for issue_link in issue_links:
        ano = _ano_da_edicao(issue_link)
        if ano is None:
            print(f"⚠️ Ignorando link sem ano: {issue_link}")
            continue

        if ano < ano_minimo:
            print(
                f"⏭️ {journal_name}: primeira edição abaixo de {ano_minimo} ({ano}). "
                f"Indo para a próxima revista."
            )
            break

        print(f"\nLink da edição {ano}: {issue_link}")
        get_issue(diretorio, link, issue_link, pasta, saveMode)

    driver.quit()
