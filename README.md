# Peugeot Citroën RT6 MapaRadar Updater

Converte dados de radares e zonas de perigo do MapaRadar para o formato CSV usado
pela central RNEG RT6 de veículos Peugeot e Citroën.

Testado em um Peugeot 308 com central RNEG RT6 e firmware `RT6 2.86B`.

> Este repositório não inclui bases de radares, arquivos convertidos, mapas OSM,
> índices gerados ou saídas prontas. Esses arquivos devem ser obtidos e mantidos
> localmente por cada usuário.

---

## Instruções em Português

### Visão Geral

A central RT6 usa arquivos `.LZW` para carregar Pontos de Interesse (POI). Este
projeto gera os dois CSVs intermediários esperados por ferramentas como o
RadarViewer v2.0:

| Arquivo | Conteúdo |
| --- | --- |
| `RADAR.csv` | Radares fixos, radares móveis, semáforos com radar e câmeras |
| `DANGERZ.csv` | Polícia rodoviária, pedágios e lombadas |

O fluxo básico é:

```text
dados MapaRadar -> python main.py -> output/RADAR.csv + output/DANGERZ.csv
```

### Dois Fluxos de Uso

Este projeto suporta dois caminhos de conversão:

| Fluxo | Quando usar | Como funciona |
| --- | --- | --- |
| CSV convertido via MiraScript | Quando você já gerou `converted_radars.csv` e `converted_dangerz.csv` no próprio veículo | A central RT6 executa o MiraScript, gera as coordenadas proprietárias, e este projeto usa esses CSVs para montar `RADAR.csv` e `DANGERZ.csv` finais |
| Conversão direta em Python | Quando você quer converter no computador, sem rodar MiraScript e sem depender do veículo durante a conversão | O Python calcula as coordenadas RT6 por interpolação e gera os CSVs finais diretamente |

O primeiro fluxo tende a ser o mais fiel porque usa a função proprietária da
própria central. O segundo fluxo é mais prático para atualizações feitas no PC,
mas requer as dependências Python e dados locais suficientes para montar o
interpolador.

### Créditos e Comunidade

Este projeto existe graças ao trabalho das comunidades MapaRadar, c4clube e
clubepeugeot, que preservaram e compartilharam conhecimento sobre atualização de
POIs, radares e centrais RT6. A atualização original dos radares para RT6 era
acompanhada no fórum MapaRadar:

https://forum.maparadar.com/viewtopic.php?t=61848

Consulte e respeite as regras da comunidade e as condições de uso dos dados.

### Requisitos

- Python 3.8 ou superior
- Dependências do `requirements.txt` para ter todos os modos disponíveis:
  - `numpy` e `scipy`: necessários para `--no-car`
  - `osmium`: necessário para `--build-osm-index`

O modo padrão, usando arquivos já convertidos pela central, usa apenas a
biblioteca padrão do Python.

### Instalação

```bash
git clone https://github.com/tomsnunes/peugeot-citroen-rt6-maparadar-updater.git
cd peugeot-citroen-rt6-maparadar-updater
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Preparação dos Arquivos

Crie as pastas abaixo localmente. Elas são ignoradas pelo Git.

```text
databases/
  maparadar/
    maparadar_radars.csv
    maparadar_dangerz.csv
  base/
    base_radar.csv
    base_dangerz.csv
  converted/
    converted_radars.csv
    converted_dangerz.csv
  openstreetmap/
    brazil-*.osm.pbf
