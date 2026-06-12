import pandas as pd
import numpy as np
import os
import json
import re
import unicodedata
from datetime import datetime, timedelta, date
import tkinter as tk
from tkinter import filedialog, messagebox

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass

# --- Configurações Globais ---
# ATENÇÃO: Este caminho deve ser o diretório base onde os arquivos auxiliares (JSON, XLSX) estão.
# Substitua pelo caminho correto no seu sistema.
BASE_COMMON_FILES_PATH = r"R:\SPECTRUM_SYSTEM\Aeronautas\Documentos_Comuns\Arquivos_Diversos"
ATIVIDADES_ESCALA_LATAM_FILE = "AtividadesEscalaLATAM.json"

def _arquivo_entrada_eh_latam() -> bool:
    candidatos = [
        os.environ.get("AERO_ESCALA_CSV", ""),
        globals().get("INPUT_FILE", ""),
        globals().get("arquivo_entrada", ""),
    ]
    for candidato in candidatos:
        candidato = str(candidato).strip().strip('"')
        if candidato and "LATAM" in os.path.basename(candidato).upper():
            return True
    return False


def _resolver_json_apoio(file_name: str) -> str:
    base_dir = BASE_COMMON_FILES_PATH
    candidatos = []
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


def _carregar_regras_plantao_latam() -> set:
    """
    A partir do AtividadesEscalaLATAM:
    - PLANTÃO quando codigo_ams contém 'SOBRE AVISO'/'SOBREAVISO'
      OU descricao_resumida contém 'HSB'.
    """
    file_path = _resolver_json_apoio(ATIVIDADES_ESCALA_LATAM_FILE)
    if not os.path.exists(file_path):
        print(f"AVISO: Catálogo LATAM não encontrado: {file_path}")
        return set()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"AVISO: Falha ao carregar catálogo LATAM '{file_path}': {e}")
        return set()

    atividades = data.get('atividades', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    tokens_plantao = set()

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

        if ('SOBRE AVISO' in codigo_ams) or ('SOBREAVISO' in codigo_ams) or ('HSB' in descricao_resumida):
            tokens_plantao.update(tokens_entry)

    print(f"INFO: Regras LATAM carregadas do catálogo de plantão: {len(tokens_plantao)} tokens")
    return tokens_plantao


def _activity_casa_tokens(activity_val: str, tokens: set) -> bool:
    if not activity_val or activity_val == 'NAN' or not tokens:
        return False
    if activity_val in tokens:
        return True
    return any(activity_val.startswith(tk) for tk in tokens if tk and len(tk) >= 2)


def _tem_tempo_plantao_fonte(valor) -> bool:
    if pd.isna(valor):
        return False
    txt = str(valor).strip().upper()
    if txt in {'', '0', '0:00', '00:00', '00:00:00', '0 DAYS 00:00:00', 'NAT'}:
        return False
    return True

# --- Funções de Utilitário (UI e Nome de Arquivo) ---
def determinar_diretorio_e_arquivo():
    entrada_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    saida_env = os.environ.get("AERO_OUTPUT_DIR", "").strip().strip('"')
    if entrada_env and os.path.isfile(entrada_env):
        output_dir = saida_env if saida_env else os.path.dirname(entrada_env)
        if output_dir and os.path.isdir(output_dir):
            print(f"📄 Arquivo de entrada (ENV): {entrada_env}")
            print(f"📂 Diretório de saída (ENV): {output_dir}")
            return entrada_env, output_dir

    root = tk.Tk()
    root.withdraw() # Esconde a janela principal do Tkinter

    input_file_path = filedialog.askopenfilename(
        title="Selecione o arquivo CSV principal",
        filetypes=[("Arquivos CSV", "*.csv")]
    )
    if not input_file_path:
        messagebox.showwarning("Seleção Cancelada", "Nenhum arquivo CSV selecionado. O script será encerrado.")
        return None, None

    output_dir = filedialog.askdirectory(
        title="Selecione o diretório para salvar o arquivo CSV de saída"
    )
    if not output_dir:
        messagebox.showwarning("Seleção Cancelada", "Nenhum diretório de saída selecionado. O script será encerrado.")
        return None, None

    return input_file_path, output_dir

def gerar_nome_csv_saida_base(original_filename):
    """Gera um nome de arquivo de saída baseado no nome do arquivo original,
    substituindo 'RESERVA' ou 'QUARTA_VERSAO' por 'PLANTAO' e removendo '_Processado'."""
    base_name = os.path.basename(original_filename)
    name_without_ext = os.path.splitext(base_name)[0]

    # Substitui "RESERVA" ou "QUARTA_VERSAO" por "PLANTAO" no nome do arquivo
    processed_name = name_without_ext.replace("RESERVA", "PLANTAO")
    processed_name = processed_name.replace("QUARTA_VERSAO", "PLANTAO")
    
    # Adicionalmente, remove "_Processado" se por acaso estiver no nome base (erro anterior)
    processed_name = processed_name.replace("_Processado", "")
    processed_name = re.sub(r'_\d{8}_\d{6}$', '', processed_name)

    return f"{processed_name}.csv" 

# --- Funções de Parsing e Formatação ---

def parse_date_from_excel_serial(serial_value):
    """Converte um número de série do Excel para datetime.datetime."""
    if pd.isna(serial_value):
        return pd.NaT
    try:
        num_val = float(serial_value)
        # 1899-12-30 é a data de origem para números de série do Excel (Windows)
        return pd.to_datetime(num_val, unit='D', origin='1899-12-30')
    except (ValueError, TypeError):
        return pd.NaT

def parse_timedelta_from_excel_float_or_string(value):
    """
    Converte um valor (string ou float) para um Timedelta.
    Assume floats grandes como microssegundos.
    """
    if pd.isna(value) or value == '':
        return pd.NaT
    # 1. Tentar como Timedelta string (ex: '0 days HH:MM:SS' ou 'HH:MM:SS')
    try:
        # Tenta interpretar como string de tempo se não contiver 'days'
        if isinstance(value, str) and 'days' not in value:
            # Pelo menos 5 caracteres para 'HH:MM'
            if len(value) >= 5 and value[2] == ':' and (len(value) < 8 or value[5] == ':'): # Assume HH:MM ou HH:MM:SS
                parts = value.split(':')
                if len(parts) == 3:
                    h, m, s = map(int, parts)
                    td = timedelta(hours=h, minutes=m, seconds=s)
                elif len(parts) == 2:
                    h, m = map(int, parts)
                    td = timedelta(hours=h, minutes=m)
                else:
                    raise ValueError("Formato de tempo inesperado")
                return td
        td = pd.to_timedelta(value)
        if pd.notna(td):
            return td
    except:
        pass # Segue para a próxima tentativa
    # 2. Tentar como float, assumindo microssegundos (comum em CSVs exportados de sistemas)
    try:
        num_val = float(value)
        # Heurística: números muito grandes que não seriam dias ou horas inteiras, mas sim unidades menores.
        # Se for um valor muito grande (ex: > 1000000 para segundos), pode ser microssegundos ou nanosegundos
        if abs(num_val) > 1_000_000: # Se for maior que 1 segundo em microssegundos
            return pd.to_timedelta(num_val, unit='us') # Tenta microssegundos
        else: # Se for um float menor, tentar como dias (número de dias fracionário)
             return pd.to_timedelta(num_val, unit='D')
    except (ValueError, TypeError):
        pass
    return pd.NaT # Se todas as tentativas falharem

def load_json_to_set(file_name: str, type_expected: str = 'string') -> set:
    """
    Carrega um arquivo JSON e tenta extrair um conjunto de valores.
    'type_expected' pode ser 'string' (para tipos_voo/folgas/tipos_reserva/tipos_plantao) ou 'date' (para feriados).
    """
    file_path = _resolver_json_apoio(file_name)
    print(f"Tentando carregar arquivo de configuração: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        extracted_values = set()
        def process_item(item):
            if type_expected == 'string':
                if isinstance(item, str):
                    extracted_values.add(item.strip().upper()) # Normalização forte para strings
                elif isinstance(item, dict):
                    # Tenta encontrar chaves comuns como 'atividade', 'Activity', 'name', 'valor'
                    for key in ['atividade', 'Activity', 'name', 'valor']:
                        if key in item and isinstance(item[key], str):
                            extracted_values.add(item[key].strip().upper())
                            return
            elif type_expected == 'date':
                parsed_date = pd.NaT
                # Primeiro, tenta parsear como string de data
                if isinstance(item, str):
                    dt_parsed_str = pd.to_datetime(item, errors='coerce') 
                    if pd.notna(dt_parsed_str):
                        parsed_date = dt_parsed_str.date()
                # Se não conseguiu como string ou é um número, tenta como número de série do Excel
                if pd.isna(parsed_date) and isinstance(item, (int, float)):
                    try:
                        parsed_date = parse_date_from_excel_serial(item).date()
                    except:
                        pass
                elif pd.isna(parsed_date) and isinstance(item, str) and item.replace('.', '', 1).replace(',', '', 1).isdigit(): # Tentar se parece número
                     try:
                         parsed_date = parse_date_from_excel_serial(float(item)).date()
                     except:
                         pass
                elif pd.isna(parsed_date) and isinstance(item, dict):
                    # Tenta encontrar chaves como 'date', 'data'
                    for key in ['date', 'data']:
                        if key in item:
                            dt_parsed_dict = pd.to_datetime(item[key], errors='coerce') 
                            if pd.notna(dt_parsed_dict):
                                parsed_date = dt_parsed_dict.date()
                                break
                            elif isinstance(item[key], (int, float)): # Tentar se o valor dentro do dict é número
                                try:
                                    parsed_date = parse_date_from_excel_serial(item[key]).date()
                                    break
                                except:
                                    pass
                if not pd.isna(parsed_date):
                    extracted_values.add(parsed_date)
                else:
                    print(f"Aviso: Não foi possível parsear a data '{item}' de {file_name}. Ignorando este item.")
        if isinstance(data, list):
            for item in data:
                process_item(item)
        elif isinstance(data, dict):
            # Procura por listas aninhadas, ou processa valores do dict
            # Suporta dicionários como {"exclude_activities": ["Manutenção", "Limpeza"]}
            if 'exclude_activities' in data and isinstance(data['exclude_activities'], list):
                for item in data['exclude_activities']:
                    process_item(item)
            else: # Tenta processar os valores diretamente se não houver 'exclude_activities'
                for key, value in data.items():
                    if isinstance(value, list):
                        for item in value:
                            process_item(item)
                    else: # Processa o valor se for um item simples
                        process_item(value)
        else:
            print(f"Aviso: Formato de JSON inesperado para {file_name}. Esperava lista ou dicionário. Tentando extrair valores diretamente.")
            process_item(data) # Tenta processar o objeto JSON inteiro como um item
        if not extracted_values:
            print(f"Aviso: Nenhum valor válido extraído de {file_name}. Verifique a estrutura do arquivo JSON.")
        return extracted_values
    except FileNotFoundError:
        messagebox.showerror("Erro de Arquivo", f"Arquivo de configuração não encontrado: {file_name}. Por favor, verifique o caminho '{BASE_COMMON_FILES_PATH}'.")
        raise
    except json.JSONDecodeError:
        messagebox.showerror("Erro de JSON", f"Erro ao decodificar JSON em {file_name}. Verifique a sintaxe do arquivo.")
        raise
    except Exception as e:
        messagebox.showerror("Erro Geral", f"Ocorreu um erro ao carregar {file_name}: {e}")
        raise

def format_timedelta_to_hms(td):
    """Formata um Timedelta para 'HH:MM:SS' ou 'D days HH:MM:SS'."""
    if pd.isna(td) or td is None:
        return "00:00:00"
    total_seconds = int(td.total_seconds())
    if total_seconds == 0:
        return "00:00:00"
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    days = hours // 24
    hours = hours % 24
    if days > 0:
        return f"{sign}{days} days {hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"

# --- Funções de Cálculo Detalhado para Tempo e Pagamento ---

def is_special_time(dt_obj, holidays_set):
    """
    Determina se um datetime.datetime é considerado 'especial'
    com base em feriados, sábados, domingos e vésperas de feriado (18h-06h).
    """
    current_date = dt_obj.date()
    current_hour = dt_obj.hour
    # 1. É feriado?
    if current_date in holidays_set:
        return True
    # 2. É Sábado ou Domingo?
    if current_date.weekday() == 5 or current_date.weekday() == 6: # 5 para Sábado, 6 para Domingo
        return True
    # 3. É véspera de feriado a partir das 18:00h?
    # Véspera de feriado significa que o dia seguinte é feriado.
    next_day_is_holiday = (current_date + timedelta(days=1)) in holidays_set
    if next_day_is_holiday and current_hour >= 18:
        return True
        # A parte "até as 06h" do dia seguinte (o feriado) já é coberta pela regra "É feriado?".
    return False

def is_holiday(date_obj: date, holidays_set: set) -> bool:
    """Verifica se uma data (datetime.date) é um feriado."""
    return date_obj in holidays_set

def is_eve_of_holiday(date_obj: date, holidays_set: set) -> bool:
    """Verifica se uma data (datetime.date) é véspera de feriado."""
    tomorrow = date_obj + timedelta(days=1)
    return is_holiday(tomorrow, holidays_set)

def calculate_time_and_payment_splits(start_dt, end_dt, activity_type_normalized, holidays_set):
    """
    Calcula as divisões de tempo e pagamento (Diurno/Noturno, Normal/Especial)
    para um dado intervalo [start_dt, end_dt).
    """
    # Nomes das colunas de saída, para PLANTÃO
    res = {
        'Tempo Plantao Diurno': timedelta(0),
        'Tempo Plantao Noturno': timedelta(0),
        'Tempo Plantao Especial Diurno': timedelta(0),
        'Tempo Plantao Especial Noturno': timedelta(0),
        'Pagamento Plantao Diurno': timedelta(0),
        'Pagamento Plantao Noturno': timedelta(0),
        'Pagamento Plantao Especial Diurno': timedelta(0),
        'Pagamento Plantao Especial Noturno': timedelta(0),
    }
    if pd.isna(start_dt) or pd.isna(end_dt) or start_dt >= end_dt:
        return res

    current_dt = start_dt

    # Itera minuto a minuto para precisão absoluta (necessário para cálculos trabalhistas)
    while current_dt < end_dt:
        next_dt = current_dt + timedelta(minutes=1)
        if next_dt > end_dt:
            delta = end_dt - current_dt
            next_dt = end_dt
        else:
            delta = timedelta(minutes=1)
        
        # Verificar se o momento atual é especial (seguindo lógica do REPOUSO)
        eh_especial = False
        current_date = current_dt.date()
        current_hour = current_dt.hour
        weekday = current_date.weekday()
        
        # Sábado a partir das 21:00
        if weekday == 5 and current_hour >= 21:
            eh_especial = True
        
        # Domingo até 18:00 (continuação do sábado especial)
        elif weekday == 6 and current_hour < 18:
            eh_especial = True
        
        # Domingo de 18:00 até 21:00 (especial de domingo)
        elif weekday == 6 and 18 <= current_hour < 21:
            eh_especial = True
        
        # Véspera de feriado a partir das 21:00
        elif is_eve_of_holiday(current_date, holidays_set) and current_hour >= 21:
            eh_especial = True
        
        # Feriado até 18:00 (continuação do especial de véspera)
        elif is_holiday(current_date, holidays_set) and current_hour < 18:
            eh_especial = True
        
        # Feriado de 18:00 até 21:00 (especial de feriado)
        elif is_holiday(current_date, holidays_set) and 18 <= current_hour < 21:
            eh_especial = True
        
        # Acumula tempo normal sempre
        # TEMPO PLANTÃO: Noturno 18:00-06:00, Diurno 06:00-18:00
        if current_hour >= 18 or current_hour < 6:
            res['Tempo Plantao Noturno'] += delta
        else:
            res['Tempo Plantao Diurno'] += delta
        
        # PAGAMENTO: Noturno 21:00-09:00, Diurno 09:00-21:00
        if current_hour >= 21 or current_hour < 9:
            res['Pagamento Plantao Noturno'] += delta
        else:
            res['Pagamento Plantao Diurno'] += delta
        
        # Se for especial, acumula também nos contadores especiais
        if eh_especial:
            # TEMPO PLANTÃO: verificar se é noturno (18:00-06:00)
            if current_hour >= 18 or current_hour < 6:
                res['Tempo Plantao Especial Noturno'] += delta
            else:
                res['Tempo Plantao Especial Diurno'] += delta
            
            # PAGAMENTO: verificar se é noturno (21:00-09:00)
            if current_hour >= 21 or current_hour < 9:
                res['Pagamento Plantao Especial Noturno'] += delta
            else:
                res['Pagamento Plantao Especial Diurno'] += delta
        
        current_dt = next_dt
    return res

# --- Lógica Principal do Script ---

def processar_dados_aeronautica():
    input_csv_path, output_dir = determinar_diretorio_e_arquivo()
    if not input_csv_path or not output_dir:
        return

    arquivo_eh_latam = 'LATAM' in os.path.basename(input_csv_path).upper()
    print(f"Arquivo LATAM detectado: {'SIM' if arquivo_eh_latam else 'NÃO'}")

    # --- 2. Carregar e Preparar Dados de Apoio ---
    print("Carregando arquivos de apoio (tipos_plantao.json, feriados.json)...\n")
    try:
        # Carrega tipos_plantao.json para filtragem INCLUSIVA
        tipos_plantao_inclusion_data = load_json_to_set('tipos_plantao.json', type_expected='string')
        if not tipos_plantao_inclusion_data:
            messagebox.showwarning("Aviso de Configuração", "O arquivo 'tipos_plantao.json' está vazio ou não contém dados válidos. Nenhuma linha será incluída no processamento.")
            print("Aviso: 'tipos_plantao.json' carregado mas está vazio ou não contém dados válidos. Nenhuma linha será incluída no processamento.\n")
            # df_processed será vazio se não houver dados para inclusão
            # Avança para o final do script para gerar um CSV vazio ou avisar
            # Mas para não travar, precisamos retornar ou ter um df_processed vazio
            # Neste caso, é melhor continuar e df_processed ficará vazio
            # return # Melhor não retornar aqui, para o fluxo continuar e gerar um CSV vazio se necessário

        # Carrega feriados.json para determinar dias especiais
        feriados_data = load_json_to_set('feriados.json', type_expected='date')
        if not feriados_data:
            print("Aviso: 'feriados.json' carregado mas está vazio ou não contém datas válidas. Cálculos de Tempo Especial (feriados) podem ser imprecisos.\n")

        tokens_plantao_latam = set()
        if arquivo_eh_latam:
            tokens_plantao_latam = _carregar_regras_plantao_latam()
            tipos_plantao_inclusion_data = set(tipos_plantao_inclusion_data) | set(tokens_plantao_latam) | {'HSB'}
            print(f"INFO LATAM: tipos_plantao total={len(tipos_plantao_inclusion_data)}")

    except Exception as e:
        print(f"Erro ao carregar arquivos de apoio: {e}")
        return

    # --- 3. Leitura do CSV e Pré-processamento ---
    print(f"Lendo o arquivo CSV: {input_csv_path}")
    try:
        # Tenta ler com encoding padrão e, se falhar, tenta 'latin1'
        try:
            df = pd.read_csv(input_csv_path)
        except UnicodeDecodeError:
            df = pd.read_csv(input_csv_path, encoding='latin1')

        # Mapeamento para nomes de colunas esperados no output para nomes internos snake_case
        column_map_input_to_internal = {
            'Activity': 'activity', 'Id_Leg': 'id_leg', 'Checkin': 'checkin',
            'Start': 'start', 'Dep': 'dep', 'Arr': 'arr', 'End': 'end',
            'Checkout': 'checkout',
            'Tempo Plantao': 'tempo_plantao_fonte',
            'ACVer': 'acver', 'DD': 'dd', 'CAT': 'cat', 'Crew': 'crew'
        }

        # Renomeia as colunas do DataFrame para os nomes internos em snake_case
        # Cria um mapeamento de colunas existentes (case-insensitive) para snake_case
        existing_cols_lower_to_original = {col.lower(): col for col in df.columns}
        rename_dict = {}
        for input_col_expected, internal_col_name in column_map_input_to_internal.items():
            if input_col_expected.lower() in existing_cols_lower_to_original:
                original_col_name = existing_cols_lower_to_original[input_col_expected.lower()]
                rename_dict[original_col_name] = internal_col_name
            else:
                print(f"Aviso: Coluna '{input_col_expected}' ou sua variação (ex: '{input_col_expected.lower()}') não encontrada no arquivo CSV. Será criada como vazia.")
        df.rename(columns=rename_dict, inplace=True)

        # Garante que as colunas essenciais para o processamento existam com os nomes internos
        # Para PLANTÃO, o período é entre Checkout e Checkin
        required_internal_cols = ['activity', 'checkin', 'checkout'] 
        for col in required_internal_cols:
            if col not in df.columns:
                df[col] = np.nan # Cria a coluna com NaN se não existir

    except Exception as e:
        messagebox.showerror("Erro de Leitura", f"Erro ao ler o arquivo CSV ou processar colunas: {e}")
        print(f"ERRO: Erro ao ler o arquivo CSV ou processar colunas: {e}")
        return

    print("CSV lido com sucesso e colunas normalizadas para processamento.\n")

    # --- 4. Otimização de Tipos de Dados e Conversão de Data/Hora ---
    print("Otimizando tipos de dados e convertendo colunas de data/hora...\n")

    # Otimizar tipos de colunas para reduzir tamanho em memória
    for col in ['activity', 'dep', 'arr', 'acver', 'dd', 'cat']:
        if col in df.columns and df[col].dtype == 'object':
            df[col] = df[col].astype('category')

    # Converter colunas de data/hora para o formato datetime
    # Para PLANTÃO, as colunas de interesse são Checkin e Checkout para o período
    datetime_internal_cols = ['checkin', 'checkout'] 
    # Outras colunas datetime que podem estar presentes para formatação final
    other_datetime_cols = ['start', 'end'] 
    all_cols_to_convert = list(set(datetime_internal_cols + other_datetime_cols))

    for col in all_cols_to_convert:
        if col in df.columns:
            def parse_dt_value(val):
                if pd.isna(val) or val == '':
                    return pd.NaT
                # 1. Tentar parsear como string usando inferência (mais robusto para formatos variados)
                try:
                    dt_parsed = pd.to_datetime(str(val), errors='coerce') 
                    if pd.notna(dt_parsed):
                        return dt_parsed
                except:
                    pass # Segue para a próxima tentativa
                # 2. Se a string falhou, tentar como número de série do Excel
                try:
                    num_val = float(val)
                    if num_val > 0 and num_val < 75000: # Heurística para números de série de data
                        dt_parsed = parse_date_from_excel_serial(num_val)
                        if pd.notna(dt_parsed) and dt_parsed.year > 1900: 
                            return dt_parsed
                except (ValueError, TypeError):
                    pass
                return pd.NaT # Se todas as tentativas falharem
            df[col] = df[col].apply(parse_dt_value)
        else:
            df[col] = pd.NaT # Se a coluna não existe, preenche com Not a Time

    print("Colunas de data/hora convertidas.\n")
    print("Amostra de colunas de tempo após conversão (first 5 rows):\n")
    print(df[['checkin', 'checkout', 'start', 'end']].head().to_string())
    print("\n")

    # --- 5. Filtragem por Inclusão (tipos_plantao.json) ---
    initial_row_count = len(df)
    # Prepara a coluna 'activity_for_filter' normalizada (string completa) ANTES DO FILTRO
    df['activity_for_filter'] = df['activity'].apply(lambda x: str(x).strip().upper() if pd.notna(x) else None)

    # Condição de Inclusão (Activity): Manter 'activity_for_filter' que estão em 'tipos_plantao_inclusion_data'
    # Esta é a lógica de filtro de INCLUSÃO.
    if tipos_plantao_inclusion_data: # Se o JSON de plantão tiver dados
        activity_include_condition = df['activity_for_filter'].isin(tipos_plantao_inclusion_data)
        if arquivo_eh_latam and tokens_plantao_latam:
            activity_include_condition_latam = df['activity_for_filter'].apply(
                lambda a: _activity_casa_tokens(a, tokens_plantao_latam)
            )
            activity_include_condition = activity_include_condition | activity_include_condition_latam
            print(f"DEBUG LATAM: condição plantão catálogo={activity_include_condition_latam.sum()} linhas True.")

        # Fallback LATAM: considera linhas onde o CSV fonte já traz Tempo Plantao preenchido
        if arquivo_eh_latam and 'tempo_plantao_fonte' in df.columns:
            cond_tempo_plantao_fonte = df['tempo_plantao_fonte'].apply(_tem_tempo_plantao_fonte)
            activity_include_condition = activity_include_condition | cond_tempo_plantao_fonte
            print(f"DEBUG LATAM: condição Tempo Plantao fonte={cond_tempo_plantao_fonte.sum()} linhas True.")

        df_processed = df[activity_include_condition].copy() # Filtra para incluir apenas
        print(f"DEBUG: Condição de 'Activity' (em tipos_plantao.json) resultou em {activity_include_condition.sum()} linhas incluídas.")
    else: # Se o JSON de plantão estiver vazio, não há atividades para incluir
        df_processed = pd.DataFrame(columns=df.columns) # Cria um DataFrame vazio
        print("Nenhum dado em 'tipos_plantao.json' para aplicar o filtro por 'Activity'. O DataFrame de saída estará vazio.\n")

    print(f"Total de linhas lidas: {initial_row_count}. Linhas após filtro inclusivo de Activity: {len(df_processed)}\n")
    if len(df_processed) < initial_row_count:
        print(f"{initial_row_count - len(df_processed)} linhas foram removidas pelo filtro de Activity.\n")
    else:
        print("Todas as linhas (ou nenhuma) atendem aos critérios de filtro (nenhuma remoção adicional por filtro).\n")


    # --- DIAGNÓSTICO CRÍTICO: Relação Checkout e Checkin para Plantão ---
    print("--- DIAGNÓSTICO DE DURAÇÃO PARA CÁLCULO DETALHADO (PLANTÃO) ---\n")
    if 'checkin' in df_processed.columns and 'checkout' in df_processed.columns:
        print(f"Shape de df_processed antes do cálculo de plantão detalhado: {df_processed.shape}")
        # Contagem de NaT em Checkin e Checkout
        nan_checkin = df_processed['checkin'].isna().sum()
        nan_checkout = df_processed['checkout'].isna().sum()
        print(f"Linhas com 'checkin' como NaT: {nan_checkin}")
        print(f"Linhas com 'checkout' como NaT: {nan_checkout}")

        # Relação de durações válidas para cálculo detalhado (Checkin e Checkout não nulos, e Checkout deve ser posterior a Checkin)
        valid_time_range_mask = (df_processed['checkin'].notna()) & \
                                (df_processed['checkout'].notna()) & \
                                (df_processed['checkout'] > df_processed['checkin'])

        valid_time_range_df = df_processed[valid_time_range_mask]
        print(f"Linhas VÁLIDAS (checkin e checkout não NaT e checkout > checkin) para cálculo detalhado: {valid_time_range_df.shape[0]}")
        if not valid_time_range_df.empty:
            print("Amostra de Checkin e Checkout para as primeiras 5 linhas VÁLIDAS:\n")
            print(valid_time_range_df[['checkin', 'checkout']].head().to_string())
        else:
            print("Nenhuma linha com valores válidos para 'checkin' e 'checkout' após filtragem para cálculo detalhado.")
    else:
        print("Colunas 'checkin' ou 'checkout' não encontradas em df_processed para diagnóstico.\n")
    print("------------------------------------------------------------------\n")

    # --- 6. Calcular as 8 colunas de detalhamento do Tempo Plantão ---
    print("Calculando Tempo Plantão e Pagamento Plantão e suas subdivisões...\n")

    # Define as novas colunas de detalhamento com os nomes e ordem CORRETOS (Com "Plantao")
    detailed_plantao_columns = [
        'Tempo Plantao Diurno',
        'Tempo Plantao Noturno', 
        'Tempo Plantao Especial Diurno', 
        'Tempo Plantao Especial Noturno',
        'Pagamento Plantao Diurno',
        'Pagamento Plantao Noturno', 
        'Pagamento Plantao Especial Diurno', 
        'Pagamento Plantao Especial Noturno'
    ]

    # Inicializa as novas colunas com Timedelta(0) para tempo e pagamento
    for col in detailed_plantao_columns:
        df_processed[col] = pd.Timedelta(0)

    # Máscara de validação para aplicar o cálculo detalhado:
    # 1. 'checkin' não pode ser NaT
    # 2. 'checkout' não pode ser NaT
    # 3. 'checkout' deve ser maior que 'checkin'
    valid_calculation_mask = (df_processed['checkin'].notna()) & \
                             (df_processed['checkout'].notna()) & \
                             (df_processed['checkout'] > df_processed['checkin'])

    print(f"DEBUG: Número de linhas com período válido para cálculo detalhado: {valid_calculation_mask.sum()}")

    # Aplica a função de cálculo detalhado apenas nas linhas com períodos válidos
    if valid_calculation_mask.any(): # Verifica se há pelo menos uma linha válida para processamento
        calculated_results = df_processed.loc[valid_calculation_mask].apply(
            lambda row: calculate_time_and_payment_splits(
                row['checkin'],   # Início do período a ser detalhado (Checkin para Plantão)
                row['checkout'],  # Fim do período a ser detalhado (Checkout para Plantão)
                row['activity_for_filter'], # Tipo de atividade (já filtrado)
                feriados_data
            ),
            axis=1
        )
        # Expande o dicionário de resultados em novas colunas
        for col_name in detailed_plantao_columns:
            df_processed.loc[valid_calculation_mask, col_name] = calculated_results.apply(lambda x: x[col_name])
    else:
        print("Não há linhas válidas para calcular o tempo de plantão detalhado (após todos os filtros e validações de dados).\n")

    print("Cálculos de Tempo Plantão e Pagamento Plantão detalhados (8 colunas) concluídos.\n")

    # --- 7. Preparar DataFrame para Saída (Ordem Corrigida e Novos Nomes) ---
    # Define as colunas desejadas no CSV de saída com seus nomes exatos e na ordem correta
    final_output_columns_pascal_case = [
        'Activity', 'Id_Leg', 'Checkin', 'Start', 'Dep', 'Arr', 'End', 'Checkout',
        'Tempo Plantao' # Esta será a duração calculada de Checkout - Checkin
    ] + detailed_plantao_columns # As 8 colunas de detalhamento na ordem corrigida

    # Criar um DataFrame de saída vazio com as colunas na ordem desejada
    df_output = pd.DataFrame(columns=final_output_columns_pascal_case)

    # Preencher o DataFrame de saída com os dados processados, mapeando nomes internos para nomes de saída
    for col_pascal in final_output_columns_pascal_case:
        # Tenta mapear o nome PascalCase de volta para o snake_case interno ou usa o nome PascalCase diretamente se for uma coluna nova
        internal_col_name = col_pascal.replace(' ', '_').lower() # Ex: 'Tempo Plantao' -> 'tempo_plantao'

        if col_pascal == 'Activity':
            df_output[col_pascal] = df_processed['activity'] if 'activity' in df_processed.columns else np.nan
        elif col_pascal == 'Id_Leg':
            df_output[col_pascal] = df_processed['id_leg'] if 'id_leg' in df_processed.columns else np.nan
        elif col_pascal == 'Checkin':
            df_output[col_pascal] = df_processed['checkin'] if 'checkin' in df_processed.columns else pd.NaT
        elif col_pascal == 'Start':
            df_output[col_pascal] = df_processed['start'] if 'start' in df_processed.columns else pd.NaT
        elif col_pascal == 'Dep':
            df_output[col_pascal] = df_processed['dep'] if 'dep' in df_processed.columns else np.nan
        elif col_pascal == 'Arr':
            df_output[col_pascal] = df_processed['arr'] if 'arr' in df_processed.columns else np.nan
        elif col_pascal == 'End':
            df_output[col_pascal] = df_processed['end'] if 'end' in df_processed.columns else pd.NaT
        elif col_pascal == 'Checkout':
            df_output[col_pascal] = df_processed['checkout'] if 'checkout' in df_processed.columns else pd.NaT
        elif col_pascal == 'Tempo Plantao': # AGORA CALCULADO: Checkout - Checkin
            df_output[col_pascal] = df_processed['checkout'] - df_processed['checkin'] if 'checkin' in df_processed.columns and 'checkout' in df_processed.columns else pd.NaT
        elif col_pascal in detailed_plantao_columns:
            df_output[col_pascal] = df_processed[col_pascal] if col_pascal in df_processed.columns else pd.NaT
        else:
            df_output[col_pascal] = np.nan # Caso alguma coluna não mapeada seja adicionada

    # Formatar TODAS as colunas Timedelta (Tempo Plantao principal e as 8 detalhadas) para string 'HH:MM:SS' ou 'D days HH:MM:SS'
    for col in ['Tempo Plantao'] + detailed_plantao_columns:
        if col in df_output.columns:
            df_output[col] = df_output[col].apply(format_timedelta_to_hms)

    # Formatar APENAS colunas datetime para string 'YYYY-MM-DD HH:MM:SS'
    datetime_cols_for_format = ['Checkin', 'Start', 'End', 'Checkout'] 
    for col in datetime_cols_for_format:
        if col in df_output.columns:
            df_output[col] = df_output[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    # --- VERIFICAÇÃO DE CONSISTÊNCIA DO TEMPO PLANTÃO ---
    print("--- VERIFICAÇÃO DE CONSISTÊNCIA DO TEMPO PLANTÃO ---\n")
    df_temp = df_processed.copy() # Usar df_processed para ter acesso aos timedeltas

    # Calcula a soma das 4 colunas de Tempo Plantão (Diurno/Noturno, Normal/Especial)
    df_temp['total_tempo_plantao_calculated'] = df_temp['Tempo Plantao Diurno'] + \
                                                 df_temp['Tempo Plantao Noturno'] + \
                                                 df_temp['Tempo Plantao Especial Diurno'] + \
                                                 df_temp['Tempo Plantao Especial Noturno']

    # Calcula a duração total do período de interesse (Checkout - Checkin)
    df_temp['total_plantao_checkout_checkin'] = df_temp['checkout'] - df_temp['checkin']

    # Verifica se a soma das 4 colunas Tempo Plantão é igual a Checkout - Checkin
    # A comparação deve levar em conta pequenas diferenças de ponto flutuante se houver,
    # mas com timedelta puro, deveriam ser exatas.
    # Usar .round() ou np.isclose() pode ser necessário para floats, mas para timedeltas puros é OK.
    consistency_check_all_four = (df_temp['total_tempo_plantao_calculated'] == df_temp['total_plantao_checkout_checkin']).all()
    print(f"DEBUG: Soma das 4 colunas 'Tempo Plantão' === (Checkout - Checkin): {consistency_check_all_four}\n")

    # Verifica a regra específica do usuário: Soma de Diurno + Noturno (NÃO-ESPECIAL) == Tempo Plantão Total
    # Esta é a checagem que pode falhar se houver tempo "Especial" na reserva
    df_temp['sum_normal_tempo_plantao'] = df_temp['Tempo Plantao Diurno'] + df_temp['Tempo Plantao Noturno']
    
    # Filtra as linhas onde há discrepância. A máscara deve ser para Timedelta, não string.
    # Converte para segundos para comparação numérica aproximada, se houver floats no original
    discrepancy_mask = ~df_temp['total_plantao_checkout_checkin'].isna() & \
                       ~df_temp['sum_normal_tempo_plantao'].isna() & \
                       (df_temp['sum_normal_tempo_plantao'] != df_temp['total_plantao_checkout_checkin']) # Comparação direta de Timedelta

    discrepancy_rows = df_temp[discrepancy_mask]

    if not discrepancy_rows.empty:
        print("AVISO IMPORTANTE: A regra 'Tempo Plantão == (Tempo Plantao Diurno + Tempo Plantao Noturno)' não se mantém para todas as linhas.\n")
        print("Isso ocorre porque o Tempo Plantão total (Checkout - Checkin) também inclui 'Tempo Plantao Especial Diurno' e 'Tempo Plantao Especial Noturno'.\n")
        print("Para a regra ser verdadeira, o Tempo Plantão deveria ser a soma de TODAS as 4 sub-colunas Tempo Plantão, ou as colunas Diurno/Noturno deveriam incluir o tempo Especial.\n")
        print(discrepancy_rows[['checkin', 'checkout', 'Tempo Plantao Diurno', 'Tempo Plantao Noturno',
                               'Tempo Plantao Especial Diurno', 'Tempo Plantao Especial Noturno',
                               'total_plantao_checkout_checkin', 'sum_normal_tempo_plantao']].head(1).to_string())
        print("\n")
    else:
        print("DEBUG: A regra 'Tempo Plantão == (Tempo Plantao Diurno + Tempo Plantao Noturno)' parece se manter (sem tempo especial ou tempo especial zerado para estas linhas).\n")
    print("--- FIM DA VERIFICAÇÃO DE CONSISTÊNCIA ---\n")


    # --- IMPRIMIR AS PRIMEIRAS 5 LINHAS DO DATAFRAME FINAL ---
    print("\n--- Primeiras 5 linhas do DataFrame FINAL com colunas calculadas e formatadas ---\n")
    display_cols_example = [col for col in final_output_columns_pascal_case if col in df_output.columns]
    print(df_output[display_cols_example].head(5).to_string())
    print("\n---------------------------------------------------------------\n")

    # --- 8. Salvamento do Arquivo CSV de Saída ---
    # Preparar nome do arquivo de saída
    base_output_filename = gerar_nome_csv_saida_base(input_csv_path) 
    timestamp = datetime.now().strftime("%d%m%Y_%H%M%S") 
    name_part, ext_part = os.path.splitext(base_output_filename)
    output_filename_with_timestamp = f"{name_part}_{timestamp}{ext_part}"
    output_file_path = os.path.join(output_dir, output_filename_with_timestamp)

    # Verificar se não há dados e exibir mensagem apropriada
    if df_processed.empty and not tipos_plantao_inclusion_data:
        messagebox.showinfo("Processamento Concluído", "NÃO HOUVERAM PLANTÕES NO PERÍODO\n\nNenhuma linha foi processada, pois 'tipos_plantao.json' está vazio ou não possui atividades para inclusão.\n\nO arquivo CSV será criado apenas com cabeçalhos.")
        print("\n" + "="*60)
        print("NÃO HOUVERAM PLANTÕES NO PERÍODO")
        print("="*60)
        print("Nenhuma linha foi processada, pois 'tipos_plantao.json' está vazio ou não possui atividades para inclusão.")
        print("O arquivo CSV será criado apenas com cabeçalhos.\n")
    elif df_processed.empty:
        messagebox.showinfo("Processamento Concluído", "NÃO HOUVERAM PLANTÕES NO PERÍODO\n\nNenhuma linha foi processada após a aplicação dos filtros.\n\nO arquivo CSV será criado apenas com cabeçalhos.")
        print("\n" + "="*60)
        print("NÃO HOUVERAM PLANTÕES NO PERÍODO")
        print("="*60)
        print("Nenhuma linha foi processada após a aplicação dos filtros.")
        print("O arquivo CSV será criado apenas com cabeçalhos.\n")

    # Salvar o arquivo CSV (mesmo que vazio, com apenas cabeçalhos)
    try:
        df_output.to_csv(output_file_path, index=False, encoding='utf-8-sig')
        print(f"Arquivo '{output_filename_with_timestamp}' salvo com sucesso em: {output_file_path}\n")
        messagebox.showinfo("Sucesso", f"Processamento concluído! Arquivo salvo em:\n{output_file_path}")
    except Exception as e:
        messagebox.showerror("Erro ao Salvar", f"Erro ao salvar o arquivo CSV de saída: {e}\n"
                                               "Verifique se você tem permissão de escrita no diretório selecionado e se o arquivo não está aberto.")
        print(f"ERRO: Erro ao salvar o arquivo CSV de saída: {e}\n")

# --- Execução do Script ---
if __name__ == "__main__":
    try:
        processar_dados_aeronautica()
    except Exception as e:
        messagebox.showerror("Erro Inesperado", f"Ocorreu um erro inesperado: {e}\n"
                                                 "Verifique a saída do console para mais detalhes.")
        print(f"ERRO INESPERADO NA EXECUÇÃO PRINCIPAL: {e}\n")