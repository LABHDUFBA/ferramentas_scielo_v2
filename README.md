<p align="center"><img src="img/labhd.png" height="256" width="256"/></p>

# ferramentas_scielo

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)

>Esse repositório é parte dos projetos desenvolvidos pelos membros do [LABHDUFBA](http://labhd.ufba.br/) e tem como objetivo oferecer ferramentas de raspagem, organização e análise de artigos ciêntíficos publicados na plataforma [Scielo.br](https://www.scielo.br/scielo.php?script=sci_home&lng=pt&nrm=iso).

## Instalação

Para executar os Scripts desse repositório, você precisa clonar ou fazer download para sua máquina. Antes de executar os scripts, é preciso preparar seu computador, como mostramos abaixo.

### Python

A ferramentas desse projeto foram escritas em [Python 3.8](https://www.python.org/). Esta é uma linguagem de programação que te permite trabalhar rapidamente e integrar diferentes sistemas com maior eficiência.
Para executar o arquivo .py é preciso instalar o Python3 em seu computador.

[Clique aqui](https://python.org.br/instalacao-windows/) para um tutorial de instalação do Python no Windows, [clique aqui](https://python.org.br/instalacao-linux/) para Linux e [clique aqui](https://python.org.br/instalacao-mac/)
para Mac.

Após a instalação, vc pode executar o arquivo .py direto do prompt de comando do Windows ou pelo terminal do Linux, ou utilizar as diversas [IDE](https://pt.wikipedia.org/wiki/Ambiente_de_desenvolvimento_integrado) disponíveis.

Exemplo de como executar utilizando o terminal do Linux, após instalar o Python3.8:

1. Acesse o diretório em que o arquivo .py está salvo:
   ```sh
   $ cd user/local
   ```
1. Instale as bibliotecas requeridas:
   ```sh
   $ pip3 install -r requirements.txt
   ```
1. Execute o arquivo usando Python3.8
   ```sh
   $ python3 scielo_v2.py
   ```

## scielo_v2.py

Esse script permite ao usuário selecionar qual assunto pretende raspar de acordo com a categorização estabelecida pela plataforma [Scielo.br](https://www.scielo.br/journals/thematic?status=current). É possível escolher entre oito assunto:

* Ciências Agrárias
* Ciências Biológicas
* Ciências da Saúde
* Ciêncas Exatas e da Terra 
* Ciências Humanas
* Ciências Sociais Aplicadas
* Engenharias
* Linguística, Letras e Artes

Após a definição do assunto, é preciso definir o tipo de raspagem: 

1. Realizar a raspagem de todos os arquivos XML de todas as edições de todas as revistas da área selecionada: opção `1`;
2. Realizar a raspagem de todos os arquivos XML e PDF de todas as edições de todas as revistas da área selecionada: opção `2`.
   
    :warning: Devido ao volume de dados, contando dezenas de milhares de artigos, o download de todos os arquivos PDF demandará  muito tempo e uso intenso de sua máquina.

    
:warning: Os arquivos XML possuem todos os metadados dos artigos, incluíndo o texto completo e as referências bibliográficas.

Após o download dos arquivos XML é posssível utilizar a ferramenta `scielo_xml_to_csv` para convertar todos os XML para um arquivo `csv`.

Acesse a pasta `scielo_xml_to_csv` e execute o arquivo `run.py`.

Para mais informações leia o [README.md](scielo_xml_to_csv/README.md) da ferramenta.

## scielo_rev_v2.py

Nesse script é possível raspar uma revista ou uma lista de revistas específicas através de seu nome.

Possui as mesmas características do `scielo_v2.py`, porém a definição da(s) revista(s) a ser(em) raspada(s) é feita através da abreviação do nome da revista conforme URL da revista no site do Scielo.br.

Por exemplo, se vc pretende raspar os arquivos da revista Almanack, acesse a página inicial da revista no repositório e encontre a abreviação de seu título na URL.

```
https://www.scielo.br/j/alm/
```

Nesse caso, o abreviação do nome da revista é `alm`. Esse termo deve ser informado para o programa.

## :warning: Atenção

Ambos os scripts criarão diretórios para armazenar os arquivos e dados.

- `scielo/{AAAA-MM-DD}/PDF/{nomeDaRevista}` no caso da raspagem de PDFs;
- `scielo/{AAAA-MM-DD}/XML/{nomeDaRevista}` no caso da raspagem de XMls.

Entretanto, se a pasta com o nome de uma revista já existir no mesmo caminho que o programa está sendo executado, só serão baixados arquivos que ainda não existem.

## Licença 

[MIT Licence](LICENSE)

2021 [Eric Brasil (IHL/UNILAB, LABHDUFBA)](https://github.com/ericbrasiln), [Gabriel Andrade (UFBA, LABHDUFBA)](https://github.com/gabrielsandrade), [Leonardo Nascimento (UFBA, LABHDUFBA)](https://github.com/leofn)