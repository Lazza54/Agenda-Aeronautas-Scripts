import pandas as pd
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
import datetime
from datetime import timedelta
import re
import unicodedata

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass

# --- 1. Configurações e Funções de Suporte ---

# ATENÇÃO: VERIFIQUE E AJUSTE ESTE CAMINHO CONFORME SEU AMBIENTE
# Este é o diretório onde os arquivos JSON e Excel de apoio devem estar localizados.
# Se este caminho estiver incorreto, o script não encontrará os arquivos de apoio.
BASE_COMMON_FILES_PATH = r'R:\SPECTRUM_SYSTEM\Aeronautas\Documentos_Comuns\Arquivos_Diversos'
ATIVIDADES_ESCALA_LATAM_FILE = 'AtividadesEscalaLATAM.json'

KEYWORDS_CODIGO_AMS_TREINAMENTO = [
    'INSTRUTOR', 'INICIAL', 'IFR', 'GROUND SCHOOL', 'FORMACAO', 'ENSINO', 'EQUIPAMENTO', 'CURSO', 'MOCK'
]
KEYWORDS_DESCRICAO_TEXTUAL_TREINAMENTO = [
    'CURSO', 'COMBATE', 'CHECK', 'CHECADOR', 'CAT', 'AVALIACAO', 'ARTIGOS'
]
KEYWORD_DESCRICAO_RESUMIDA_TREINAMENTO = 'TRAINING'

def _arquivo_entrada_eh_latam() -> bool:
    entrada_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    return bool(entrada_env) and "LATAM" in os.path.basename(entrada_env).upper()


def _resolver_json_apoio(file_name: str) -> str:
    base_dir = BASE_COMMON_FILES_PATH
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidatos = []

    # Prioriza catálogo LATAM local (quando existir), para permitir ajustes imediatos no módulo.
    if file_name == ATIVIDADES_ESCALA_LATAM_FILE:
        candidatos.append(os.path.join(script_dir, file_name))

    if _arquivo_entrada_eh_latam():
        stem, ext = os.path.splitext(file_name)
        candidatos.append(os.path.join(base_dir, f"{stem}_LATAM{ext}"))
        if file_name.lower() == "folgas.json":
            candidatos.append(os.path.join(base_dir, "folgas_regulamentares_LATAM.json"))
    candidatos.append(os.path.join(base_dir, file_name))
    for candidato in candidatos:
        if os.path.exists(candidato):
            return candidato
    return candidatos[0]


def _normalizar_texto(valor) -> str:
    if valor is None:
        return ''
    txt = str(valor).strip().upper()
    txt = unicodedata.normalize('NFKD', txt)
    return ''.join(ch for ch in txt if not unicodedata.combining(ch))


def _carregar_regras_treinamento_latam():
    """
    Retorna dois conjuntos:
    - tokens_catalogo: tokens de Activity válidos do AtividadesEscalaLATAM
    - tokens_treinamento: subconjunto de tokens que atendem às palavras-chave de treinamento
    """
    file_path = _resolver_json_apoio(ATIVIDADES_ESCALA_LATAM_FILE)
    if not os.path.exists(file_path):
        print(f"AVISO: Catálogo LATAM não encontrado: {file_path}")
        return set(), set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"AVISO: Falha ao carregar catálogo LATAM '{file_path}': {e}")
        return set(), set()

    atividades = []
    if isinstance(data, dict):
        atividades = data.get('atividades', [])
    elif isinstance(data, list):
        atividades = data

    tokens_catalogo = set()
    tokens_treinamento = set()

    for entry in atividades:
        if not isinstance(entry, dict):
            continue

        codigo_ams = _normalizar_texto(entry.get('codigo_ams', ''))
        codigo_iflight = _normalizar_texto(entry.get('codigo_iflight_neo', ''))
        descricao_resumida = _normalizar_texto(entry.get('descricao_resumida', ''))
        descricao_textual = _normalizar_texto(entry.get('descricao_textual', ''))

        tokens_entry = {t for t in [codigo_ams, codigo_iflight, descricao_resumida, descricao_textual] if t}
        if not tokens_entry:
            continue

        tokens_catalogo.update(tokens_entry)

        cond_ams = any(kw in codigo_ams for kw in KEYWORDS_CODIGO_AMS_TREINAMENTO)
        cond_textual = any(kw in descricao_textual for kw in KEYWORDS_DESCRICAO_TEXTUAL_TREINAMENTO)
        cond_resumida = KEYWORD_DESCRICAO_RESUMIDA_TREINAMENTO in descricao_resumida

        if cond_ams or cond_textual or cond_resumida:
            tokens_treinamento.update(tokens_entry)

    print(f"INFO: Catálogo LATAM carregado para treinamento. tokens_catalogo={len(tokens_catalogo)} | tokens_treinamento={len(tokens_treinamento)}")
    return tokens_catalogo, tokens_treinamento

def gerar_nome_csv_saida(nome_csv_entrada: str) -> str:
    """
    Gera o nome do arquivo CSV de saída no padrão:
    <stem_sem__TERCEIRA_VERSAO[_data]>_QUARTA_VERSAO_<DDMMAAAA_HHMMSS>.csv

    Args:
        nome_csv_entrada (str): O nome completo (ou caminho) do arquivo CSV de entrada.

    Returns:
        str: O nome do arquivo CSV de saída.
    """
    quarta_versao = "_QUARTA_VERSAO"
    # Extrai o nome do arquivo da string do caminho completo
    base_nome = os.path.basename(nome_csv_entrada)
    nome_sem_ext, ext = os.path.splitext(base_nome)

    # Remove qualquer sufixo de versão anterior e força o padrão
    nome_limpo = re.sub(r"(_TERCEIRA_VERSAO|_SEGUNDA_VERSAO|_PRIMEIRA_VERSAO)?(_\d{8}_\d{6})?$", "", nome_sem_ext)
    ts = datetime.datetime.now().strftime("%d%m%Y_%H%M%S")
    nome_csv_saida_base = f"{nome_limpo}{quarta_versao}_{ts}"
    return f"{nome_csv_saida_base}{ext}"

