import time, re
from issue_xml import*
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC

def revistas(diretorio, link, link_journal, journal_name, saveMode):
    firefox_options = Options()
    firefox_options.add_argument('-lang=pt-BR')
    firefox_options.set_preference('intl.accept_languages', 'pt-BR, pt')
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--start-maximized')

    driver = webdriver.Firefox(options=firefox_options)
    driver.get(link_journal)

    # Aceitar cookies (seletor robusto PT/EN)
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
    # … resto igual …
    alterar = re.sub(r"[(,.:\(\)<>?/\\|@+)]", "", journal_name)
    pasta = re.sub(r"\s+", "_", alterar)
    revista_dir = os.path.join(diretorio, "XML", pasta)
    os.makedirs(revista_dir, exist_ok=True)
    issue_box = driver.find_element(By.ID,'issueList')
    issue_table = issue_box.find_element(By.TAG_NAME,'table')
    issues = issue_table.find_elements(By.TAG_NAME,'a')
    for issue in issues:
        issue_link = issue.get_attribute("href")
        print(f'\nLink da edição: {issue_link}')
        get_issue(revista_dir, link, issue_link, pasta, saveMode)
    # Fechando o navegador
    driver.quit()
