"""
Navega nas edições de uma revista do SciELO e delega o download
dos XMLs/PDFs para issue_xml.get_issue.

Otimizações:
- Reutiliza o driver passado pelo caller (sessão quente com cookies)
- Usa WebDriverWait em vez de time.sleep
- Extrai dados dos links antes de iterar (evita StaleElementReference)
- Fallbacks para diferentes layouts de página /grid
- Debug: salva HTML quando não encontra edições
"""

import os
import re
import time

from issue_xml import get_issue
from driver_utils import ano_da_edicao, close_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def _extract_issue_links(driver, journal_name):
    """
    Tenta múltiplos seletores para encontrar links de edições.
    Retorna lista de URLs ou [] se não encontrar.
    """
    # Estratégia 1: issueList com tabela (layout padrão)
    try:
        issue_box = driver.find_element(By.ID, "issueList")
        try:
            issue_table = issue_box.find_element(By.TAG_NAME, "table")
            anchors = issue_table.find_elements(By.TAG_NAME, "a")
            links = [a.get_attribute("href") for a in anchors
                      if "/i/" in (a.get_attribute("href") or "")]
            if links:
                return links
        except NoSuchElementException:
            pass
    except NoSuchElementException:
        pass

    # Estratégia 2: qualquer tabela com links /i/ na página
    tables = driver.find_elements(By.TAG_NAME, "table")
    for table in tables:
        anchors = table.find_elements(By.TAG_NAME, "a")
        links = [a.get_attribute("href") for a in anchors
                  if "/i/" in (a.get_attribute("href") or "")]
        if links:
            return links

    # Estratégia 3: qualquer link /i/ na página (fora de tabelas)
    all_links = [a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a")]
    issue_links = [h for h in all_links if h and "/i/" in h]
    if issue_links:
        return issue_links

    # Estratégia 4: página sem /grid — tentar a URL base
    current_url = driver.current_url
    if current_url.endswith("/grid"):
        base_url = current_url[:-5]  # remove /grid
        # A página base pode ter os links de edições em formato diferente
        driver.get(base_url)
        time.sleep(2)
        all_links = [a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a")]
        issue_links = [h for h in all_links if h and "/i/" in h]
        if issue_links:
            return issue_links

    return []


def revistas(diretorio, link, link_journal, journal_name, saveMode, ano_minimo=0, driver=None, uploader=None):
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

    # Verificar se a página carregou corretamente (não é 404 ou bloqueio)
    page_title = driver.title or ""
    if "not found" in page_title.lower() or "404" in page_title.lower():
        print(f"  ⚠️ {journal_name}: revista não encontrada (404). Pulando.")
        if own_driver:
            close_driver(driver)
        return

    # Verificar bloqueio Cloudflare/Bunny
    body_text = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text[:500].lower()
    except Exception:
        pass
    if "establishing a secure connection" in body_text or "security check" in body_text:
        print(f"  ⚠️ {journal_name}: bloqueado por proteção anti-bot. Pulando.")
        if own_driver:
            close_driver(driver)
        return

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

    # Buscar links de edições com fallbacks
    issue_links = _extract_issue_links(driver, journal_name)

    if not issue_links:
        # Debug: salvar HTML para análise
        debug_path = os.path.join(diretorio, "debug")
        os.makedirs(debug_path, exist_ok=True)
        safe_name = re.sub(r"[^\w]", "_", journal_name or "unknown")
        debug_file = os.path.join(debug_path, f"{safe_name}_no_issues.html")
        try:
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print(f"  ℹ️ {journal_name}: sem edições encontradas. HTML salvo em {debug_file}")
        except Exception:
            print(f"  ℹ️ {journal_name}: sem edições encontradas. Pulando.")
        if own_driver:
            close_driver(driver)
        return

    # Deduplicar links (evitar processar a mesma edição duas vezes)
    seen = set()
    unique_links = []
    for href in issue_links:
        if href not in seen:
            seen.add(href)
            unique_links.append(href)
    issue_links = unique_links

    print(f"  📖 {len(issue_links)} edições encontradas")

    # Processa edições (da mais recente para a mais antiga)
    for issue_link in issue_links:
        ano = ano_da_edicao(issue_link)
        if ano is None:
            # Link sem ano reconhecível — tentar processar mesmo assim
            print(f"  ⚠️ Link sem ano: {issue_link}")
            continue

        if ano < ano_minimo:
            print(f"  ⏭️ {effective_name}: edição {ano} < {ano_minimo}. Próxima revista.")
            break

        print(f"\n  Edição {ano}: {issue_link}")
        get_issue(diretorio, link, issue_link, pasta, saveMode, driver=driver, uploader=uploader)

    if own_driver:
        close_driver(driver)