def determinar_diretorio_e_arquivo():
    """
    Função para permitir ao usuário selecionar o arquivo CSV de entrada.
    O arquivo de saída é salvo no mesmo diretório do CSV de entrada.
    Simula a função padronizada mencionada no prompt.
    """
    entrada_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')

    if entrada_env and os.path.isfile(entrada_env):
        output_dir = os.path.dirname(entrada_env)
        if output_dir and os.path.isdir(output_dir):
            print(f"📄 Arquivo de entrada (ENV): {entrada_env}")
            print(f"📂 Diretório de saída (ENV): {output_dir}")
            return entrada_env, output_dir

    root = tk.Tk()
    root.withdraw()  # Esconde a janela principal do Tkinter

    input_file_path = filedialog.askopenfilename(
        title="Selecione o arquivo CSV de entrada para processar",
        filetypes=[("Arquivos CSV", "*.csv")]
    )

    if not input_file_path:
        messagebox.showwarning("Seleção Cancelada", "Nenhum arquivo de entrada selecionado. O script será encerrado.")
        return None, None

    output_dir = os.path.dirname(input_file_path)

    return input_file_path, output_dir

def load_json_to_set(file_name, normalize_case=False):
    """
    Carrega um arquivo JSON e tenta extrair uma lista de valores para um set,
    adaptando-se a estruturas comuns (lista de simples, lista de dicionários,
    ou dicionário com chave raiz contendo lista).
    Tenta extrair o valor de chaves comuns ('name', 'code', 'id', 'value', 'type', 'description', 'date')
    se o item for um dicionário.
    Se normalize_case for True, todos os valores string serão convertidos para maiúsculas.
    """
    file_path = _resolver_json_apoio(file_name)
    if not os.path.exists(file_path):
        print(f"AVISO: Arquivo de apoio '{file_name}' NÃO ENCONTRADO em '{BASE_COMMON_FILES_PATH}'. Retornando set vazio.")
        return set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

            potential_list = None
            if isinstance(data, list):
                potential_list = data
            elif isinstance(data, dict):
                # Prioridade 1: Se o dicionário raiz tem apenas UMA chave cujo valor é uma lista, use essa lista
                list_values_in_root = [v for v in data.values() if isinstance(v, list)]
                if len(list_values_in_root) == 1:
                    potential_list = list_values_in_root[0]
                    print(f"INFO: Lista encontrada como único valor de lista no dicionário raiz em '{file_name}'.")
                else:
                    # Prioridade 2: Verificar chaves raiz comuns (mantido para compatibilidade)
                    # Adicionei 'voos', 'tipos_voo', 'atividades' aqui como chaves comuns
                    common_root_keys = ['data', 'items', 'types', 'entries', 'values', 'list', 'details', 'categories', 'voos', 'tipos_voo', 'atividades']
                    for r_key in common_root_keys:
                        if r_key in data and isinstance(data[r_key], list):
                            potential_list = data[r_key]
                            print(f"INFO: Lista encontrada em '{file_name}' sob a chave raiz: '{r_key}'.")
                            break
                    
                    # Tratamento especial para feriados.json (se for um dicionário onde chaves/valores são datas)
                    if potential_list is None and file_name == 'feriados.json':
                        if all(isinstance(v, str) for v in data.values()):
                            potential_list = list(data.values())
                            print(f"INFO: Feriados encontrados em '{file_name}' como valores de um dicionário.")
                        elif all(isinstance(k, str) for k in data.keys()):
                            potential_list = list(data.keys())
                            print(f"INFO: Feriados encontrados em '{file_name}' como chaves de um dicionário.")
                    
                    # Prioridade 3: Se ainda não encontrou lista, e é um dict, tente extrair de seus valores ou chaves
                    # (Esta parte foi aprimorada para lidar com listas aninhadas nos valores)
                    if potential_list is None:
                        temp_list_from_dict_values = []
                        all_values_simple_or_extractable = True
                        for val in data.values():
                            if isinstance(val, (str, int, float, bool, type(None))):
                                temp_list_from_dict_values.append(val)
                            elif isinstance(val, list): # Se o valor é uma lista, itere sobre seus elementos
                                for sub_item in val:
                                    if isinstance(sub_item, (str, int, float, bool, type(None))):
                                        temp_list_from_dict_values.append(sub_item)
                                    else:
                                        all_values_simple_or_extractable = False # Tipo não simples dentro da sub-lista
                                        break
                                if not all_values_simple_or_extractable: break # Saia se encontrou problema
                            elif isinstance(val, dict):
                                extracted_from_value_dict = None
                                # Adicionado 'IATA' e 'ICAO' para compatibilidade com aeroportos.json
                                # Este `common_item_keys` é o da função em geral.
                                for ik in ['name', 'code', 'value', 'type', 'description', 'id', 'date', 'IATA', 'ICAO']:
                                    if ik in val:
                                        extracted_from_value_dict = val[ik]
                                        break
                                if extracted_from_value_dict is not None and isinstance(extracted_from_value_dict, (str, int, float, bool, type(None))):
                                    temp_list_from_dict_values.append(extracted_from_value_dict)
                                else:
                                    all_values_simple_or_extractable = False
                                    break
                            else: # Outro tipo de objeto complexo não tratado (ex: objeto aninhado que não é dict/list simples)
                                all_values_simple_or_extractable = False
                                break
                        
                        if all_values_simple_or_extractable and temp_list_from_dict_values:
                            potential_list = temp_list_from_dict_values
                            print(f"INFO: Itens extraídos de valores de dicionário raiz em '{file_name}'.")
                        else:
                            # Se extrair valores falhou, tente as chaves
                            temp_list_from_dict_keys = []
                            all_keys_simple = True
                            for key in data.keys():
                                if isinstance(key, (str, int, float, bool, type(None))):
                                    temp_list_from_dict_keys.append(key)
                                else:
                                    all_keys_simple = False
                                    break
                            if all_keys_simple and temp_list_from_dict_keys:
                                potential_list = temp_list_from_dict_keys
                                print(f"INFO: Itens extraídos de chaves de dicionário raiz em '{file_name}'.")
                            else:
                                print(f"AVISO: O arquivo '{file_name}' é um dicionário com estrutura não reconhecida para extração de lista. Retornando set vazio.")
                                return set()

            if potential_list is None:
                print(f"AVISO: Estrutura inesperada para '{file_name}'. Esperado lista ou dicionário contendo lista. Retornando set vazio.")
                return set()

            final_set = set()
            # Ordem de preferência para chaves dentro de dicionários de itens (Adicionado IATA e ICAO)
            common_item_keys = ['name', 'code', 'value', 'type', 'description', 'id', 'date', 'IATA', 'ICAO']

            for item in potential_list:
                if isinstance(item, dict):
                    extracted_value = None
                    for ik in common_item_keys:
                        if ik in item:
                            extracted_value = item[ik]
                            break
                    if extracted_value is not None:
                        if isinstance(extracted_value, str):
                            val_to_add = extracted_value
                            if normalize_case:
                                val_to_add = val_to_add.upper()
                            final_set.add(val_to_add)
                        elif isinstance(extracted_value, (int, float, bool, type(None))):
                            final_set.add(str(extracted_value))
                        else:
                            print(f"AVISO: Valor extraído de '{file_name}' (chave '{ik}') é do tipo '{type(extracted_value)}' e não é um tipo simples (string, número, bool). Ignorando este valor.")
                    else:
                        print(f"AVISO: Dicionário em '{file_name}' (item: {item}) não contém chaves comuns ('{', '.join(common_item_keys)}') para extração de valor. Ignorando este item.")
                elif isinstance(item, str):
                    val_to_add = item
                    if normalize_case:
                        val_to_add = val_to_add.upper()
                    final_set.add(val_to_add)
                elif isinstance(item, (int, float, bool, type(None))):
                    final_set.add(str(item))
                else:
                    print(f"AVISO: Item de tipo inesperado ou não hashable em '{file_name}' (tipo: {type(item)}, item: {item}). Ignorando.")
            
            print(f"INFO: Arquivo '{file_name}' carregado e {len(final_set)} itens extraídos para o set.")
            return final_set

    except json.JSONDecodeError:
        print(f"ERRO: Falha ao decodificar JSON do arquivo '{file_name}'. Verifique a sintaxe JSON. Retornando set vazio.")
        return set()
    except Exception as e:
        print(f"ERRO ao carregar '{file_name}': {e}. Retornando set vazio.")
        return set()

