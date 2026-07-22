"""
Utilitários centralizados para o driver Selenium do SciELO.

Otimizações:
- Warm-up automático na página principal (bypass Bunny Shield)
- Download de XML via fetch() JavaScript (sem navegar por artigo)
- Download de PDF via fetch() JavaScript com base64
- Waits inteligentes (WebDriverWait, nunca time.sleep fixo)
- Driver configurado para Chromium snap com flags corretas
"""

import os
import re
import base64
import time
import tempfile
import shutil
import logging

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)
from webdriver_manager.chrome import ChromeDriverManager


LOGGER = logging.getLogger("scielo")
_BROWSER_BINARIES = (
    "/snap/bin/chromium",
    "/opt/google/chrome/chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)


# ── Configuração do driver ──────────────────────────────────────────────────

# Porta de debug variável para evitar conflitos entre instâncias
_DEBUG_PORT_COUNTER = 0


def _next_debug_port():
    global _DEBUG_PORT_COUNTER
    _DEBUG_PORT_COUNTER += 1
    return 9220 + _DEBUG_PORT_COUNTER


def criar_driver():
    """Cria e configura uma instância do Chromium headless para SciELO.

    Usa webdriver-manager para baixar o chromedriver compatível.
    Flags específicas para snap chromium + anti-detecção.
    """
    port = _next_debug_port()
    tmp = tempfile.mkdtemp(prefix="chrome-scielo-")

    binary_location = next((path for path in _BROWSER_BINARIES if os.path.isfile(path) and os.access(path, os.X_OK)), None)
    if binary_location is None:
        searched = ", ".join(_BROWSER_BINARIES)
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"Chrome/Chromium não encontrado. Caminhos verificados: {searched}")

    options = ChromeOptions()
    options.binary_location = binary_location
    LOGGER.info("Browser binary selected", extra={"event": "browser_binary_selected", "file_path": binary_location})
    # Headless novo (Chrome 109+)
    options.add_argument("--headless=new")
    # Segurança no Linux snap
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Performance
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-default-apps")
    # Necessário para snap chromium
    options.add_argument(f"--remote-debugging-port={port}")
    options.add_argument(f"--user-data-dir={tmp}")
    options.add_argument(f"--data-path={tmp}/data")
    options.add_argument(f"--disk-cache-dir={tmp}/cache")
    # Janela (renderização mínima para o conteúdo)
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=pt-BR")
    # Anti-detecção
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )
    # Não carregar imagens — economia significativa de banda e memória
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheet": 2,
    }
    options.add_experimental_option("prefs", prefs)

    service = ChromeService(ChromeDriverManager().install())
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    # implicitly_wait = 0 (usamos explicit waits)
    driver.implicitly_wait(0)
    driver._scielo_profile_dir = tmp
    return driver


def close_driver(driver):
    """Quit the browser and remove its disposable Chrome profile."""
    profile_dir = getattr(driver, "_scielo_profile_dir", None)
    try:
        driver.quit()
    except Exception:
        LOGGER.exception("Error while closing browser", extra={"event": "driver_close_failed"})
    finally:
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)


def _atomic_write(dest, content, binary=False):
    """Write a complete download atomically, with a unique temporary file."""
    destination_dir = os.path.dirname(dest) or "."
    os.makedirs(destination_dir, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".scielo-", suffix=".part", dir=destination_dir)
    try:
        mode = "wb" if binary else "w"
        with os.fdopen(fd, mode, encoding=None if binary else "utf-8") as handle:
            handle.write(content)
        os.replace(temporary_path, dest)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def warmup_driver(driver):
    """Navega até o SciELO para resolver o desafio Bunny Shield e obter cookies.

    Deve ser chamado uma vez antes de qualquer navegação interna.
    Retorna True se o warm-up teve sucesso.
    """
    driver.get("https://www.scielo.br/j/asoc/")
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        # Verifica se o Bunny Shield foi resolvido
        title = driver.title
        if "secure connection" in title.lower() or "challenge" in title.lower():
            # Espera mais um pouco
            time.sleep(5)
            title = driver.title
            if "secure connection" in title.lower():
                return False
        return True
    except TimeoutException:
        return False


# ── Download de XML via JavaScript fetch ──────────────────────────────────────

_FETCH_XML_JS = """
var url = arguments[0];
var callback = arguments[1];
fetch(url, {credentials: 'include'})
    .then(function(response) {
        if (!response.ok) {
            callback({success: false, error: 'HTTP ' + response.status, code: response.status});
            return;
        }
        return response.text();
    })
    .then(function(text) {
        if (!text) {
            callback({success: false, error: 'empty response'});
            return;
        }
        callback({success: true, data: text, length: text.length});
    })
    .catch(function(err) {
        callback({success: false, error: err.message});
    });
"""

_FETCH_PDF_JS = """
var url = arguments[0];
var callback = arguments[1];
fetch(url, {credentials: 'include'})
    .then(function(response) {
        if (!response.ok) {
            callback({success: false, error: 'HTTP ' + response.status, code: response.status});
            return;
        }
        return response.arrayBuffer();
    })
    .then(function(buffer) {
        if (!buffer) {
            callback({success: false, error: 'empty buffer'});
            return;
        }
        var bytes = new Uint8Array(buffer);
        var binary = '';
        for (var i = 0; i < bytes.length; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        callback({success: true, data: btoa(binary), length: bytes.length});
    })
    .catch(function(err) {
        callback({success: false, error: err.message});
    });
"""


