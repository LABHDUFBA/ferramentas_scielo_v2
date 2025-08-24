import os
import re
import ssl
import time

import wget
from reports import *
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ssl._create_default_https_context = ssl._create_unverified_context

error_xml_list = []
error_pdf_list = []


def _article_id_from_link(link: str) -> str:
    """
    Extrai o identificador do artigo a partir de .../a/<id>/...
    """
    m = re.search(r"/a/([^/]+)/", link)
    if m:
        return m.group(1)
    # fallback defensivo
    return link.split("/a/")[-1].split("/")[0].split("?")[0]


def get_pdf(diretorio, xml_link, link, pasta, error_pdf_list):
    """
    Baixa o PDF correspondente ao xml_link escolhido (mesmo idioma),
    salvando como IDENTIFICADOR.pdf (sem sufixo de idioma).
    """
    pdf_link = xml_link.replace("?format=xml", "?format=pdf")

    article_id = _article_id_from_link(pdf_link)
    full_name = f"{article_id}.pdf"

    path_org_pdf = os.path.join(diretorio, "PDF")
    path_final_pdf = os.path.join(path_org_pdf, pasta)
    if not os.path.exists(path_final_pdf):
        os.makedirs(path_final_pdf)

    out_pdf = os.path.join(path_final_pdf, full_name)
    if not os.path.exists(out_pdf):
        try:
            wget.download(pdf_link, out_pdf)
        except Exception as e:
            print(f"Erro: {e}")
            error_pdf_list.append(pdf_link)
    else:
        print("\nPDF já existe.")


def get_issue(diretorio, link, issue_link, pasta, saveMode):
    """
    Baixa os XMLs de cada artigo da edição, salvando apenas um idioma por artigo
    (prioridade: pt > es > en > outro). Nome do arquivo: IDENTIFICADOR.xml.
    """
    firefox_options = Options()
    firefox_options.add_argument("-lang=pt-BR")
    firefox_options.add_argument("--headless")
    firefox_options.add_argument("--no-sandbox")
    firefox_options.add_argument("--start-maximized")
    driver = webdriver.Firefox(options=firefox_options)
    driver.get(issue_link)

    # Aceitar cookies (quando presente)
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[7]/a"))
        ).click()
    except Exception:
        pass

    time.sleep(1)

    # caminho base para relatórios (evita variável não definida)
    base_xml_dir = os.path.join(diretorio, "XML", pasta)

    try:
        journal = driver.find_element(By.TAG_NAME, "h1").text
        publisher = driver.find_element(By.CLASS_NAME, "namePlublisher").text
        print(f"\n- Revista: {journal}\n- Publicação de: {publisher}\n")

        table = driver.find_element(By.CLASS_NAME, "table")
        tbody = table.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")

        # Agrupa variações por artigo e prioriza idioma
        artigos_por_id = {}  # base_id -> {lang: xml_link}
        LANG_PREF = ["pt", "es", "en"]

        for row in rows:
            try:
                anchors = row.find_elements(By.TAG_NAME, "a")
                pdf_anchors = [
                    a for a in anchors if "format=pdf" in (a.get_attribute("href") or "")
                ]
                for a in pdf_anchors:
                    href_pdf = a.get_attribute("href")
                    if not href_pdf:
                        continue

                    # gera link XML preservando querystring (inclui lang)
                    xml_link = href_pdf.replace("format=pdf", "format=xml")

                    # chave base sem querystring (um "artigo")
                    base_id = xml_link.split("?")[0]

                    # extrai lang com regex (fallback pouco provável)
                    m_lang = re.search(r"[?&]lang=([a-z]{2})", xml_link)
                    lang = m_lang.group(1) if m_lang else "xx"

                    bucket = artigos_por_id.setdefault(base_id, {})
                    bucket[lang] = xml_link
            except Exception as e:
                print(f"Erro ao processar linha de artigo: {e}")
                continue

        # Baixa apenas um idioma por artigo, conforme prioridade
        for base_id, langs_dict in artigos_por_id.items():
            chosen_lang = None
            for pref in LANG_PREF:
                if pref in langs_dict:
                    chosen_lang = pref
                    break
            if not chosen_lang:
                # escolhe qualquer disponível de forma determinística
                chosen_lang = sorted(langs_dict.keys())[0]

            xml_link = langs_dict[chosen_lang]

            # nome do arquivo: apenas IDENTIFICADOR.xml
            article_id = _article_id_from_link(xml_link)
            full_name = f"{article_id}.xml"

            path_org = os.path.join(diretorio, "XML")
            path_final = os.path.join(path_org, pasta)
            if not os.path.exists(path_final):
                os.makedirs(path_final)
            out_xml = os.path.join(path_final, full_name)

            if not os.path.exists(out_xml):
                try:
                    print(f"\nBaixando XML: {xml_link}")
                    wget.download(xml_link, out_xml)
                except Exception as e:
                    print(f"Erro: {e}")
                    error_xml_list.append(xml_link)
            else:
                print("\nXML já existe.")

            if saveMode == 2:
                get_pdf(diretorio, xml_link, link, pasta, error_pdf_list)

        if error_xml_list:
            report_erro(base_xml_dir, error_xml_list, saveMode)
        if error_pdf_list:
            report_erro_pdf(pasta, error_pdf_list, saveMode)
    except Exception as e:
        print(f"\nErro: {e}")
        print(f"\nNão foi possível encontrar dados para {issue_link}")

    driver.quit()
