import time, re, os
import wget
from reports import*
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
error_xml_list = []
error_pdf_list = []

def get_issue(diretorio, link, issue_link, pasta, saveMode):
    firefox_options = Options()
    firefox_options.add_argument('-lang=pt-BR')
    firefox_options.set_preference('intl.accept_languages', 'pt-BR, pt')
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--start-maximized')

    driver = webdriver.Firefox(options=firefox_options)
    driver.get(issue_link)

    # Aceitar cookies (atualizado p/ Selenium moderno)
    try:
        driver.find_element(By.CLASS_NAME, 'alert-cookie-notification')
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    'a#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, '
                    'div.alert-cookie-notification a'
                ))
            ).click()
        except Exception:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//div[contains(@class,'alert-cookie-notification')]//a[1]"
                ))
            ).click()
    except Exception:
        pass

    time.sleep(1)
    #try to find h1 tag, if not, pass
    try:
        journal = driver.find_element(By.TAG_NAME,'h1').text
        publisher = driver.find_element(By.CLASS_NAME,'namePlublisher').text
        print(f'\n- Revista: {journal}\n- Publicação de: {publisher}\n')
        table = driver.find_element(By.CLASS_NAME,'table')
        tbody = table.find_element(By.TAG_NAME,'tbody')
        links = tbody.find_elements(By.TAG_NAME,'tr')
        for article in links:
            try:
                article_links = article.find_elements(By.TAG_NAME,'a')
                article_links = [link for link in article_links if 'format=pdf' in link.get_attribute("href")]
                for article_link in article_links:
                    xml_link = article_link.get_attribute("href").replace('format=pdf', 'format=xml')
                    xml_link = re.sub(r"(\?[a-z]+=[a-z]+$)","?format=xml", xml_link)
                    m = re.search(r'/a/([A-Za-z0-9]+)', xml_link)
                    article_id = m.group(1) if m else 'sem_id'
                    full_name = f'{article_id}.xml'
                    path_org = os. path. join(diretorio, 'XML')
                    path_final = os.path.join(path_org, pasta)
                    if not os.path.exists(path_final):
                        os.makedirs(path_final)
                    out_xml = os.path.join(path_final, full_name)
                    if not os.path.exists(out_xml):
                        try:
                            print(f'\nBaixando XML: {xml_link}')
                            wget.download(xml_link, out_xml)
                        except Exception as e:
                            print(f'Erro: {e}')
                            error_xml_list.append(xml_link)
                    else:
                        print('\nXML já existe.')
                    if saveMode == 2:
                        get_pdf(diretorio, xml_link, link, pasta, error_pdf_list)
                    else:
                        pass
            except Exception as e:
                print(f'Erro ao acessar o artigo: {e}')
                print('\nsem link')
        if len(error_xml_list)!=0:
            report_erro (path_final, error_xml_list, saveMode)
        if len(error_pdf_list)!=0:    
            report_erro_pdf(pasta, error_pdf_list,saveMode)
    except Exception as e:
        print(f'\nErro: {e}')
        print(f'\nNão foi possível encontrar dados para {issue_link}')
    # Fechando o navegador
    driver.quit()

