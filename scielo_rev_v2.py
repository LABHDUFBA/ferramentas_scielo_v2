import os
import time
from reports import report_scrape_rev
from revistas import revistas

timestr = time.strftime("%Y-%m-%d")
saveMode = ""


def main():
    global saveMode
    while saveMode not in (1, 2):
        rev_list = []
        print("-=- Definição da(s) revista(s) -=-\n")
        while True:
            abbrev = input("Digite a abreviação da revista que deseja raspar: ").strip()
            if abbrev:
                rev_list.append(abbrev)
            resp = input("Deseja inserir outra? [S/N] ").strip().lower()
            if resp in ("n", "nao", "não", "no"):
                print("-=" * 50)
                break

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

        report_scrape_rev(diretorio, timestr, rev_list, saveMode)

        for revista in rev_list:
            # exemplo: revista = "alm"  -> https://www.scielo.br/j/alm/
            link = f"https://www.scielo.br/j/{revista}/"
            link_final = link + "grid"
            # `revistas` tratará o nome real (fallback via <h1>), caso a sigla seja insuficiente
            revistas(diretorio, link, link_final, revista, saveMode, ano_minimo)


if __name__ == "__main__":
    main()