def load_excel_file(file_name):
    """Carrega um arquivo Excel."""
    file_path = os.path.join(BASE_COMMON_FILES_PATH, file_name)
    if not os.path.exists(file_path):
        print(f"AVISO: Arquivo Excel '{file_name}' NÃO ENCONTRADO em '{BASE_COMMON_FILES_PATH}'.")
        return None
    try:
        df_excel = pd.read_excel(file_path)
        print(f"Arquivo '{file_name}' carregado com sucesso.")
        return df_excel
    except ImportError:
        print(f"ERRO: A biblioteca 'openpyxl' não está instalada. Para ler arquivos .xlsx, instale-a: pip install openpyxl")
        return None
    except Exception as e:
        print(f"ERRO ao carregar o arquivo Excel '{file_name}': {e}")
        return None

# --- 2. Carregamento dos Arquivos de Apoio ---
def carregar_arquivos_apoio():
    """Carrega todos os arquivos JSON e Excel de apoio."""
    print(f"\nTentando carregar arquivos de apoio do diretório: {BASE_COMMON_FILES_PATH}")
    if not os.path.exists(BASE_COMMON_FILES_PATH):
        messagebox.showerror("Erro de Caminho",
                             f"O diretório BASE_COMMON_FILES_PATH não existe:\n{BASE_COMMON_FILES_PATH}\n"
                             "Por favor, ajuste o caminho no código ou crie o diretório.")
        return None

    data = {
        'todos_aeroportos': load_json_to_set('todos_aeroportos.json', normalize_case=True),
        'tipos_voo': load_json_to_set('tipos_voo.json', normalize_case=True),
        'tipos_treinamentos': load_json_to_set('tipos_treinamentos.json', normalize_case=True),
        'tipos_reserva': load_json_to_set('tipos_reserva.json', normalize_case=True),
        'tipos_plantao': load_json_to_set('tipos_plantao.json', normalize_case=True),
        'folgas': load_json_to_set('folgas.json', normalize_case=True),
        'feriados': load_json_to_set('feriados.json'), # Feriados podem ser datas/strings, não forçar UPPERCASE
        'siglas_sabre': load_excel_file('Siglas Sabre 1.xlsx')
    }
    print("Carregamento de arquivos de apoio concluído.")

    print("\n--- Conteúdo dos Sets Carregados (para verificação) ---")
    for key, value in data.items():
        if isinstance(value, set):
            print(f"{key}: {sorted(list(value))}")
    print("-----------------------------------------------------")

    return data

