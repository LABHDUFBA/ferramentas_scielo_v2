<p align="center"><img src="img/labhd.png" height="256" width="256"/></p>

# Ferramentas Scielo v2 

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.7032159.svg)](https://doi.org/10.5281/zenodo.7032159) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)

Veja a documentação completa em https://labhdufba.github.io/ferramentas_scielo_v2/

---

No ano de 2020, desenvolvemos uma ferramenta para raspagem da base de artigos do Scielo.br. A ferramenta, escrita em Python, utilizava a biblioteca `BeautifulSoup` para coletar os dados. Entretanto, em 2021 o repositório Scielo.br passou por uma reestruturação completa.

Foi necessário, consequentemente, a reconstrução da ferramenta para lidar com a nova versão do site. Agora, utilizamos o `Selenium` para acessar e raspar os dados do repositório.

Com a `ferramentas_scielo_v2` é possível realizar a raspagem [por área do conhecimento](https://labhdufba.github.io/ferramentas_scielo_v2/#raspagem-por-area-de-conhecimento) ou [por revista (ou uma lista de revistas)](https://labhdufba.github.io/ferramentas_scielo_v2/#raspagem-por-revista-ou-por-lista-de-revistas). Também é possível optar pelo tipo de raspagem: apenas XML ou XML e PDFs.

Também disponibilizamos uma ferramenta para converter os XMLs para CSV, com o script `scielo_xml_to_csv/run.py`.

## Instalação

### Pré-requisitos

1. **Python 3.10+** — [instalação](https://python.org.br/instalacao-linux/)
2. **Chromium** — instalado via snap no Ubuntu (`snap install chromium`) ou via gerenciador de pacotes em outras distribuições. O script detecta automaticamente o binário em `/snap/bin/chromium`.
3. Clone o repositório e crie um ambiente virtual:

```bash
git clone https://github.com/LABHDUFBA/ferramentas_scielo_v2.git
cd ferramentas_scielo_v2
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Navegador e WebDriver

O script utiliza **Chromium** (não Firefox) controlado pelo `webdriver-manager`, que baixa automaticamente a versão compatível do `chromedriver`. Não é necessário instalar o GeckoDriver ou configurar o PATH manualmente.

> **Nota para usuários de Ubuntu/Debian:** o Chromium via snap funciona corretamente com as flags `--no-sandbox` e `--user-data-dir` configuradas automaticamente pelo script.

### Requisitos (`requirements.txt`)

- `selenium` — automação do navegador
- `webdriver-manager` — download automático do chromedriver
- `bs4` / `beautifulsoup4` — parsing HTML
- `lxml` — processamento de XML
- `pandas` — exportação de dados
- `requests` — requisições HTTP (fallback)
- `wget` — downloads alternativos

## Arquitetura

```
scielo_v2.py          ← Script principal (raspagem por área)
  ├── driver_utils.py     ← Criação do driver, warm-up, downloads via fetch()
  ├── revistas.py         ← Extração de revistas e edições por área
  ├── issue_xml.py        ← Download de XMLs/PDFs por edição
  └── reports.py          ← Geração de relatórios de erro

scielo_rev_v2.py      ← Raspagem por revista individual
  └── (mesmos módulos auxiliares)
```

### Fluxo de execução

1. `scielo_v2.py` cria o driver Chromium e faz **warm-up** no SciELO (resolve Bunny Shield/Cloudflare)
2. Navega até a página de revistas por área, expande o accordion da área escolhida
3. `revistas.py` extrai os links de todas as revistas e, para cada uma, busca as edições na página `/grid`
4. `issue_xml.py` processa cada edição: extrai links de artigos e baixa XMLs (e PDFs, se solicitado) via `fetch()` JavaScript reutilizando os cookies da sessão
5. XMLs já existentes são **pulados automaticamente** — reexecuções são incrementais

### Estratégias de resiliência

- **Bunny Shield/Cloudflare:** warm-up automático com espera inteligente; detecção de páginas de bloqueio
- **Layouts alternativos de `/grid`:** 4 estratégias de fallback para encontrar links de edições (issueList → tabela → links soltos → URL base sem `/grid`)
- **Download de XML:** `fetch()` JS dentro da sessão (rápido); fallback para navegação direta se `fetch()` retornar 403
- **Debug:** HTML de páginas problemáticas é salvo em `scielo/{data}/debug/`
- **Reprocessamento incremental:** XMLs já baixados são pulados com `⏩`

## Utilização

### Raspagem por área de conhecimento

```bash
source venv/bin/activate
python3 scielo_v2.py
```

O script solicitará:

1. **Área temática** (1–8)
2. **Tipo de raspagem** — 1 = XML apenas, 2 = XML + PDF
3. **Filtro por ano mínimo** — opcional (ex.: `2023` para pular edições anteriores)

```
-=- Definição da área temática -=-

- Opções:
1- Ciências Agrárias
2- Ciências Biológicas
3- Ciências da Saúde
4- Ciências Exatas e da Terra
5- Ciências Humanas
6- Ciências Sociais Aplicadas
7- Engenharias
8- Lingüística, Letras e Artes
Digite o número correspondente à área temática que deseja raspar:
```

### Raspagem por revista individual

```bash
python3 scielo_rev_v2.py
```

Forneça a abreviação da revista conforme a URL:

```
https://www.scielo.br/j/asoc/  →  abreviação: asoc
```

### Estrutura de saída

```
scielo/
  └── {AAAA-MM-DD}/
      ├── XML/
      │   ├── Ambiente_&_Sociedade/
      │   │   ├── S0101-31502023000100001.xml
      │   │   └── ...
      │   └── Revista_de_Administração_Pública/
      │       └── ...
      ├── PDF/          ← (apenas se saveMode=2)
      │   └── ...
      └── debug/        ← HTMLs de páginas problemáticas
```

> **Reprocessamento incremental:** se a pasta de uma revista já existir, apenas os arquivos que ainda não foram baixados serão baixados. É seguro interromper e retomar a coleta.

### Parâmetros via variáveis de ambiente

O script aceita variáveis de ambiente para execução não-interativa (útil para cron ou pipelines):

| Variável | Descrição | Exemplo |
|---|---|---|
| `SCIELO_AREA` | Número da área (1–8; somente `scielo_v2.py`) | `6` |
| `SCIELO_MODE` | Tipo de raspagem (1 ou 2) | `1` |
| `SCIELO_ANO_MINIMO` | Ano mínimo (0 = sem filtro) | `2023` |

Quando presentes, as variáveis eliminam somente os respectivos prompts. A lista de
revistas em `scielo_rev_v2.py` continua sendo informada interativamente.

### Upload opcional para S3

Os dois raspadores podem enviar cada XML/PDF ao S3 assim que o download termina:

```bash
python3 scielo_v2.py --s3-bucket meu-bucket --s3-prefix scielo/2026-07-23
```

Use `--s3-endpoint-url https://minio.exemplo` para serviços compatíveis com S3 e
`--s3-delete-local` para remover cada arquivo **somente após** o upload bem-sucedido.
As credenciais são obtidas pela cadeia padrão do boto3 (variáveis AWS, perfil ou role).

## Conversão de XML para CSV

Após o download dos arquivos XML, utilize `scielo_xml_to_csv/run.py` para converter todos os XML em CSV.

```bash
cd scielo_xml_to_csv
python3 run.py
```

Campos extraídos: `file_name`, `article_id`, `article_category`, `authors`, `contact_email`, `authors_affiliation`, `article_title`, `journal_title`, `journal_issn`, `journal_publisher`, `pub_date`, `abstract`, `key_words`, `issue`, `num`, `doi`, `full_text`, `footnotes`, `refs`.

## Limitações conhecidas

- **Rate limiting:** o SciELO (Bunny Shield/Cloudflare) bloqueia IPs após raspagem prolongada (~11h contínuas). Se ocorrer bloqueio, aguarde algumas horas ou troque de IP.
- **Revistas sem `/grid` padrão:** algumas revistas usam layouts alternativos. O script possui fallbacks, mas pode haver casos raros que exigem inspeção manual (HTML de debug é salvo automaticamente).
- **PDFs:** o download de PDFs consome banda e tempo significativos. Recomendamos iniciar com modo 1 (XML apenas).
- **Headless:** o script roda em modo headless por padrão. Para depuração visual, remova a flag `--headless=new` em `driver_utils.py`.

## Histórico de mudanças

- **v2.3** (jun/2026) — Migração completa de Firefox/GeckoDriver para Chromium/webdriver-manager; download de XML via `fetch()` JS; fallbacks para layouts alternativos de `/grid`; warm-up automático contra Bunny Shield; reprocessamento incremental; flag `--no-sandbox` para snap; debug HTML automático
- **v2.2** — Conversão para XML→CSV enriquecida (autores, keywords, referências em NDJSON)
- **v2.1** — Atualização para nova versão do site SciELO (Selenium + BeautifulSoup)

---

Elementos presentes nesse repositório foram retirados de [Scielo_Journal_Metadata_Downoader](https://github.com/johnsgomez/Scielo_Journal_Metadata_Downoader), criado por [johnsgomez](https://github.com/johnsgomez)

## Como citar?

É possível clicar em `Cite this repository` na aba à direita nesse repositório para acessar a citação nos formatos APA e BibTex, ou ainda acessar o [arquivo da citação](CITATION.cff) em formato `.cff`.

Abaixo a citação no formato BibTex:

```
@software{brasil_eric_2022_5168727,
  author       = {Brasil, Eric and
                  Nascimento, Leonardo and
                  Andrade, Gabriel and
                  Barbosa, Jorge},
  title        = {Ferramentas Scielo v2},
  month        = sep,
  year         = 2022,
  note         = {{Se você utilizar esse programa, por favor cite 
                   como referenciado abaixo.}},
  publisher    = {Zenodo},
  version      = {2.3},
  doi          = {10.5281/zenodo.5168727},
  url          = {https://doi.org/10.5281/zenodo.5168727}
}
```

## Licença 

[MIT Licence](LICENSE)

2021–2026 [Eric Brasil (IHL/UNILAB, LABHDUFBA)](https://github.com/ericbrasiln), [Gabriel Andrade (UFBA, LABHDUFBA)](https://github.com/gabrielsandrade), [Leonardo Nascimento (UFBA, LABHDUFBA)](https://github.com/leofn)
[Jorge Barbosa (PPGCS/UFBA, LABHDUFBA)](https://github.com/jhsbarbosa)
