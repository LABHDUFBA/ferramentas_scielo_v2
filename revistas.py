"""
Navega nas edições de uma revista do SciELO e delega o download
dos XMLs/PDFs para issue_xml.get_issue.

Otimizações:
- Reutiliza o driver passado pelo caller (sessão quente com cookies)
- Usa WebDriverWait em vez de time.sleep
- Extrai dados dos links antes de iterar (evita StaleElementReference)
"""

import os
import re

from issue_xml import get_issue
from driver_utils import ano_da_edicao
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def revistas(diretorio, link, link_journal, journal_name, saveMode, ano_minimo=0, driver=None):
    """
    Acessa a página de grid de uma revista e processa suas edições.

    - Filtra por ano mínimo (pula edições mais antigas)
    - Se driver for fornecido, reutiliza a sessão
    - Se não, cria e destrói um novo driver (caminho legacy)
    """
    own_driver = driver is None
    if own_driver:
        from driver_utils import criar_driver, warmup_driver
        driver = criar_driver()
        warmup_driver(driver)

    driver.get(link_journal)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except TimeoutException:
        print(f"  ⚠️ Timeout ao carregar revista: {link_journal}")

    # Nome da revista
    effective_name = (journal_name or "").strip()
    if not effective_name:
        try:
            effective_name = driver.find_element(By.TAG_NAME, "h1").text.strip()
        except NoSuchElementException:
            effective_name = ""

    pasta = re.sub(r"\s+", "_", re.sub(r"[,.\(\)<>?/\\|@+]", "", effective_name)) or "Sem_Nome"
    print(f"\nRevista: {effective_name} ({link})")
    print(f"Pasta: {pasta}")

    # Buscar a lista de edições
    try:
        issue_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "issueList"))
        )
    except TimeoutException:
        print(f"  ℹ️ {journal_name}: sem 'issueList' (revista sem edições). Pulando.")
        if own_driver:
            driver.quit()
        return

    try:
        issue_table = issue_box.find_element(By.TAG_NAME, "table")
    except NoSuchElementException:
        print(f"  ℹ️ {journal_name}: sem tabela de edições. Pulando.")
        if own_driver:
            driver.quit()
        return

    # Extrai todos os links ANTES de iterar (evita StaleElementReference)
    anchors = issue_table.find_elements(By.TAG_NAME, "a")
    issue_links = []
    for a in anchors:
        href = a.get_attribute("href")
        if href and "/i/" in href:
            issue_links.append(href)

    if not issue_links:
        print(f"  ℹ️ {journal_name}: sem links de edições. Pulando.")
        if own_driver:
            driver.quit()
        return

    # Processa edições em ordem (da mais recente para a mais antiga)
    for issue_link in issue_links:
        ano = ano_da_edicao(issue_link)
        if ano is None:
            continue

        if ano < ano_minimo:
            print(f"  ⏭️ {effective_name}: edição {ano} < {ano_minimo}. Próxima revista.")
            break

        print(f"\n  Edição {ano}: {issue_link}")
        get_issue(diretorio, link, issue_link, pasta, saveMode, driver=driver)

    if own_driver:
        driver.quit()