# --- 3. Função Principal de Processamento ---
def processar_dados_aeronautica():
    """
    Função principal que orquestra o carregamento, processamento e salvamento
    dos dados de aeronáutica.
    """
    input_csv_path, output_dir = determinar_diretorio_e_arquivo()

    if not input_csv_path or not output_dir:
        print("Operação cancelada pelo usuário ou caminhos inválidos.")
        return

    print(f"\nArquivo de entrada selecionado: {input_csv_path}")
    print(f"Diretório de saída selecionado: {output_dir}")

    arquivo_eh_latam = 'LATAM' in os.path.basename(input_csv_path).upper()
    print(f"Arquivo LATAM detectado: {'SIM' if arquivo_eh_latam else 'NÃO'}")

    try:
        df = pd.read_csv(input_csv_path) 
        for col in ['Checkin', 'Start', 'End', 'Checkout']:
            if col in df.columns:
                df[col] = df[col].astype(str)

        linhas_inicial = len(df)
        print(f"\n{'='*80}")
        print(f"RASTREAMENTO DE LINHAS - Início do processamento: {linhas_inicial} linhas")
        print(f"{'='*80}")
        print(f"Arquivo CSV de entrada carregado. Linhas iniciais: {linhas_inicial}")
    except Exception as e:
        messagebox.showerror("Erro de Leitura CSV", f"Erro ao carregar o arquivo CSV: {e}\n"
                                                      "Verifique se o arquivo não está corrompido ou aberto em outro programa.")
        print(f"ERRO: Error ao carregar o arquivo CSV: {e}")
        return

    apoio_data = carregar_arquivos_apoio()
    if apoio_data is None:
        print("Falha ao carregar arquivos de apoio. Encerrando.")
        return

    tipos_voo = apoio_data.get('tipos_voo', set())
    folgas = apoio_data.get('folgas', set())
    tipos_reserva = apoio_data.get('tipos_reserva', set())
    tipos_plantao = apoio_data.get('tipos_plantao', set())
    tipos_treinamentos = apoio_data.get('tipos_treinamentos', set())
    feriados = apoio_data.get('feriados', set())

    # --- 4. Preparação dos Dados: Verificação e Conversão de Tipos ---
    required_cols = ['Activity', 'Id_Leg', 'Checkin', 'Start', 'End', 'Checkout']
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        messagebox.showerror("Colunas Ausentes",
                             f"As seguintes colunas obrigatórias não foram encontradas no CSV de entrada: {', '.join(missing_cols)}\n"
                             "Por favor, verifique se o arquivo CSV está correto e tente novamente.")
        print(f"ERRO: Colunas obrigatórias ausentes: {missing_cols}. Encerrando.")
        return

    time_cols = ['Checkin', 'Start', 'End', 'Checkout']
    print("\n--- Processamento de Colunas de Data/Hora ---")
    
    # DIAGNÓSTICO: Amostra de datas ANTES da conversão
    print("\n🔍 DIAGNÓSTICO - Amostra de valores ORIGINAIS nas colunas de data:")
    for col in time_cols:
        if col in df.columns:
            amostra = df[col].head(10).tolist()
            print(f"  {col}: {amostra}")
    print()
    
    for col in time_cols:
        print(f"Processando coluna: '{col}'")
        
        # Keep original string values for multiple parsing attempts
        original_col_strings = df[col].astype(str)
        
        # Temporary series to store converted datetimes
        converted_datetimes = pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns]')

        # Attempt 1: Convert using explicit DD/MM/YYYY HH:MM format (as per ANALYZE_IMAGES)
        try_string_format = pd.to_datetime(original_col_strings, format='%d/%m/%Y %H:%M', errors='coerce')
        converted_datetimes.update(try_string_format) # Update only non-NaT values
        sucesso_formato_string = try_string_format.notna().sum()
        print(f"  → Tentativa 1 (formato DD/MM/YYYY HH:MM): {sucesso_formato_string} valores convertidos")

        # Attempt 2: For values still NaT, try formato DDMMMYY HH:MM (ex: 01DEZ17 02:00)
        needs_format2_idx = converted_datetimes.isnull()
        if needs_format2_idx.any():
            format2_candidates = original_col_strings.loc[needs_format2_idx]
            # Mapear abreviações de mês em português
            mes_map = {
                'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 
                'MAI': '05', 'JUN': '06', 'JUL': '07', 'AGO': '08',
                'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
            }
            # Converter formato DDMMMYY HH:MM para DD/MM/20YY HH:MM
            def converter_formato_brasileiro(s):
                try:
                    # Extrair partes: 01DEZ17 02:00 -> 01, DEZ, 17, 02:00
                    if len(s) >= 13:  # Tamanho mínimo: "01DEZ17 00:00" = 13 caracteres
                        dia = s[0:2]
                        mes_abrev = s[2:5].upper()
                        ano = s[5:7]
                        hora = s[8:]
                        mes_num = mes_map.get(mes_abrev)
                        if mes_num:
                            # Interpretação de ano: 00-50 = 2000-2050, 51-99 = 1951-1999
                            # Mas para este dataset: 17-23 são 2017-2023
                            ano_int = int(ano)
                            if ano_int <= 50:
                                ano_completo = f"20{ano}"  # 2000-2050
                            else:
                                ano_completo = f"19{ano}"  # 1951-1999
                            return f"{dia}/{mes_num}/{ano_completo} {hora}"
                except:
                    pass
                return None
            
            format2_converted = format2_candidates.apply(converter_formato_brasileiro)
            try_format2 = pd.to_datetime(format2_converted, format='%d/%m/%Y %H:%M', errors='coerce')
            converted_datetimes.update(try_format2)
            sucesso_formato2 = try_format2.notna().sum()
            print(f"  → Tentativa 2 (formato DDMMMYY HH:MM - português): {sucesso_formato2} valores convertidos")

        # Attempt 3: For values still NaT, try converting as Excel serial numbers
        needs_serial_conversion_idx = converted_datetimes.isnull()
        if needs_serial_conversion_idx.any():
            serial_candidates = original_col_strings.loc[needs_serial_conversion_idx]
            
            # Convert these candidates to numeric
            numeric_attempt = pd.to_numeric(serial_candidates, errors='coerce')
            
            # Filter for values that became numbers and are plausible Excel serials (e.g., year 2017+ would be > 42736)
            # Using a more general range (1 to 60000) to cover very old dates, but still filter garbage
            is_serial_date_candidate = numeric_attempt.notna() & (numeric_attempt >= 1) & (numeric_attempt < 60000) 

            # Convert these specific numeric candidates to datetime
            try_serial_format = pd.to_datetime(
                numeric_attempt.loc[is_serial_date_candidate],
                unit='D',
                origin='1899-12-30',
                errors='coerce'
            )
            converted_datetimes.update(try_serial_format) # Update only non-NaT values
            sucesso_serial = try_serial_format.notna().sum()
            print(f"  → Tentativa 3 (Excel serial numbers): {sucesso_serial} valores convertidos")

        # Assign the final converted series back to the DataFrame column
        df[col] = converted_datetimes
        
        # Report on remaining NaTs
        invalid_count = df[col].isnull().sum()
        if invalid_count > 0:
            print(f"  ⚠️  AVISO: {invalid_count} valores ainda são NaT na coluna '{col}' após tentativas de conversão.")
            # Mostrar exemplos de valores que falharam
            falhas = original_col_strings[df[col].isnull()].head(5).tolist()
            print(f"     Exemplos de valores que falharam: {falhas}")
        else:
            print(f"  ✓ Coluna '{col}' convertida com sucesso (100% das linhas).")
    
    linhas_apos_conversao = len(df)
    print(f"\n{'='*80}")
    print(f"RASTREAMENTO: Após conversão de datas: {linhas_apos_conversao} linhas (perdidas: {linhas_inicial - linhas_apos_conversao})")
    print(f"{'='*80}")
    
    # DIAGNÓSTICO: Análise de anos/meses APÓS conversão
    print("\n🔍 DIAGNÓSTICO - Análise temporal APÓS conversão:")
    for col in ['Start', 'Checkin']:
        if col in df.columns and df[col].notna().any():
            datas_validas = df[df[col].notna()]
            if len(datas_validas) > 0:
                anos = datas_validas[col].dt.year.value_counts().sort_index()
                print(f"\n  Distribuição de ANOS na coluna '{col}':")
                for ano, count in anos.items():
                    print(f"    {ano}: {count} linhas")
                
                # Mostrar meses de 2019+ para verificar quais estão faltando
                df_2019_plus = datas_validas[datas_validas[col].dt.year >= 2019].copy()
                if len(df_2019_plus) > 0:
                    df_2019_plus['Ano_Mes'] = df_2019_plus[col].dt.to_period('M')
                    anos_meses = df_2019_plus['Ano_Mes'].value_counts().sort_index()
                    print(f"\n  Meses de 2019+ presentes:")
                    for mes, count in anos_meses.items():
                        print(f"    {mes}: {count} linhas")
    print("-------------------------------------------\n")

    print("\n--- Análise de Linhas com Checkin/Checkout Inválidos ---")
    initial_rows_after_load = len(df)
    
    # Identificar linhas que TÊM Checkin/Checkout inválidos
    linhas_invalidas = df[df['Checkin'].isna() | df['Checkout'].isna()]
    
    if len(linhas_invalidas) > 0:
        print(f"ℹ️  INFORMAÇÃO: {len(linhas_invalidas)} linhas têm Checkin/Checkout vazios (normal para folgas, reservas, plantões, etc.)")
        print(f"\nDistribuição por Activity:")
        if 'Activity' in linhas_invalidas.columns:
            contagem = linhas_invalidas['Activity'].value_counts()
            for activity, count in contagem.head(20).items():
                print(f"  - {activity}: {count} linhas")
        print("\n⚠️  IMPORTANTE: Estas linhas NÃO serão removidas, pois são atividades legítimas sem check-in/check-out.\n")
    
    # NÃO remover linhas com Checkin/Checkout vazios - elas são legítimas!
    # df.dropna(subset=['Checkin', 'Checkout'], inplace=True)  # COMENTADO - NÃO REMOVER!
    
    linhas_apos_dropna = len(df)
    
    print(f"\n{'='*80}")
    print(f"RASTREAMENTO: Todas as {linhas_apos_dropna} linhas mantidas (nenhuma removida)")
    print(f"{'='*80}\n")

    if df.empty:
        messagebox.showerror("Erro de Dados",
                             "O DataFrame está vazio após a conversão de datas e remoção de linhas com dados inválidos. "
                             "Verifique o formato das colunas de tempo no seu CSV de entrada e o conteúdo delas.")
        print("ERRO: DataFrame vazio após processamento de datas. Encerrando.")
        return

    print("\nInformações sobre o DataFrame após conversão de datas e remoção de NaNs (antes de remover colunas extras):")
    df.info()
    print("-" * 30)

    # REMOVER COLUNAS ESPECÍFICAS
    cols_to_remove = ['AcVer', 'DD', 'CAT', 'Crew']
    existing_cols_to_remove = [col for col in cols_to_remove if col in df.columns]
    if existing_cols_to_remove:
        df.drop(columns=existing_cols_to_remove, inplace=True)
        print(f"Colunas removidas: {', '.join(existing_cols_to_remove)}")
    else:
        print("Nenhuma das colunas 'AcVer', 'DD', 'CAT', 'Crew' encontrada para remoção.")

    # Normalizar Id_Leg: remover espaços e converter para maiúsculas
    df['Id_Leg_Norm'] = df['Id_Leg'].astype(str).str.strip().str.upper()

    # MODIFICAÇÃO CHAVE: Extrair o prefixo alfabético da Activity para Activity_Norm
    # Isso vai transformar 'AD5046' em 'AD', 'FR' em 'FR', etc.
    # Usa expressão regular para pegar um ou mais caracteres alfabéticos no início da string.
    df['Activity_Norm'] = df['Activity'].astype(str).str.upper().str.extract(r'^([A-Z]+)', expand=False)
    # Para casos onde a atividade não começa com letras (ex: '12345'), ou se str.extract retornar NaN,
    # usamos a Activity original em maiúsculas (para tentar match direto caso os JSONs tenham nomes completos)
    df['Activity_Norm'] = df['Activity_Norm'].fillna(df['Activity'].astype(str).str.upper())

    # Atividades iniciadas por 'LA' também devem ser tratadas como voo,
    # mesmo quando a sigla exata não estiver cadastrada em tipos_voo.json.
    cond_activity_la = df['Activity'].astype(str).str.upper().str.startswith('LA', na=False)
    cond_activity_voo = df['Activity_Norm'].isin(tipos_voo) | cond_activity_la


    # --- 5. Cálculos e Criação de Novas Colunas ---
    print("\nIniciando cálculos das novas colunas...")

    # 6.1 – Tempo Operacao = End - Start (CORREÇÃO SOLICITADA)
    df['Tempo Operacao'] = df['End'] - df['Start']

    # 6.2 – Tempo Apresentacao = Start – Checkin
    # Condição: Id_Leg_Norm in ['-I', '-IF'] AND Activity_Norm in tipos_voo
    cond_id_leg_apres = df['Id_Leg_Norm'].isin(['-I', '-IF'])
    cond_activity_apres = cond_activity_voo
    
    # Debug detalhado e aprimorado para Tempo Apresentacao
    print(f"\n--- Debug Tempo Apresentacao ---")
    print(f"  Tipos de Voo carregados (tipos_voo.json): {sorted(list(tipos_voo))}")
    print(f"  {cond_id_leg_apres.sum()} linhas atendem a Id_Leg_Norm in ['-I', '-IF'].")
    print(f"  {cond_activity_apres.sum()} linhas atendem a Activity_Norm in tipos_voo.")
    
    cond_apresentacao = cond_id_leg_apres & cond_activity_apres
    df['Tempo Apresentacao'] = np.where(cond_apresentacao, df['Start'] - df['Checkin'], pd.NaT)
    print(f"  {cond_apresentacao.sum()} linhas atendem à condição COMBINADA para 'Tempo Apresentacao'.")

    if cond_apresentacao.sum() == 0:
        print(f"  AVISO: Nenhuma linha atendeu à condição combinada para 'Tempo Apresentacao'.")
        print(f"  Possíveis causas: ")
        
        not_id_leg = df.loc[~cond_id_leg_apres, 'Id_Leg_Norm'].value_counts().head(5)
        if not_id_leg.empty:
            print(f"    - Todas as linhas têm Id_Leg_Norm em ['-I', '-IF'] (ou a coluna está vazia após normalização).")
        else:
            print(f"    - Exemplos de Id_Leg_Norm que *NÃO* são '-I' ou '-IF':\n{not_id_leg.to_string()}")

        not_activity_norm = df.loc[~cond_activity_apres, 'Activity_Norm'].value_counts().head(5)
        if not_activity_norm.empty:
            print(f"    - Todas as linhas têm Activity_Norm em tipos_voo (ou a coluna está vazia após normalização).")
        else:
            print(f"    - Exemplos de Activity_Norm que *NÃO* estão em tipos_voo.json:\n{not_activity_norm.to_string()}")

        if cond_id_leg_apres.sum() > 0:
            failed_activity_sample = df.loc[cond_id_leg_apres & (~cond_activity_apres), ['Activity', 'Id_Leg', 'Activity_Norm', 'Id_Leg_Norm']].head(10)
            if not failed_activity_sample.empty:
                print(f"    - Linhas com Id_Leg_Norm VÁLIDO para Tempo Apresentacao, mas Activity_Norm INVÁLIDO (primeiras 10):\n{failed_activity_sample.to_string()}")
        
    print(f"---------------------------\n")

    # 6.3 – Tempo Corte = Checkout – End
    # Condição: Id_Leg_Norm in ['-IF', '-F'] AND Activity_Norm in tipos_voo
    cond_id_leg_corte = df['Id_Leg_Norm'].isin(['-IF', '-F'])
    cond_activity_corte = cond_activity_voo # Reutilizando tipos_voo + prefixo LA
    
    # Debug detalhado e aprimorado para Tempo Corte
    print(f"\n--- Debug Tempo Corte ---")
    print(f"  Tipos de Voo carregados (tipos_voo.json): {sorted(list(tipos_voo))}") # Contexto
    print(f"  {cond_id_leg_corte.sum()} linhas atendem a Id_Leg_Norm in ['-IF', '-F'].")
    print(f"  {cond_activity_corte.sum()} linhas atendem a Activity_Norm in tipos_voo.")
    
    cond_corte = cond_id_leg_corte & cond_activity_corte # Condição combinada
    
    calculated_temp_corte_val = df['Checkout'] - df['End']
    
    df['Tempo Corte'] = np.where(cond_corte, calculated_temp_corte_val, pd.NaT)
    
    print(f"  {cond_corte.sum()} linhas atendem à condição COMBINADA para 'Tempo Corte'.")

    if cond_corte.sum() == 0:
        print(f"  AVISO: Nenhuma linha atendeu à condição combinada para 'Tempo Corte'.")
        print(f"  Possíveis causas: ")
        
        not_id_leg = df.loc[~cond_id_leg_corte, 'Id_Leg_Norm'].value_counts().head(5)
        if not_id_leg.empty:
            print(f"    - Todas as linhas têm Id_Leg_Norm em ['-IF', '-F'].")
        else:
            print(f"    - Exemplos de Id_Leg_Norm que *NÃO* são '-IF' ou '-F':\n{not_id_leg.to_string()}")

        not_activity_norm = df.loc[~cond_activity_corte, 'Activity_Norm'].value_counts().head(5)
        if not_activity_norm.empty:
            print(f"    - Todas as linhas têm Activity_Norm em tipos_voo.")
        else:
            print(f"    - Exemplos de Activity_Norm que *NÃO* estão em tipos_voo.json:\n{not_activity_norm.to_string()}")

        if cond_id_leg_corte.sum() > 0:
            failed_activity_sample = df.loc[cond_id_leg_corte & (~cond_activity_corte), ['Activity', 'Id_Leg', 'Activity_Norm', 'Id_Leg_Norm']].head(10)
            if not failed_activity_sample.empty:
                print(f"    - Linhas com Id_Leg_Norm VÁLIDO para Tempo Corte, mas Activity_Norm INVÁLIDO (primeiras 10):\n{failed_activity_sample.to_string()}")
    else:
        print(f"  Verificando exemplos calculados para 'Tempo Corte':")
        calculated_samples = df.loc[cond_corte, ['Activity', 'Id_Leg', 'End', 'Checkout', 'Tempo Corte']].head(5)
        print(calculated_samples.to_string())
    print("-----------------------------------------------------------\n")
    
    
    # 6.4 – Tempo Solo = Start da próxima linha cronológica - End da linha atual
    # Regras: Activity_Norm in tipos_voo AND Id_Leg_Norm NOT IN ['-IF', '-F']
    
    # Calculate Next_Start using simple shift(-1) (for next chronological row)
    df['Next_Start_Solo_Temp'] = df['Start'].shift(-1)
    
    # NOVAS CONDIÇÕES COMBINADAS para Tempo Solo
    cond_solo_activity = cond_activity_voo
    cond_solo_id_leg = ~df['Id_Leg_Norm'].isin(['-IF', '-F']) # NOT IN ['-IF', '-F']
    
    cond_solo_final = cond_solo_activity & cond_solo_id_leg
    
    # Debug detalhado para Tempo Solo
    print(f"\n--- Debug Tempo Solo ---")
    print(f"  Tipos de Voo carregados (tipos_voo.json): {sorted(list(tipos_voo))}")
    print(f"  {cond_solo_activity.sum()} linhas atendem a Activity_Norm in tipos_voo.")
    print(f"  {cond_solo_id_leg.sum()} linhas atendem a Id_Leg_Norm NOT IN ['-IF', '-F'].")
    
    # Apply the calculation only where cond_solo_final is True
    df['Tempo Solo'] = np.where(cond_solo_final, df['Next_Start_Solo_Temp'] - df['End'], pd.NaT)
    
    # Count how many non-NaT values were calculated for Tempo Solo
    calculated_solo_count = df['Tempo Solo'].notna().sum()
    print(f"  {calculated_solo_count} valores de 'Tempo Solo' foram calculados (não NaT).")

    if calculated_solo_count == 0:
        print(f"  AVISO: Nenhuma linha resultou em um cálculo válido para 'Tempo Solo'.")
        print(f"  Possíveis causas: ")
        not_activity_norm_solo = df.loc[~cond_solo_activity, 'Activity_Norm'].value_counts().head(5)
        if not_activity_norm_solo.empty:
            print(f"    - Todas as linhas têm Activity_Norm em tipos_voo (ou a coluna está vazia após normalização).")
        else:
            print(f"    - Exemplos de Activity_Norm que *NÃO* estão em tipos_voo.json:\n{not_activity_norm_solo.to_string()}")

        not_id_leg_solo = df.loc[~cond_solo_id_leg, 'Id_Leg_Norm'].value_counts().head(5)
        if not_id_leg_solo.empty:
            print(f"    - Todas as linhas têm Id_Leg_Norm NOT IN ['-IF', '-F'] (ou a coluna está vazia após normalização).")
        else:
            print(f"    - Exemplos de Id_Leg_Norm que *NÃO* atendem à condição NOT IN ['-IF', '-F']:\n{not_id_leg_solo.to_string()}")

        if cond_solo_activity.sum() > 0 or cond_solo_id_leg.sum() > 0:
            failed_combined_sample = df.loc[cond_solo_activity ^ cond_solo_id_leg, ['Activity', 'Id_Leg', 'Activity_Norm', 'Id_Leg_Norm']].head(10)
            if not failed_combined_sample.empty:
                print(f"    - Linhas que atendem APENAS UMA das condições para Tempo Solo (primeiras 10):\n{failed_combined_sample.to_string()}")

    else:
        print(f"  Verificando exemplos calculados para 'Tempo Solo':")
        calculated_samples_solo = df.loc[df['Tempo Solo'].notna(), ['Activity', 'Id_Leg', 'Start', 'End', 'Next_Start_Solo_Temp', 'Tempo Solo']].head(5)
        print(calculated_samples_solo.to_string())

    print(f"---------------------------\n")

    df.drop(columns=['Next_Start_Solo_Temp'], inplace=True) # Drop the temporary grouped column

    # 6.5 – Tempo Jornada = (Checkout – Checkin) + 30 minutos
    # Condição: Id_Leg_Norm in ['-IF', '-F'] AND Activity_Norm NOT in folgas
    cond_jornada = (df['Id_Leg_Norm'].isin(['-IF', '-F'])) & (~df['Activity_Norm'].isin(folgas))
    df['Tempo Jornada'] = np.where(cond_jornada, (df['Checkout'] - df['Checkin']), pd.NaT)

    # 6.6 – Tempo Repouso = Checkin da próxima linha – Checkout da linha atual
    # Condição: Id_Leg_Norm in ['-IF', '-F'] AND Activity_Norm NOT in folgas
    df['Next_Checkin_Repouso'] = df['Checkin'].shift(-1)
    cond_repouso = (df['Id_Leg_Norm'].isin(['-IF', '-F'])) & (~df['Activity_Norm'].isin(folgas))
    df['Tempo Repouso'] = np.where(cond_repouso, df['Next_Checkin_Repouso'] - df['Checkout'], pd.NaT)
    df.drop(columns=['Next_Checkin_Repouso'], inplace=True)

    # --- DEBUGGING E CORREÇÃO DE TIPOS PARA TIMEDELTA ---
    print(f"\nDebug: Verificando e corrigindo tipos de Timedelta antes dos cálculos 'Extra'...")
    
    timedelta_cols = ['Tempo Operacao', 'Tempo Apresentacao', 'Tempo Corte', 'Tempo Solo', 'Tempo Jornada', 'Tempo Repouso']
    
    for td_col in timedelta_cols:
        if td_col in df.columns:
            current_dtype = df[td_col].dtype
            print(f"  Processando coluna '{td_col}'. Dtype atual: {current_dtype}")

            if pd.api.types.is_timedelta64_dtype(df[td_col]):
                print(f"  Coluna '{td_col}' já é timedelta64[ns]. Nenhuma conversão extra necessária.")
            elif pd.api.types.is_datetime64_any_dtype(df[td_col]): # Check if it's datetime
                print(f"  AVISO GRAVE: Coluna '{td_col}' é inesperadamente do tipo datetime64[ns]! "
                      "Isso deveria ser um timedelta. Forçando NaT para esta coluna para evitar o crash. "
                      "Isso indica um problema na geração desta coluna.")
                df[td_col] = pd.Series([pd.NaT] * len(df), dtype='timedelta64[ns]')
            else: # Try to convert if it's neither datetime nor timedelta
                print(f"  Tentando converter coluna '{td_col}' de {current_dtype} para timedelta64[ns] com coerção.")
                original_dtype_for_log = current_dtype 
                df[td_col] = pd.to_timedelta(df[td_col], errors='coerce')
                if not pd.api.types.is_timedelta64_dtype(df[td_col]): # Check if conversion was successful
                    print(f"  ATENÇÃO: Coluna '{td_col}' não pôde ser convertida para timedelta64[ns]. Permaneceu como {df[td_col].dtype}. Forçando NaT.")
                    df[td_col] = pd.Series([pd.NaT] * len(df), dtype='timedelta64[ns]')
                else:
                    print(f"  Coluna '{td_col}' teve seu dtype alterado de {original_dtype_for_log} para {df[td_col].dtype} (coerção para Timedelta).")
            
            if pd.api.types.is_object_dtype(df[td_col]):
                 print(f"  AVISO: Coluna '{td_col}' ainda contém objetos após a tentativa de conversão para timedelta. Isso pode causar problemas.")
                 df[td_col] = df[td_col].apply(lambda x: x if pd.isna(x) or isinstance(x, (pd.Timedelta, np.timedelta64)) else pd.NaT)

    print("-" * 30)

    # As colunas Tempo Repouso Extra dependem de Tempo Repouso.
    df['Tempo Repouso Extra Simples'] = df['Tempo Repouso'] - timedelta(hours=12)
    df['Tempo Repouso Extra Composta'] = df['Tempo Repouso'] - timedelta(hours=16)
    df['Tempo Repouso Extra Revezamento'] = df['Tempo Repouso'] - timedelta(hours=24)

    # 6.10 – Tempo Reserva = Tempo Operacao (CONDIÇÃO ALTERADA PARA 'IN')
    # Condição: Activity_Norm IN tipos_reserva
    cond_reserva = df['Activity_Norm'].isin(tipos_reserva)
    if arquivo_eh_latam:
        cond_reserva = cond_reserva | (df['Activity_Norm'] == 'ASB')
    df['Tempo Reserva'] = np.where(cond_reserva, df['Tempo Operacao'], pd.NaT)

    # 6.11 - Tempo Plantao = Tempo Operacao (CONDIÇÃO ALTERADA PARA 'IN')
    # Condição: Activity_Norm IN tipos_plantao
    cond_plantao = df['Activity_Norm'].isin(tipos_plantao)
    if arquivo_eh_latam:
        cond_plantao = cond_plantao | (df['Activity_Norm'] == 'HSB')
    df['Tempo Plantao'] = np.where(cond_plantao, df['Tempo Operacao'], pd.NaT)

    # 6.12 - Tempo Treinamento = Tempo Operacao
    # Regra base: Activity_Norm IN tipos_treinamentos
    cond_treinamento = df['Activity_Norm'].isin(tipos_treinamentos)

    # Regra LATAM solicitada:
    # - Activity deve existir no AtividadesEscalaLATAM;
    # - Checkin e Start com mesmo hh:mm (atividade de terra, não voo);
    # - entrada do catálogo deve atender palavras-chave em codigo_ams / descricao_textual / descricao_resumida.
    if arquivo_eh_latam:
        tokens_catalogo_latam, tokens_treinamento_latam = _carregar_regras_treinamento_latam()

        if tokens_catalogo_latam and tokens_treinamento_latam:
            activity_for_match = df['Activity'].astype(str).str.strip().str.upper()

            def _activity_casa_tokens(activity_val, tokens):
                if not activity_val or activity_val == 'NAN':
                    return False
                if activity_val in tokens:
                    return True
                return any(activity_val.startswith(tk) for tk in tokens if tk and len(tk) >= 2)

            cond_catalogo_latam = activity_for_match.apply(lambda a: _activity_casa_tokens(a, tokens_catalogo_latam))
            cond_treinamento_keywords_latam = activity_for_match.apply(lambda a: _activity_casa_tokens(a, tokens_treinamento_latam))

            checkin_hhmm = df['Checkin'].dt.strftime('%H:%M')
            start_hhmm = df['Start'].dt.strftime('%H:%M')
            cond_terra_hhmm = df['Checkin'].notna() & df['Start'].notna() & checkin_hhmm.eq(start_hhmm)
            cond_nao_voo_id_leg = ~df['Id_Leg'].astype(str).str.upper().str.contains('LA', na=False)

            cond_regra_treinamento_latam = (
                cond_catalogo_latam
                & cond_treinamento_keywords_latam
                & cond_terra_hhmm
                & cond_nao_voo_id_leg
            )
            print(
                f"DEBUG LATAM Treinamento: catálogo={cond_catalogo_latam.sum()} | "
                f"keywords={cond_treinamento_keywords_latam.sum()} | terra_hhmm={cond_terra_hhmm.sum()} | "
                f"nao_voo_id_leg={cond_nao_voo_id_leg.sum()} | regra_final={cond_regra_treinamento_latam.sum()}"
            )

            cond_treinamento = cond_treinamento | cond_regra_treinamento_latam

    df['Tempo Treinamento'] = np.where(cond_treinamento, df['Tempo Operacao'], pd.NaT)

    print("Cálculos concluídos.")

    # Remove as colunas normalizadas temporárias
    df.drop(columns=['Id_Leg_Norm', 'Activity_Norm'], inplace=True)

    # --- IMPRIMIR AS PRIMEIRAS 5 LINHAS DO DATAFRAME FINAL ---
    print("\n--- Primeiras 5 linhas do DataFrame FINAL com colunas calculadas ---")
    display_cols = [col for col in required_cols if col not in existing_cols_to_remove] + [
        'Tempo Operacao', 'Tempo Apresentacao', 'Tempo Corte', 'Tempo Solo',
        'Tempo Jornada', 'Tempo Repouso', 'Tempo Repouso Extra Simples',
        'Tempo Repouso Extra Composta', 'Tempo Repouso Extra Revezamento',
        'Tempo Reserva', 'Tempo Plantao', 'Tempo Treinamento'
    ]
    existing_display_cols = [col for col in display_cols if col in df.columns]
    print(df[existing_display_cols].head(5).to_string())
    print("---------------------------------------------------------------")


    # --- 6. Formatação e Salvamento do Arquivo CSV de Saída ---
    linhas_final = len(df)
    print(f"\n{'='*80}")
    print(f"RASTREAMENTO: Antes de salvar arquivo final: {linhas_final} linhas")
    print(f"TOTAL DE LINHAS PERDIDAS NO PROCESSAMENTO: {linhas_inicial - linhas_final}")
    print(f"{'='*80}\n")
    
    # CHAVE: Gerar o nome do arquivo de saída baseado no arquivo de entrada
    output_filename = gerar_nome_csv_saida(input_csv_path)
    output_file_path = os.path.join(output_dir, output_filename)

    # 🔧 CORREÇÃO DEFINITIVA: Converter timedelta para string legível antes de salvar
    timedelta_cols = [
        'Tempo Operacao', 'Tempo Apresentacao', 'Tempo Corte', 'Tempo Solo',
        'Tempo Jornada', 'Tempo Repouso', 'Tempo Repouso Extra Simples',
        'Tempo Repouso Extra Composta', 'Tempo Repouso Extra Revezamento',
        'Tempo Reserva', 'Tempo Plantao', 'Tempo Treinamento'
    ]
    for col in timedelta_cols:
        if col in df.columns:
            def format_timedelta(x):
                if pd.isna(x):
                    return ""
                # Se veio como inteiro (nanosegundos), converte para timedelta e string
                if isinstance(x, (int, float, np.integer, np.floating)):
                    try:
                        return str(pd.to_timedelta(x))
                    except Exception:
                        return str(x)
                if isinstance(x, (pd.Timedelta, np.timedelta64)):
                    return str(x)
                return str(x)
            df[col] = df[col].apply(format_timedelta)

    try:
        df.to_csv(output_file_path, index=False, encoding='utf-8-sig')
        print(f"\nArquivo '{output_filename}' salvo com sucesso em: {output_file_path}")
        messagebox.showinfo("Sucesso", f"Processamento concluído! Arquivo salvo em:\n{output_file_path}")
    except Exception as e:
        messagebox.showerror("Erro ao Salvar", f"Erro ao salvar o arquivo CSV de saída: {e}\n"
                                               "Verifique se você tem permissão de escrita no diretório selecionado e se o arquivo não está aberto.")
        print(f"ERRO: Erro ao salvar o arquivo CSV de saída: {e}")

# --- Execução do Script ---
if __name__ == "__main__":
    try:
        processar_dados_aeronautica()
    except Exception as e:
        messagebox.showerror("Erro Inesperado", f"Ocorreu um erro inesperado: {e}\n"
                                                 "Verifique a saída do console para mais detalhes.")
        print(f"ERRO INESPERADO NA EXECUÇÃO PRINCIPAL: {e}")