def download_xml(driver, xml_url: str, dest: str, retries: int = 2) -> bool:
    """Baixa um XML do SciELO usando fetch() JavaScript dentro da sessão.

    Estratégia:
    1. Tenta fetch() JS (rápido, sem navegar)
    2. Se falhar (403/bloqueio), faz navegação + extração como fallback

    Salva o XML em `dest`. Retorna True se sucesso.
    """
    for attempt in range(retries):
        try:
            result = driver.execute_async_script(_FETCH_XML_JS, xml_url)

            if result and result.get("success"):
                xml_text = result["data"]

                # Limpa prefixo do Chrome XML viewer
                if xml_text.startswith("This XML file does not appear to have any style information"):
                    newline = xml_text.index("\n")
                    xml_text = xml_text[newline + 1:] if newline >= 0 else xml_text

                # Validação mínima
                if not _is_valid_xml(xml_text):
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    _save_debug(dest, xml_text)
                    return False

                _atomic_write(dest, xml_text)
                return True

            # Se fetch retornou 403, tenta navegação direta
            elif result and result.get("code") == 403:
                return _download_xml_via_navigation(driver, xml_url, dest)

            elif result and result.get("error"):
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return False

        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return False

    return _download_xml_via_navigation(driver, xml_url, dest)


def download_pdf(driver, pdf_url: str, dest: str, retries: int = 2) -> bool:
    """Baixa um PDF do SciELO usando fetch() JavaScript com base64."""
    for attempt in range(retries):
        try:
            result = driver.execute_async_script(_FETCH_PDF_JS, pdf_url)

            if result and result.get("success"):
                pdf_bytes = base64.b64decode(result["data"], validate=True)
                if not pdf_bytes.startswith(b"%PDF-"):
                    LOGGER.warning("Invalid PDF response", extra={"event": "invalid_pdf", "file_path": dest})
                    continue
                _atomic_write(dest, pdf_bytes, binary=True)
                return True

            elif result and result.get("code") == 403:
                # PDFs bloqueados precisam de navegação, mas é raro
                return False

            elif result and result.get("error"):
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                return False

        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return False

    return False


# ── Helpers internos ──────────────────────────────────────────────────────────

def _is_valid_xml(text: str) -> bool:
    """Verifica se o texto contém XML SciELO válido."""
    return any(
        marker in text
        for marker in ("<?xml", "<article", "<scielo", "<SciELO", "<SCIELO")
    )


def _save_debug(dest: str, content: str):
    """Salva conteúdo inválido para debug."""
    debug_path = dest + ".debug.txt"
    try:
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(content[:5000])
    except OSError:
        pass


def _download_xml_via_navigation(driver, xml_url: str, dest: str) -> bool:
    """Fallback: navega até a URL do XML e extrai o conteúdo.

    Mais lento que fetch(), mas funciona quando o fetch() é bloqueado.
    """
    try:
        driver.get(xml_url)
        # Espera o conteúdo XML aparecer
        try:
            WebDriverWait(driver, 15).until(
                lambda d: len(d.page_source) > 200
            )
        except TimeoutException:
            pass

        content = driver.page_source

        # Bunny Shield check
        if "Establishing a secure connection" in content:
            time.sleep(5)
            content = driver.page_source
            if "Establishing a secure connection" in content:
                return False

        # Extrai texto do XML viewer do Chrome
        try:
            pre_elements = driver.find_elements(By.TAG_NAME, "pre")
            if pre_elements:
                xml_text = "\n".join(
                    p.get_attribute("innerText") for p in pre_elements
                )
            else:
                xml_text = driver.find_element(
                    By.TAG_NAME, "body"
                ).get_attribute("innerText")
        except Exception:
            xml_text = driver.execute_script(
                "return document.documentElement.innerText || '';"
            )

        if not xml_text or len(xml_text.strip()) < 50:
            return False

        # Limpa prefixo do Chrome XML viewer
        if xml_text.startswith(
            "This XML file does not appear to have any style information"
        ):
            newline = xml_text.index("\n")
            xml_text = xml_text[newline + 1:] if newline >= 0 else xml_text

        if not _is_valid_xml(xml_text):
            _save_debug(dest, xml_text)
            return False

        _atomic_write(dest, xml_text)
        return True

    except Exception:
        return False


# ── Extração de IDs ───────────────────────────────────────────────────────────

def article_id_from_link(link: str) -> str:
    """Extrai o identificador do artigo a partir de .../a/<id>/..."""
    m = re.search(r"/a/([^/]+)/", link)
    if m:
        return m.group(1)
    return link.split("/a/")[-1].split("/")[0].split("?")[0]


def ano_da_edicao(href: str) -> int | None:
    """Extrai o ano do href de uma edição (ex.: .../i/2015.v18n1/ -> 2015)."""
    if not href:
        return None
    m = re.search(r"/i/((19|20)\d{2})", href)
    return int(m.group(1)) if m else None