output/
```

Arquivos comuns aos dois fluxos:

- `databases/maparadar/maparadar_radars.csv`
- `databases/maparadar/maparadar_dangerz.csv`
- `databases/base/base_radar.csv`
- `databases/base/base_dangerz.csv`

Arquivos usados no fluxo com MiraScript:

- `databases/converted/converted_radars.csv`
- `databases/converted/converted_dangerz.csv`

Esses arquivos são gerados no veículo usando MiraScript e contêm as coordenadas
proprietárias calculadas pela própria central RT6.

Arquivos opcionais para direções via OSM:

- `databases/openstreetmap/*.osm.pbf`
- `databases/openstreetmap/highway_index.npz`

Formato esperado para os CSVs do MapaRadar, sem cabeçalho:

```csv
-46.549897,-23.120720,Radar Fixo - 50 kmh@50
-43.192310,-22.910480,Lombada - 0 kmh@0
```

Os arquivos `base_*.csv` são referências limpas no formato RT6, usadas para
recuperar direções conhecidas. Por decisão de publicação, este repositório não
distribui esses dados, mas você pode utilizar a última versão disponível no fórum do MapaRadar mencionado acima como base, pretendo manter sempre uma versão mensal atualizada disponível.

### Uso: Fluxo 1, CSV Convertido via MiraScript

Use este caminho quando você já tiver os arquivos `converted_radars.csv` e
`converted_dangerz.csv` gerados pela central RT6 com MiraScript.

```bash
# Usa os CSVs convertidos pela central, quando disponíveis
python main.py
```

Se os arquivos convertidos existirem em `databases/converted/`, o programa usa
as coordenadas deles e evita recalcular coordenadas em Python.

### Uso: Fluxo 2, Conversão Direta em Python

Use este caminho para converter no computador, sem rodar MiraScript no veículo
para a atualização atual.

```bash
# Força a conversão de coordenadas em Python
python main.py --no-car
```

Esse modo usa `numpy` e `scipy`. Ele não chama MiraScript nem precisa que o
veículo esteja presente durante a conversão, mas ainda depende dos arquivos de
referência locais necessários para treinar/validar a interpolação de coordenadas.

### Opções Adicionais

```bash
# Calcula direções para pares novos usando índice OSM local ou Overpass API
python main.py --compute-dirs

# Processa apenas radares
python main.py --radar-only

# Processa apenas zonas de perigo
python main.py --dangerz-only
```

Para criar um índice OSM local de direções, coloque um PBF do Brasil em
`databases/openstreetmap/` e rode:

```bash
python main.py --build-osm-index
```

O PBF pode ser baixado, por exemplo, na página da Geofabrik para o Brasil:

https://download.geofabrik.de/south-america/brazil.html

### Saída Esperada

Após a conversão, os arquivos gerados ficam em:

```text
output/RADAR.csv
output/DANGERZ.csv
```

Eles são escritos em formato RT6, com quebras de linha CRLF e codificação ASCII.
Depois disso, use o RadarViewer v2.0 para gerar os arquivos `.LZW` aceitos pela
central.

### Preparando o Pendrive e Instalando no Veículo

Depois de gerar ou baixar a base final de atualização para RT6, prepare o
pendrive com cuidado. Essas centrais são sensíveis à leitura: qualquer erro no
software, nos arquivos ou no pendrive pode fazer a atualização falhar.

Procedimento de instalação:

1. Formate um pendrive em bom estado em FAT32, de preferência com alocação de
   4096 bytes.
2. Descompacte a base diretamente no pendrive, por exemplo usando WinRAR.
3. Ligue o automóvel e aguarde a central RT6 terminar de iniciar completamente.
4. Conecte o pendrive na porta USB do veículo.
5. Aguarde a central analisar o conteúdo e confirme a atualização quando for
   solicitado.
6. Aguarde a atualização terminar sem remover o pendrive.
7. Remova o pendrive somente ao final e confira os alertas na central.

Dicas para evitar erros com o pendrive:

- Use sempre um pendrive em bom estado e pouco usado.
- Formate em FAT32 pelo Windows; formatações feitas no macOS ou Linux podem
  causar incompatibilidades nessas centrais.
- Se o pendrive já tiver sido usado várias vezes, prefira formatação lenta,
  porque a formatação rápida pode não limpar completamente a mídia.
- Se o pendrive for muito usado, zere/restaure a mídia antes de formatar e
  copiar a atualização.

### Modos de Coordenadas

| Arquivos convertidos existem | Opção `--no-car` | Coordenadas usadas |
| --- | --- | --- |
| Sim | Não | Arquivos convertidos pela central |
| Sim | Sim | Interpolação Python |
| Não | Não | Interpolação Python como fallback |
| Não | Sim | Interpolação Python |

A conversão Python usa interpolação RBF com `scipy` treinada a partir de pares
conhecidos. Ela é útil quando não há arquivos convertidos pela central, mas a
maior fidelidade vem dos arquivos convertidos no próprio RT6.

### Direções dos Alertas

A direção (`dir`) de cada POI segue esta prioridade:

1. Coordenada exata encontrada no arquivo base.
2. Coordenada próxima no arquivo base, dentro de 50 unidades RT6.
3. Direção da via via OSM, apenas com `--compute-dirs`.
4. Valor `360`, indicando alerta em todas as direções.

Alguns itens ficam propositalmente com `360`, como radares móveis, lombadas,
pedágios e câmeras isoladas sem par confiável.

### Limitações

- O projeto não baixa dados automaticamente do MapaRadar.
- O repositório público não inclui bases, arquivos convertidos, PBFs OSM, índice
  OSM ou saídas geradas.
- O fallback via Overpass API requer internet e pode ser lento.
- A conversão Python depende da qualidade e cobertura dos pares de treinamento
  disponíveis localmente.

### Contribuindo

Contribuições são bem-vindas. Antes de abrir um pull request:

- Não inclua arquivos de `databases/`, `output/` ou `scripts/`.
- Rode `python main.py --help`.
- Rode uma checagem de sintaxe/importação nos arquivos Python.
- Descreva o veículo, firmware e arquivos usados para validar a mudança.

### Licença

MIT License. Consulte o arquivo [LICENSE](LICENSE).

---

## English Instructions

### Overview

This tool converts MapaRadar radar and danger-zone data into RT6-compatible CSV
files for Peugeot and Citroën vehicles with the RNEG RT6 navigation unit.

The RT6 unit imports POI data through `.LZW` files. This project generates the
two intermediate CSV files commonly used with RadarViewer v2.0:

| File | Contents |
| --- | --- |
| `RADAR.csv` | Fixed radars, mobile radars, speed cameras, traffic-light cameras |
| `DANGERZ.csv` | Highway police checkpoints, toll booths, speed bumps |

Basic flow:

```text
MapaRadar data -> python main.py -> output/RADAR.csv + output/DANGERZ.csv
```

### Two Supported Workflows

This project supports two conversion paths:

| Workflow | When to use it | How it works |
| --- | --- | --- |
| MiraScript-converted CSV | When you already generated `converted_radars.csv` and `converted_dangerz.csv` in the vehicle itself | The RT6 unit runs MiraScript, produces the proprietary coordinates, and this project uses those CSVs to build the final `RADAR.csv` and `DANGERZ.csv` files |
| Direct Python conversion | When you want to convert on the computer, without running MiraScript and without depending on the vehicle during conversion | Python computes RT6 coordinates by interpolation and writes the final CSV files directly |

The first workflow is usually the most faithful because it uses the proprietary
function from the RT6 unit itself. The second workflow is more convenient for
PC-based updates, but it requires the Python dependencies and enough local data
to build the coordinate interpolator.

### Credits and Community

This project builds on the work of the MapaRadar, c4clube, and clubepeugeot
communities, which preserved and shared knowledge about POI, radar, and RT6
updates. The original RT6 radar update discussion was maintained in the
MapaRadar forum:

https://forum.maparadar.com/viewtopic.php?t=61848

Please respect the community rules and the data usage terms.

### Requirements

- Python 3.8 or newer
- Dependencies from `requirements.txt` for all documented modes:
  - `numpy` and `scipy`: required for `--no-car`
  - `osmium`: required for `--build-osm-index`

The default mode, when using RT6-converted coordinate files, only uses Python's
standard library.

### Installation

```bash
git clone https://github.com/tomsnunes/peugeot-citroen-rt6-maparadar-updater.git
cd peugeot-citroen-rt6-maparadar-updater
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### File Preparation

Create these folders locally. They are ignored by Git.

```text
databases/
  maparadar/
    maparadar_radars.csv
    maparadar_dangerz.csv
  base/
    base_radar.csv
    base_dangerz.csv
  converted/
    converted_radars.csv
    converted_dangerz.csv
  openstreetmap/
    brazil-*.osm.pbf
output/
```

Files common to both workflows:

- `databases/maparadar/maparadar_radars.csv`
- `databases/maparadar/maparadar_dangerz.csv`
- `databases/base/base_radar.csv`
- `databases/base/base_dangerz.csv`

Files used by the MiraScript workflow:

- `databases/converted/converted_radars.csv`
- `databases/converted/converted_dangerz.csv`

These files are generated in the vehicle using MiraScript and contain the
proprietary coordinates calculated by the RT6 unit itself.

Optional files for OSM-based directions:

- `databases/openstreetmap/*.osm.pbf`
- `databases/openstreetmap/highway_index.npz`

Expected MapaRadar CSV format, without a header:

```csv
-46.549897,-23.120720,Radar Fixo - 50 kmh@50
-43.192310,-22.910480,Lombada - 0 kmh@0
```

The `base_*.csv` files are clean RT6 reference files used to recover known
directions. By publishing choice, this repository does not distribute those data
files, but you can use the latest version available at MapaRadar forum mentioned above as the base file, I will keep an updated monthly release on the forum too.

### Usage: Workflow 1, MiraScript-Converted CSV

Use this path when you already have `converted_radars.csv` and
`converted_dangerz.csv` generated by the RT6 unit with MiraScript.

```bash
# Uses RT6-converted CSV files when available
python main.py
```

If converted files exist in `databases/converted/`, the program uses their
coordinates and avoids recalculating coordinates in Python.

### Usage: Workflow 2, Direct Python Conversion

Use this path to convert on the computer, without running MiraScript in the
vehicle for the current update.

```bash
# Forces Python coordinate conversion
python main.py --no-car
```

This mode uses `numpy` and `scipy`. It does not call MiraScript and does not
require the vehicle to be present during conversion, but it still depends on the
local reference files needed to train/validate coordinate interpolation.

### Additional Options

```bash
# Computes directions for new pairs using a local OSM index or the Overpass API
python main.py --compute-dirs

# Process only radars
python main.py --radar-only

# Process only danger zones
python main.py --dangerz-only
```

To build a local OSM direction index, place a Brazil PBF file in
`databases/openstreetmap/` and run:

```bash
python main.py --build-osm-index
```

One source for Brazil PBF files is Geofabrik:

https://download.geofabrik.de/south-america/brazil.html

### Expected Output

The generated files are:

```text
output/RADAR.csv
output/DANGERZ.csv
```

They are written in RT6 format, with CRLF line endings and ASCII encoding. Use
RadarViewer v2.0 afterwards to generate the `.LZW` files accepted by the unit.

### Preparing the USB Drive and Installing in the Vehicle

After generating or downloading the final RT6 update package, prepare the USB
drive carefully. These head units are sensitive to read errors: any issue in the
software, files, or USB drive may cause the update to fail.

Installation procedure:

1. Format a healthy USB drive as FAT32, preferably with 4096-byte allocation.
2. Extract the update package directly to the USB drive, for example using
   WinRAR.
3. Start the vehicle and wait until the RT6 unit has fully finished booting.
4. Plug the USB drive into the vehicle USB port.
5. Wait for the unit to analyze the contents and confirm the update when
   prompted.
6. Wait until the update finishes without removing the USB drive.
7. Remove the USB drive only after completion and check the alerts on the unit.

Tips to avoid USB drive errors:

- Always use a healthy USB drive that is not heavily worn.
- Format as FAT32 on Windows; formatting on macOS or Linux may cause
  compatibility issues with these units.
- If the USB drive has been used many times, prefer a full/slow format because
  quick format may not fully clean the media.
- If the USB drive is heavily used, reset/wipe it before formatting and copying
  the update.

### Coordinate Modes

| Converted files present | `--no-car` option | Coordinates used |
| --- | --- | --- |
| Yes | No | RT6-converted files |
| Yes | Yes | Python interpolation |
| No | No | Python interpolation fallback |
| No | Yes | Python interpolation |

Python conversion uses `scipy` RBF interpolation trained from known coordinate
pairs. It is useful when converted files are unavailable, but the most faithful
coordinates come from the RT6-converted files.

### Alert Directions

The `dir` field is selected in this order:

1. Exact coordinate found in the base reference file.
2. Nearby coordinate in the base reference file, within 50 RT6 units.
3. OSM road direction, only with `--compute-dirs`.
4. `360`, meaning alert from all directions.

Some entries intentionally remain at `360`, such as mobile radars, speed bumps,
toll booths, and unpaired cameras without a reliable facing direction.

### Limitations

- This project does not automatically download MapaRadar data.
- The public repository does not include databases, converted files, OSM PBFs,
  OSM indexes, generated outputs, or scripts.
- The Overpass API fallback requires internet access and may be slow.
- Python coordinate conversion depends on the quality and coverage of local
  training pairs.

### Contributing

Contributions are welcome. Before opening a pull request:

- Do not include files from `databases/`, `output/`, or `scripts/`.
- Run `python main.py --help`.
- Run a syntax/import check for the Python files.
- Describe the vehicle, firmware, and files used to validate the change.

### License

MIT License. See [LICENSE](LICENSE).
