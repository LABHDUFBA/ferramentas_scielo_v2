"""Text reports for scraper runs and download failures."""

import os
from datetime import datetime


THEMES = {
    "1": "Ciências Agrárias", "2": "Ciências Biológicas",
    "3": "Ciências da Saúde", "4": "Ciências Exatas e da Terra",
    "5": "Ciências Humanas", "6": "Ciências Sociais Aplicadas",
    "7": "Engenharias", "8": "Linguística, Letras e Artes",
}


def _tipo(save_mode):
    return "Apenas XML" if save_mode == 1 else "XML e download de PDF"


def _write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as report:
        report.write(text)


def report_scrape(diretorio, timestamp, theme, save_mode):
    _write(os.path.join(diretorio, f"RELATÓRIO_GERAL_{timestamp}.txt"),
           f"=-=-=-=-=-Relatório da raspagem-=-=-=-=-=\n"
           f"- Data: {timestamp};\n- Área Temática: {THEMES.get(str(theme), theme)};\n"
           f"- Tipo de raspagem: {_tipo(save_mode)}\n")


def report_scrape_rev(diretorio, timestamp, rev_list, save_mode):
    _write(os.path.join(diretorio, f"RELATÓRIO_GERAL_REVISTAS_{timestamp}.txt"),
           f"=-=-=-=-=-Relatório da raspagem-=-=-=-=-=\n"
           f"- Data: {timestamp};\n- Lista de revistas: {rev_list};\n"
           f"- Tipo de raspagem: {_tipo(save_mode)}\n")


def report_erro(diretorio, error_list, save_mode):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _write(os.path.join(diretorio, f"RELATÓRIO_ERRO_{timestamp}.txt"),
           f"=-=-=-=-=-Relatório de erro-=-=-=-=-=\n- Data: {timestamp};\n"
           f"- Tipo de raspagem: {_tipo(save_mode)};\n"
           f"- Links XML não baixados: {error_list}\n")


def report_erro_pdf(diretorio, error_pdf_list, save_mode):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _write(os.path.join(diretorio, f"RELATÓRIO_ERRO_PDF_{timestamp}.txt"),
           f"=-=-=-=-=-Relatório de erro-=-=-=-=-=\n- Data: {timestamp};\n"
           f"- Tipo de raspagem: {_tipo(save_mode)};\n"
           f"- Links PDF não baixados: {error_pdf_list}\n")
