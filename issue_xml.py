"""
Baixa os XMLs (e opcionalmente PDFs) dos artigos de uma edição.

Usa driver_utils para downloads eficientes via JavaScript fetch(),
 com fallback para navegação direta se necessário.
"""

import os
import re
import logging

from driver_utils import download_xml, download_pdf, article_id_from_link
from reports import report_erro, report_erro_pdf
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Listas globais de erros (mantidas para compatibilidade com reports.py)
error_xml_list = []
error_pdf_list = []
LOGGER = logging.getLogger("scielo")

LANG_PREF = ["pt", "es", "en"]


def get_issue(diretorio, link, issue_link, pasta, saveMode, driver, uploader=None):
    """
    Processa uma edição de uma revista do SciELO.

    Para cada artigo, seleciona um idioma (pt > es > en) e baixa o XML.
    Se saveMode == 2, baixa também o PDF.

    O driver deve ter feito warm-up prévio (cookies do SciELO).
    """
    # Error lists are per issue; otherwise old failures are reported repeatedly.
    error_xml_list.clear()
    error_pdf_list.clear()
    driver.get(issue_link)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table#DocumentList, table.table, h1")
            )
        )
    except TimeoutException:
        print(f"  ⚠️ Timeout ao carregar edição: {issue_link}")
        return

    # Nome da revista
    try:
        journal = driver.find_element(By.TAG_NAME, "h1").text
    except NoSuchElementException:
        journal = pasta.replace("_", " ")

    try:
        publisher = driver.find_element(By.CLASS_NAME, "namePlublisher").text
    except NoSuchElementException:
        publisher = "N/A"

    print(f"\n- Revista: {journal}")
    print(f"- Publicação de: {publisher}")

    # Buscar tabela de artigos
    try:
        table = driver.find_element(
            By.CSS_SELECTOR, "table#DocumentList, table.table"
        )
    except NoSuchElementException:
        print(f"  ⚠️ Sem tabela de documentos em {issue_link}")
        return

    tbody = table.find_element(By.TAG_NAME, "tbody")
    rows = tbody.find_elements(By.TAG_NAME, "tr")

    # Agrupa links por artigo (mesmo ID, idiomas diferentes)
    artigos_por_id = {}
    for row in rows:
        try:
            anchors = row.find_elements(By.TAG_NAME, "a")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if "format=pdf" not in href:
                    continue

                xml_link = href.replace("format=pdf", "format=xml")
                base_id = xml_link.split("?")[0]

                m_lang = re.search(r"[?&]lang=([a-z]{2})", xml_link)
                lang = m_lang.group(1) if m_lang else "xx"

                bucket = artigos_por_id.setdefault(base_id, {})
                bucket[lang] = xml_link
        except Exception:
            continue

    if not artigos_por_id:
        print(f"  ⚠️ Nenhum artigo com link XML encontrado em {issue_link}")
        return

    # Diretórios de saída
    path_xml = os.path.join(diretorio, "XML", pasta)
    path_pdf = os.path.join(diretorio, "PDF", pasta)
    os.makedirs(path_xml, exist_ok=True)
    if saveMode == 2:
        os.makedirs(path_pdf, exist_ok=True)

    # Baixa um idioma por artigo (prioridade: pt > es > en)
    for base_id, langs_dict in artigos_por_id.items():
        chosen_lang = None
        for pref in LANG_PREF:
            if pref in langs_dict:
                chosen_lang = pref
                break
        if not chosen_lang:
            chosen_lang = sorted(langs_dict.keys())[0]

        xml_link = langs_dict[chosen_lang]
        aid = article_id_from_link(xml_link)
        full_name = f"{aid}.xml"
        out_xml = os.path.join(path_xml, full_name)

        if os.path.exists(out_xml):
            print(f"  ⏩ XML já existe: {full_name}")
        else:
            print(f"  ↓ XML ({chosen_lang}): {aid}")
            if download_xml(driver, xml_link, out_xml):
                print(f"  ✅ {full_name}")
                if uploader:
                    uploader.upload(out_xml, diretorio)
            else:
                print(f"  ✗ Falha: {full_name}")
                error_xml_list.append(xml_link)
                LOGGER.warning("XML download failed", extra={"event": "xml_download_failed", "issue_url": issue_link, "file_path": out_xml})

        # PDF (modo 2)
        if saveMode == 2:
            pdf_link = xml_link.replace("?format=xml", "?format=pdf")
            pdf_name = f"{aid}.pdf"
            out_pdf = os.path.join(path_pdf, pdf_name)

            if os.path.exists(out_pdf):
                print(f"  ⏩ PDF já existe: {pdf_name}")
                continue

            print(f"  ↓ PDF: {aid}")
            if download_pdf(driver, pdf_link, out_pdf):
                print(f"  ✅ {pdf_name}")
                if uploader:
                    uploader.upload(out_pdf, diretorio)
            else:
                print(f"  ✗ PDF falha: {pdf_name}")
                error_pdf_list.append(pdf_link)
                LOGGER.warning("PDF download failed", extra={"event": "pdf_download_failed", "issue_url": issue_link, "file_path": out_pdf})

    # Relatórios de erro
    base_xml_dir = os.path.join(diretorio, "XML", pasta)
    if error_xml_list:
        report_erro(base_xml_dir, error_xml_list, saveMode)
    if error_pdf_list:
        report_erro_pdf(path_pdf, error_pdf_list, saveMode)
