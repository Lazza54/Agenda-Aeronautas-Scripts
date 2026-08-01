import pandas as pd
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from datetime import datetime, timedelta, time, date
import re

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass

# --- 1. Configurações e Funções de Suporte Comuns ---

# ATENÇÃO: VERIFIQUE E AJUSTE ESTE CAMINHO CONFORME SEU AMBIENTE
# Este é o diretório onde os arquivos JSON e Excel de apoio devem estar localizados.
# Se este caminho estiver incorreto, o script não encontrará os arquivos de apoio.
BASE_COMMON_FILES_PATH = str(BASE_COMMON_FILES_PATH)

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

import unicodedata
from config_caminhos import BASE_COMMON_FILES_PATH
def _normalizar_texto(valor) -> str:
    if valor is None: return ''
    txt = str(valor).strip().upper()
    txt = unicodedata.normalize('NFKD', txt)
    return ''.join(ch for ch in txt if not unicodedata.combining(ch))

def _carregar_atividades_pagas_regras_voo_latam():
    file_path = os.path.join(BASE_COMMON_FILES_PATH, 'AtividadesEscalaLATAM.json')
    if not os.path.exists(file_path): return set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except: return set()

    atividades = data.get('atividades', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    tokens = set()
    for entry in atividades:
        if isinstance(entry, dict) and entry.get("atividade paga", "").strip().upper() == "S" and entry.get("segue regras do voo", "").strip().upper() == "S":
            c = _normalizar_texto(entry.get('codigo_iflight_neo', ''))
            if c: tokens.add(c)
    return tokens

def gerar_nome_csv_saida_base(nome_csv_entrada: str) -> str:
    """
    Gera o nome base do arquivo CSV de saída (sem timestamp), substituindo sufixos de etapas anteriores
    por '_REPOUSO_EXTRA'.
    """
    base_nome = os.path.basename(nome_csv_entrada)
    nome_sem_ext, _ = os.path.splitext(base_nome)

    # Lista de sufixos de etapas anteriores para remover
    previous_stage_suffixes = ['_APRESENTACAO', '_OPERACAO', '_TEMPO_CORTE', '_TEMPO_SOLO', '_REPOUSO', '_QUARTA_VERSAO']
    
    cleaned_name = nome_sem_ext
    for suffix in previous_stage_suffixes:
        if suffix in cleaned_name:
            cleaned_name = cleaned_name.replace(suffix, '')
    
    # Remove qualquer timestamp existente para garantir um nome base limpo
    timestamp_pattern = r'_\d{8}_\d{6}$' # Exemplo: _YYYYMMDD_HHMMSS
    cleaned_name = re.sub(timestamp_pattern, '', cleaned_name)

    # Garante que o nome termine com o sufixo correto para esta etapa
    if not cleaned_name.endswith('_REPOUSO_EXTRA'):
        return f"{cleaned_name}_REPOUSO_EXTRA.csv"
    
    return f"{cleaned_name}.csv" # Caso já termine com _REPOUSO_EXTRA

def determinar_diretorio_e_arquivo():
    """
    Função para permitir ao usuário selecionar o arquivo CSV de entrada
    e usar o mesmo diretório para salvar o arquivo de saída.
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
        title="Selecione o arquivo CSV de entrada para processar (Repouso Extra)",
        filetypes=[("Arquivos CSV", "*.csv")]
    )

    if not input_file_path:
        messagebox.showwarning("Seleção Cancelada", "Nenhum arquivo de entrada selecionado. O script será encerrado.")
        return None, None

    output_dir = os.path.dirname(input_file_path)

    return input_file_path, output_dir

def parse_date_from_excel_serial(serial_value):
    """Converte um número de série do Excel para datetime.datetime."""
    if pd.isna(serial_value):
        return pd.NaT
    try:
        num_val = float(serial_value)
        return pd.to_datetime(num_val, unit='D', origin='1899-12-30')
    except (ValueError, TypeError):
        return pd.NaT


def load_json_to_set(file_name: str, type_expected: str = 'string') -> set:
    """
    Carrega um arquivo JSON e tenta extrair um conjunto de valores.
    'type_expected' pode ser 'string' (para tipos_voo) ou 'date' (para feriados).
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
                    extracted_values.add(item.strip().upper())
                elif isinstance(item, dict):
                    for key in ['atividade', 'Activity', 'name']:
                        if key in item and isinstance(item[key], str):
                            extracted_values.add(item[key].strip().upper())
                            return
            elif type_expected == 'date':
                parsed_date = pd.NaT
                if isinstance(item, str):
                    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(item, fmt).date()
                            break
                        except ValueError:
                            continue
                    if pd.isna(parsed_date) and item.replace('.', '').isdigit():
                         try:
                             parsed_date = parse_date_from_excel_serial(float(item)).date()
                         except:
                             pass
                elif isinstance(item, (int, float)):
                    try:
                        parsed_date = parse_date_from_excel_serial(item).date()
                    except:
                        pass
                elif isinstance(item, dict):
                    for key in ['date', 'data']:
                        if key in item:
                            parsed_date_from_dict = pd.NaT
                            if isinstance(item[key], str):
                                formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']
                                for fmt in formats:
                                    try:
                                        parsed_date_from_dict = datetime.strptime(item[key], fmt).date()
                                        break
                                    except ValueError:
                                        continue
                            elif isinstance(item[key], (int, float)):
                                try:
                                    parsed_date_from_dict = parse_date_from_excel_serial(item[key]).date()
                                except:
                                    pass
                            
                            if not pd.isna(parsed_date_from_dict):
                                parsed_date = parsed_date_from_dict
                                break

                if not pd.isna(parsed_date):
                    extracted_values.add(parsed_date)
                else:
                    print(f"Aviso: Não foi possível parsear a data '{item}' de {file_name}.")

        if isinstance(data, list):
            for item in data:
                process_item(item)
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    for item in value:
                        process_item(item)
                else:
                    process_item(value)
        else:
            print(f"Aviso: Formato de JSON inesperado para {file_name}. Esperava lista ou dicionário.")

        if not extracted_values:
            print(f"Aviso: Nenhum valor extraído de {file_name}. Verifique a estrutura do arquivo JSON.")
            
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

def is_holiday(date_obj: date, holidays_set: set) -> bool:
    """Verifica se uma data (datetime.date) é um feriado."""
    return date_obj in holidays_set

def is_eve_of_holiday(date_obj: date, holidays_set: set) -> bool:
    """Verifica se uma data (datetime.date) é véspera de feriado."""
    tomorrow = date_obj + timedelta(days=1)
    return is_holiday(tomorrow, holidays_set)

def get_interval_overlap_with_repeating_period(event_start_dt: datetime, event_end_dt: datetime, 
                                                 period_start_hour: int, period_start_minute: int, 
                                                 period_end_hour: int, period_end_minute: int) -> timedelta:
    """
    Calcula a duração total da sobreposição entre um intervalo de evento [event_start_dt, event_end_dt)
    e um período diário repetitivo (definido por horas/minutos de início e fim, potencialmente cruzando a meia-noite).
    
    Para período noturno 18:00-06:00:
    - period_start_hour=18, period_start_minute=0
    - period_end_hour=6, period_end_minute=0
    """
    total_overlap = timedelta(0)
    
    if pd.isna(event_start_dt) or pd.isna(event_end_dt) or event_start_dt >= event_end_dt:
        return timedelta(0)

    period_start_hour %= 24
    period_end_hour %= 24
    period_start_minute %= 60
    period_end_minute %= 60

    period_start_time = time(period_start_hour, period_start_minute)
    period_end_time = time(period_end_hour, period_end_minute)
    
    # Determina se o período cruza meia-noite (ex: 18:00 - 06:00)
    crosses_midnight = period_end_time <= period_start_time

    # Itera dia a dia pelo intervalo do evento
    current_day = event_start_dt.date()
    end_day = event_end_dt.date()
    
    # Se cruza meia-noite, pode precisar começar do dia anterior
    if crosses_midnight and event_start_dt.time() < period_end_time:
        current_day -= timedelta(days=1)
    
    while current_day <= end_day + timedelta(days=1):
        if crosses_midnight:
            # Período noturno cruzando meia-noite (ex: 18:00 hoje até 06:00 amanhã)
            period_start_dt = datetime.combine(current_day, period_start_time)
            period_end_dt = datetime.combine(current_day + timedelta(days=1), period_end_time)
        else:
            # Período dentro do mesmo dia (ex: 06:00 até 18:00)
            period_start_dt = datetime.combine(current_day, period_start_time)
            period_end_dt = datetime.combine(current_day, period_end_time)
        
        # Calcula sobreposição
        overlap_start = max(event_start_dt, period_start_dt)
        overlap_end = min(event_end_dt, period_end_dt)
        
        if overlap_end > overlap_start:
            total_overlap += (overlap_end - overlap_start)
        
        current_day += timedelta(days=1)
    
    return total_overlap

# Função para calcular durações de Repouso Extra (apenas tempo além de 12 horas)
def calculate_repouso_extra_durations(checkout_dt: datetime, checkin_next_dt: datetime, holidays_set: set) -> tuple:
    """
    Calcula os tempos diurnos/noturnos (normais e especiais) para REPOUSO EXTRA.
    Repouso Extra = tempo de repouso que excede 12 horas.
    
    Períodos especiais (total 24h):
    - Sábado: 21:00 sáb → 18:00 dom (21h)
    - Domingo: 18:00 dom → 21:00 dom (3h)
    - Véspera feriado: 21:00 véspera → 18:00 feriado (21h)
    - Feriado: 18:00 feriado → 21:00 feriado (3h)
    """
    # Retorna zeros se as datas são inválidas ou o intervalo é zero/negativo
    if pd.isna(checkout_dt) or pd.isna(checkin_next_dt) or checkout_dt >= checkin_next_dt:
        return (timedelta(0),) * 4

    # Calcula o tempo total de repouso
    tempo_repouso_total = checkin_next_dt - checkout_dt
    
    # Se o repouso for menor ou igual a 12 horas, não há repouso extra
    if tempo_repouso_total <= timedelta(hours=12):
        return (timedelta(0),) * 4
    
    # Calcula o tempo extra (além de 12 horas)
    # O início do repouso extra é: checkout + 12 horas + 1 minuto
    repouso_extra_start = checkout_dt + timedelta(hours=12, minutes=1)
    repouso_extra_end = checkin_next_dt
    
    # Duração total do repouso extra
    total_repouso_extra_duration = repouso_extra_end - repouso_extra_start

    # --- Cálculo de Tempos Diurno/Noturno Padrão para Repouso Extra ---
    # Repouso Extra: Noturno 18:00 - 06:00
    repouso_extra_night_total = get_interval_overlap_with_repeating_period(repouso_extra_start, repouso_extra_end, 18, 0, 6, 0)
    repouso_extra_day_total = total_repouso_extra_duration - repouso_extra_night_total

    # --- Cálculo de Tempos Diurno/Noturno Especiais ---
    repouso_extra_special_day = timedelta(0)
    repouso_extra_special_night = timedelta(0)

    # Itera minuto a minuto para verificar se cada momento é especial
    current_dt = repouso_extra_start
    while current_dt < repouso_extra_end:
        next_dt = current_dt + timedelta(minutes=1)
        if next_dt > repouso_extra_end:
            delta = repouso_extra_end - current_dt
            next_dt = repouso_extra_end
        else:
            delta = timedelta(minutes=1)
        
        # Verificar se o momento atual é especial
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
        
        # Se for especial, acumula nos contadores especiais
        if eh_especial:
            # Verificar se é noturno (18:00-06:00)
            if current_hour >= 18 or current_hour < 6:
                repouso_extra_special_night += delta
            else:
                repouso_extra_special_day += delta
        
        current_dt = next_dt

    return (repouso_extra_day_total, repouso_extra_night_total, repouso_extra_special_day, repouso_extra_special_night)

# Funcao generica para calcular diurno/noturno/especial de qualquer periodo de repouso
def calculate_repouso_breakdown(checkout_dt: datetime, checkin_next_dt: datetime, tempo_repouso: timedelta, holidays_set: set, offset_hours: int = 0) -> tuple:
    """
    Calcula os tempos diurnos/noturnos (normais e especiais) para qualquer periodo de repouso.
    Retorna (diurno, noturno, especial_diurno, especial_noturno)
    Se tempo_repouso for negativo ou zero, retorna zeros.
    
    IMPORTANTE: 
    - O repouso INICIA 1 minuto apos o checkout + offset_hours
    - offset_hours: 0 para Repouso normal, 12 para Simples, 16 para Composta, 24 para Revezamento
    - Periodo NOTURNO: 18:00 - 06:00
    - Periodo DIURNO: 06:00 - 18:00
    - Os valores especiais SAO SUBCONJUNTOS dos valores normais (diurno/noturno).
    """
    # Retorna zeros se tempo for negativo ou zero
    if pd.isna(tempo_repouso) or tempo_repouso <= timedelta(0):
        return (timedelta(0),) * 4
    
    # Retorna zeros se as datas são inválidas ou o intervalo é zero/negativo
    if pd.isna(checkout_dt) or pd.isna(checkin_next_dt) or checkout_dt >= checkin_next_dt:
        return (timedelta(0),) * 4

    # O repouso INICIA 1 minuto apos o checkout + offset (12h, 16h ou 24h para extras)
    repouso_start = checkout_dt + timedelta(hours=offset_hours, minutes=1)
    repouso_end = repouso_start + tempo_repouso
    
    # Garante que nao ultrapasse checkin_next_dt
    if repouso_end > checkin_next_dt:
        repouso_end = checkin_next_dt
        # Ajusta o tempo de repouso para o real disponivel
        tempo_repouso = repouso_end - repouso_start
    
    # Se tempo ficou negativo ou zero apos ajuste, retorna zeros
    if tempo_repouso <= timedelta(0):
        return (timedelta(0),) * 4

    # --- Cálculo de Tempos Diurno/Noturno Padrão ---
    # Noturno: 18:00 - 06:00
    # Diurno: 06:00 - 18:00
    repouso_night_total = get_interval_overlap_with_repeating_period(repouso_start, repouso_end, 18, 0, 6, 0)
    repouso_day_total = tempo_repouso - repouso_night_total

    # --- Cálculo de Tempos Diurno/Noturno Especiais ---
    # Especiais sao PARTE dos valores normais, nao adicionais
    repouso_special_day = timedelta(0)
    repouso_special_night = timedelta(0)

    # Itera minuto a minuto para verificar se cada momento é especial
    current_dt = repouso_start
    while current_dt < repouso_end:
        next_dt = current_dt + timedelta(minutes=1)
        if next_dt > repouso_end:
            delta = repouso_end - current_dt
            next_dt = repouso_end
        else:
            delta = timedelta(minutes=1)
        
        # Verificar se o momento atual é especial
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
        
        # Se for especial, acumula nos contadores especiais
        if eh_especial:
            # Verificar se é noturno (18:00-06:00)
            if current_hour >= 18 or current_hour < 6:
                repouso_special_night += delta
            else:
                repouso_special_day += delta
        
        current_dt = next_dt

    return (repouso_day_total, repouso_night_total, repouso_special_day, repouso_special_night)

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

# --- Lógica Principal do Script ---
def processar_dados_aeronautica():
    input_csv_path, output_dir = determinar_diretorio_e_arquivo()
    if not input_csv_path or not output_dir:
        return

    # --- 2. Carregar e Preparar Dados de Apoio ---
    print("Carregando arquivos de apoio (tipos_voo.json, feriados.json)...")
    try:
        tipos_voo_data = load_json_to_set('tipos_voo.json', type_expected='string')
        feriados_data = load_json_to_set('feriados.json', type_expected='date')
    except Exception as e:
        print(f"Erro ao carregar arquivos de apoio: {e}")
        return

    # --- 3. Leitura do CSV e Pré-processamento ---
    print(f"Lendo o arquivo CSV: {input_csv_path}")
    try:
        try:
            df = pd.read_csv(input_csv_path)
        except UnicodeDecodeError:
            df = pd.read_csv(input_csv_path, encoding='latin1')
        
        column_map_input_to_internal = {
            'Activity': 'activity', 'Id_Leg': 'id_leg', 'Checkin': 'checkin',
            'Start': 'start', 'Dep': 'dep', 'Arr': 'arr', 'End': 'end',
            'Checkout': 'checkout',
            'Tempo Repouso': 'tempo_repouso',
            'Tempo Repouso Extra Simples': 'tempo_repouso_extra_simples',
            'Tempo Repouso Extra Composta': 'tempo_repouso_extra_composta',
            'Tempo Repouso Extra Revezamento': 'tempo_repouso_extra_revezamento',
            'ACVer': 'acver', 'DD': 'dd', 'CAT': 'cat', 'Crew': 'crew'
        }

        current_columns_lower = {col.lower(): col for col in df.columns}
        
        rename_dict = {}
        for input_col_expected, internal_col_name in column_map_input_to_internal.items():
            if input_col_expected in df.columns:
                rename_dict[input_col_expected] = internal_col_name
            elif input_col_expected.lower() in current_columns_lower:
                rename_dict[current_columns_lower[input_col_expected.lower()]] = internal_col_name
            else:
                print(f"Aviso: Coluna '{input_col_expected}' não encontrada no arquivo CSV. Será tratada como ausente.")
                df[internal_col_name] = np.nan

        df.rename(columns=rename_dict, inplace=True)

        required_internal_cols = ['activity', 'id_leg', 'checkin', 'start', 'dep', 'arr', 'end', 'checkout']
        if not all(col in df.columns for col in required_internal_cols):
            missing_cols = [col for col in required_internal_cols if col not in df.columns]
            messagebox.showerror("Erro de Colunas", f"O arquivo CSV não contém todas as colunas necessárias para processamento interno. Faltam: {missing_cols}")
            return

    except Exception as e:
        messagebox.showerror("Erro de Leitura", f"Erro ao ler o arquivo CSV ou processar colunas: {e}")
        print(f"ERRO: Erro ao ler o arquivo CSV ou processar colunas: {e}")
        return

    print("CSV lido com sucesso e colunas normalizadas para processamento.")

    # --- 4. Otimização de Tipos de Dados e Conversão de Data/Hora ---
    print("Otimizando tipos de dados e convertendo colunas de data/hora...")

    for col in ['activity', 'dep', 'arr', 'acver', 'dd', 'cat']:
        if col in df.columns and df[col].dtype == 'object':
            df[col] = df[col].astype('category')
    
    datetime_internal_cols = ['checkin', 'start', 'end', 'checkout']
    for col in datetime_internal_cols:
        if col in df.columns:
            def parse_dt_value(val):
                if pd.isna(val) or val == '':
                    return pd.NaT
                try:
                    num_val = float(val)
                    if num_val > 0: 
                        return parse_date_from_excel_serial(num_val)
                except (ValueError, TypeError):
                    pass

                try:
                    formats = ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', 
                               '%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M', 
                               '%H:%M:%S', '%m/%d/%Y %H:%M:%S', '%Y-%m-%d']
                    for fmt in formats:
                        try:
                            if fmt in ['%H:%M:%S', '%H:%M']:
                                parsed_time = datetime.strptime(str(val), fmt).time()
                                return datetime.combine(date(1900,1,1), parsed_time)
                            else:
                                return pd.to_datetime(str(val), format=fmt)
                        except ValueError:
                            continue
                    return pd.to_datetime(str(val), infer_datetime_format=True, errors='coerce')
                except (ValueError, TypeError):
                    return pd.NaT
            
            df[col] = df[col].apply(parse_dt_value)
        else:
            df[col] = pd.NaT

    print("Colunas de data/hora convertidas.")
    print("Amostra de colunas de tempo após conversão:")
    print(df[['checkin', 'start', 'end', 'checkout']].head().to_string())
    
    # Converter colunas de tempo de repouso para timedelta
    print("\nConvertendo colunas de tempo de repouso...")
    timedelta_cols = ['tempo_repouso', 'tempo_repouso_extra_simples', 
                      'tempo_repouso_extra_composta', 'tempo_repouso_extra_revezamento']
    
    for col in timedelta_cols:
        if col in df.columns:
            try:
                df[col] = pd.to_timedelta(df[col], errors='coerce')
                print(f"Coluna '{col}' convertida para timedelta")
            except Exception as e:
                print(f"Erro ao converter coluna '{col}': {e}")
                df[col] = pd.Timedelta(0)
        else:
            print(f"Coluna '{col}' nao encontrada - sera criada com zeros")
            df[col] = pd.Timedelta(0)

    # --- 5. Filtragem por tipos_voo.json E Id_Leg ---
    initial_row_count = len(df)
    
    def activity_starts_with_valid_tipos(activity_str):
        if pd.isna(activity_str) or not tipos_voo_data:
            return False
        activity_clean = str(activity_str).strip().upper()
        return any(activity_clean.startswith(tipo) for tipo in tipos_voo_data)

    activity_filter_condition = df['activity'].apply(activity_starts_with_valid_tipos) if tipos_voo_data else pd.Series(True, index=df.index)
    
    id_leg_filter_condition_for_inclusion = df['id_leg'].notna() & df['id_leg'].astype(str).str.endswith(('-F', '-IF'))

    nome_arquivo_upper = os.path.basename(input_csv_path).upper()
    cond_latam_json = pd.Series(False, index=df.index)
    if "LATAM" in nome_arquivo_upper:
        atividade_voo_latam = (
            df['activity']
            .astype(str)
            .str.strip()
            .str.upper()
            .str.match(r'^[A-Z]{2,3}\d{2,5}[A-Z]?$', na=False)
        )
        latam_paid_flight_activities = _carregar_atividades_pagas_regras_voo_latam()
        cond_latam_json = df['activity'].astype(str).str.strip().str.upper().isin(latam_paid_flight_activities)
        activity_filter_condition = activity_filter_condition | atividade_voo_latam | cond_latam_json

    id_leg_filter_condition_for_inclusion = id_leg_filter_condition_for_inclusion | cond_latam_json

    if tipos_voo_data or "LATAM" in nome_arquivo_upper:
        df_processed = df[activity_filter_condition & id_leg_filter_condition_for_inclusion].copy()
        print(f"Total de linhas lidas: {initial_row_count}. Linhas após filtrar por tipos_voo/LATAM E Id_Leg: {len(df_processed)}")

        if initial_row_count - len(df_processed) > 0:
            print(f"{initial_row_count - len(df_processed)} linhas foram removidas (não atendem aos critérios de filtro).")
        else:
            print("Todas as linhas atendem aos critérios de filtro.")
    else:
        df_processed = df[id_leg_filter_condition_for_inclusion].copy()
        print(f"Aviso: Dados de tipos_voo ausentes/vazios. Filtragem aplicada apenas por Id_Leg. Total de linhas lidas: {initial_row_count}. Linhas após filtrar por Id_Leg: {len(df_processed)}")

    df_processed.drop(columns=['activity_prefix'], inplace=True, errors='ignore')

    # --- 6. Calcular Tempo Repouso Extra ---
    print("Calculando Tempo de Repouso Extra (apenas tempo além de 12 horas)...")

    df_processed = df_processed.sort_values(by=['checkout']).reset_index(drop=True)
    
    df_processed['checkin_next_leg'] = df_processed['checkin'].shift(-1)
    df_processed['start_next_leg'] = df_processed['start'].shift(-1)
    
    # Criar coluna com Activity da proxima linha (limpa e em maiúsculas)
    df_processed['activity_next_leg'] = df_processed['activity'].shift(-1)
    
    # Normalizar Activity para garantir comparacao correta (remover espacos e uppercase)
    df_processed['activity_next_leg_clean'] = df_processed['activity_next_leg'].astype(str).str.strip().str.upper()

    # Inicializa colunas de tempo repouso extra
    df_processed['tempo_repouso_extra_total'] = pd.Timedelta(0) 
    new_internal_calculated_columns = [
        'repouso_extra_day_total', 'repouso_extra_night_total',
        'repouso_extra_special_day', 'repouso_extra_special_night'
    ]
    for col in new_internal_calculated_columns:
        df_processed[col] = pd.Timedelta(0) 

    # Máscara para cálculo válido.
    # Regra geral: próxima activity iniciando com AD.
    # Regra LATAM: aceitar também padrões de voo (ex.: LA3128).
    is_latam_source = "LATAM" in os.path.basename(input_csv_path).upper()
    cond_proxima_activity_ad = df_processed['activity_next_leg_clean'].str.startswith('AD')
    cond_proxima_activity_voo_latam = df_processed['activity_next_leg_clean'].str.match(r'^[A-Z]{2,3}\d{2,5}[A-Z]?$', na=False)
    cond_proxima_activity_valida = cond_proxima_activity_ad | (is_latam_source & cond_proxima_activity_voo_latam)

    # Mantém a consistência da regra original quando não LATAM.
    cond_checkin_start_diferentes = (df_processed['checkin_next_leg'] != df_processed['start_next_leg'])

    mask_for_actual_calculation = (
        df_processed['checkout'].notna() & 
        df_processed['checkin_next_leg'].notna() & 
        (df_processed['checkout'] < df_processed['checkin_next_leg']) &
        cond_proxima_activity_valida &
        (cond_checkin_start_diferentes | is_latam_source)
    )
    
    print(f"Linhas que atendem condicao para calculo de Repouso Extra: {mask_for_actual_calculation.sum()}")
    
    # Calcula o tempo de repouso total (checkin da próxima etapa - checkout da etapa atual)
    tempo_repouso_total = df_processed.loc[mask_for_actual_calculation, 'checkin_next_leg'] - df_processed.loc[mask_for_actual_calculation, 'checkout']
    
    # 1. Preencher Tempo Repouso (Total)
    df_processed.loc[mask_for_actual_calculation, 'tempo_repouso'] = tempo_repouso_total
    
    # 2. Preencher Repouso Extra Simples (> 12h)
    mask_repouso_maior_12h = tempo_repouso_total > pd.Timedelta(hours=12)
    df_processed.loc[mask_for_actual_calculation & mask_repouso_maior_12h, 'tempo_repouso_extra_total'] = \
        tempo_repouso_total[mask_repouso_maior_12h] - pd.Timedelta(hours=12)
    df_processed.loc[mask_for_actual_calculation & mask_repouso_maior_12h, 'tempo_repouso_extra_simples'] = \
        tempo_repouso_total[mask_repouso_maior_12h] - pd.Timedelta(hours=12)
        
    # 3. Preencher Repouso Extra Composta (> 16h)
    mask_repouso_maior_16h = tempo_repouso_total > pd.Timedelta(hours=16)
    df_processed.loc[mask_for_actual_calculation & mask_repouso_maior_16h, 'tempo_repouso_extra_composta'] = \
        tempo_repouso_total[mask_repouso_maior_16h] - pd.Timedelta(hours=16)
        
    # 4. Preencher Repouso Extra Revezamento (> 24h)
    mask_repouso_maior_24h = tempo_repouso_total > pd.Timedelta(hours=24)
    df_processed.loc[mask_for_actual_calculation & mask_repouso_maior_24h, 'tempo_repouso_extra_revezamento'] = \
        tempo_repouso_total[mask_repouso_maior_24h] - pd.Timedelta(hours=24)
    
    # Aplica a função de cálculo para Repouso Extra detalhado
    mask_final = mask_for_actual_calculation & mask_repouso_maior_12h
    if mask_final.any():
        results = df_processed.loc[mask_final].apply(
            lambda row: calculate_repouso_extra_durations(row['checkout'], row['checkin_next_leg'], feriados_data), 
            axis=1,
            result_type='expand' 
        )
        
        results.columns = new_internal_calculated_columns
        
        df_processed.loc[mask_final, new_internal_calculated_columns] = results

    # Garante que todas as colunas calculadas sejam Timedelta
    for col in new_internal_calculated_columns:
        df_processed[col] = pd.to_timedelta(df_processed[col], errors='coerce').fillna(pd.Timedelta(0))

    df_processed.drop(columns=['checkin_next_leg'], inplace=True, errors='ignore')

    print("Cálculos de Repouso Extra concluídos.")
    
    # --- 6B. Calcular Diurno/Noturno/Especial para as 4 colunas de Tempo Repouso ---
    print("\nCalculando breakdown de Tempo Repouso, Simples, Composta e Revezamento...")
    
    # Colunas a processar com seus respectivos offsets (em horas apos checkout)
    repouso_columns = [
        ('tempo_repouso', 'Repouso', 0),                                    # Inicia 1min apos checkout
        ('tempo_repouso_extra_simples', 'Repouso Extra Simples', 12),      # Inicia 12h + 1min apos checkout
        ('tempo_repouso_extra_composta', 'Repouso Extra Composta', 16),    # Inicia 16h + 1min apos checkout
        ('tempo_repouso_extra_revezamento', 'Repouso Extra Revezamento', 24) # Inicia 24h + 1min apos checkout
    ]
    
    for internal_col, display_name, offset_hours in repouso_columns:
        print(f"Processando: {display_name} (offset: {offset_hours}h)...")
        
        # Inicializar colunas
        df_processed[f'{internal_col}_day'] = pd.Timedelta(0)
        df_processed[f'{internal_col}_night'] = pd.Timedelta(0)
        df_processed[f'{internal_col}_special_day'] = pd.Timedelta(0)
        df_processed[f'{internal_col}_special_night'] = pd.Timedelta(0)
        
        # Mascara: valores validos (positivos, nao nulos, com checkout e checkin validos)
        mask_valid = (
            df_processed['checkout'].notna() &
            df_processed['checkin'].shift(-1).notna() &
            df_processed[internal_col].notna() &
            (df_processed[internal_col] > pd.Timedelta(0))
        )
        
        if mask_valid.any():
            # Calcular breakdown para cada linha valida
            results_breakdown = df_processed.loc[mask_valid].apply(
                lambda row: calculate_repouso_breakdown(
                    row['checkout'], 
                    df_processed.loc[row.name + 1, 'checkin'] if row.name + 1 < len(df_processed) else pd.NaT,
                    row[internal_col],
                    feriados_data,
                    offset_hours  # Passa o offset correto para cada tipo de repouso
                ),
                axis=1,
                result_type='expand'
            )
            
            results_breakdown.columns = [
                f'{internal_col}_day',
                f'{internal_col}_night', 
                f'{internal_col}_special_day',
                f'{internal_col}_special_night'
            ]
            
            df_processed.loc[mask_valid, results_breakdown.columns] = results_breakdown
            
            print(f"  {display_name}: {mask_valid.sum()} linhas calculadas")
        else:
            print(f"  {display_name}: Nenhuma linha valida para calcular")
    
    print("Calculos de breakdown de Repouso concluidos.")

    # --- 7. Preparar DataFrame para Saída ---
    final_output_columns_pascal_case = [
        'Activity', 'Id_Leg', 'Checkin', 'Start', 'Dep', 'Arr', 'End', 'Checkout',
        # Tempo Repouso
        'Tempo Repouso',
        'Tempo Repouso Diurno', 'Tempo Repouso Noturno',
        'Tempo Repouso Especial Diurno', 'Tempo Repouso Especial Noturno',
        # Tempo Repouso Extra Simples
        'Tempo Repouso Extra Simples',
        'Tempo Repouso Extra Simples Diurno', 'Tempo Repouso Extra Simples Noturno',
        'Tempo Repouso Extra Simples Especial Diurno', 'Tempo Repouso Extra Simples Especial Noturno',
        # Tempo Repouso Extra Composta
        'Tempo Repouso Extra Composta',
        'Tempo Repouso Extra Composta Diurno', 'Tempo Repouso Extra Composta Noturno',
        'Tempo Repouso Extra Composta Especial Diurno', 'Tempo Repouso Extra Composta Especial Noturno',
        # Tempo Repouso Extra Revezamento
        'Tempo Repouso Extra Revezamento',
        'Tempo Repouso Extra Revezamento Diurno', 'Tempo Repouso Extra Revezamento Noturno',
        'Tempo Repouso Extra Revezamento Especial Diurno', 'Tempo Repouso Extra Revezamento Especial Noturno'
    ]

    internal_to_output_name_map = {
        'activity': 'Activity', 'id_leg': 'Id_Leg', 'checkin': 'Checkin',
        'start': 'Start', 'end': 'End', 'dep': 'Dep', 'arr': 'Arr',
        'checkout': 'Checkout',
        # Tempo Repouso
        'tempo_repouso': 'Tempo Repouso',
        'tempo_repouso_day': 'Tempo Repouso Diurno',
        'tempo_repouso_night': 'Tempo Repouso Noturno',
        'tempo_repouso_special_day': 'Tempo Repouso Especial Diurno',
        'tempo_repouso_special_night': 'Tempo Repouso Especial Noturno',
        # Tempo Repouso Extra Simples
        'tempo_repouso_extra_simples': 'Tempo Repouso Extra Simples',
        'tempo_repouso_extra_simples_day': 'Tempo Repouso Extra Simples Diurno',
        'tempo_repouso_extra_simples_night': 'Tempo Repouso Extra Simples Noturno',
        'tempo_repouso_extra_simples_special_day': 'Tempo Repouso Extra Simples Especial Diurno',
        'tempo_repouso_extra_simples_special_night': 'Tempo Repouso Extra Simples Especial Noturno',
        # Tempo Repouso Extra Composta
        'tempo_repouso_extra_composta': 'Tempo Repouso Extra Composta',
        'tempo_repouso_extra_composta_day': 'Tempo Repouso Extra Composta Diurno',
        'tempo_repouso_extra_composta_night': 'Tempo Repouso Extra Composta Noturno',
        'tempo_repouso_extra_composta_special_day': 'Tempo Repouso Extra Composta Especial Diurno',
        'tempo_repouso_extra_composta_special_night': 'Tempo Repouso Extra Composta Especial Noturno',
        # Tempo Repouso Extra Revezamento
        'tempo_repouso_extra_revezamento': 'Tempo Repouso Extra Revezamento',
        'tempo_repouso_extra_revezamento_day': 'Tempo Repouso Extra Revezamento Diurno',
        'tempo_repouso_extra_revezamento_night': 'Tempo Repouso Extra Revezamento Noturno',
        'tempo_repouso_extra_revezamento_special_day': 'Tempo Repouso Extra Revezamento Especial Diurno',
        'tempo_repouso_extra_revezamento_special_night': 'Tempo Repouso Extra Revezamento Especial Noturno'
    }

    df_output = pd.DataFrame(columns=final_output_columns_pascal_case)

    for internal_col, output_col in internal_to_output_name_map.items():
        if internal_col in df_processed.columns:
            df_output[output_col] = df_processed[internal_col]
        else:
            if 'tempo' in internal_col or 'repouso' in internal_col:
                df_output[output_col] = pd.Timedelta(0)
            elif 'date' in internal_col or 'time' in internal_col:
                df_output[output_col] = pd.NaT
            else:
                df_output[output_col] = ''

    print("\n--- dtypes of df_output before final formatting ---")
    print(df_output.dtypes)
    print("---------------------------------------------------\n")

    # Formatar colunas Timedelta
    timedelta_cols_for_format = [
        # Tempo Repouso
        'Tempo Repouso',
        'Tempo Repouso Diurno', 'Tempo Repouso Noturno',
        'Tempo Repouso Especial Diurno', 'Tempo Repouso Especial Noturno',
        # Tempo Repouso Extra Simples
        'Tempo Repouso Extra Simples',
        'Tempo Repouso Extra Simples Diurno', 'Tempo Repouso Extra Simples Noturno',
        'Tempo Repouso Extra Simples Especial Diurno', 'Tempo Repouso Extra Simples Especial Noturno',
        # Tempo Repouso Extra Composta
        'Tempo Repouso Extra Composta',
        'Tempo Repouso Extra Composta Diurno', 'Tempo Repouso Extra Composta Noturno',
        'Tempo Repouso Extra Composta Especial Diurno', 'Tempo Repouso Extra Composta Especial Noturno',
        # Tempo Repouso Extra Revezamento
        'Tempo Repouso Extra Revezamento',
        'Tempo Repouso Extra Revezamento Diurno', 'Tempo Repouso Extra Revezamento Noturno',
        'Tempo Repouso Extra Revezamento Especial Diurno', 'Tempo Repouso Extra Revezamento Especial Noturno'
    ]
    for col in timedelta_cols_for_format:
        if col in df_output.columns:
            df_output[col] = df_output[col].apply(format_timedelta_to_hms)

    # Formatar colunas datetime
    datetime_cols_for_format = ['Checkin', 'Start', 'End', 'Checkout'] 
    for col in datetime_cols_for_format:
        if col in df_output.columns:
            df_output[col] = df_output[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    print("\n--- Primeiras 5 linhas do DataFrame FINAL com colunas calculadas e formatadas ---")
    display_cols_example = [col for col in final_output_columns_pascal_case if col in df_output.columns]
    print(df_output[display_cols_example].head(5).to_string())
    print("---------------------------------------------------------------\n")

    # --- 8. Salvamento do Arquivo CSV de Saída ---
    base_output_filename = gerar_nome_csv_saida_base(input_csv_path) 
    timestamp = datetime.now().strftime("%d%m%Y_%H%M%S") 
    
    name_part, ext_part = os.path.splitext(base_output_filename)
    output_filename_with_timestamp = f"{name_part}_{timestamp}{ext_part}"
    
    output_file_path = os.path.join(output_dir, output_filename_with_timestamp)

    if df_processed.empty and not tipos_voo_data:
        messagebox.showinfo("Processamento Concluído", "Nenhuma linha foi processada, pois 'tipos_voo.json' está vazio ou não possui atividades para inclusão.\n\nO arquivo CSV será criado apenas com cabeçalhos.")
        print("Nenhuma linha foi processada, pois 'tipos_voo.json' está vazio ou não possui atividades para inclusão.")
        print("O arquivo CSV será criado apenas com cabeçalhos.\n")
    elif df_processed.empty:
        messagebox.showinfo("Processamento Concluído", "Nenhuma linha foi processada após a aplicação dos filtros.\n\nO arquivo CSV será criado apenas com cabeçalhos.")
        print("Nenhuma linha foi processada após a aplicação dos filtros.")
        print("O arquivo CSV será criado apenas com cabeçalhos.\n")

    try:
        df_output.to_csv(output_file_path, index=False, encoding='utf-8-sig')
        print(f"Arquivo '{output_filename_with_timestamp}' salvo com sucesso em: {output_file_path}")
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
