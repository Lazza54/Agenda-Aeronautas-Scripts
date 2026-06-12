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
BASE_COMMON_FILES_PATH = r'R:\SPECTRUM_SYSTEM\Aeronautas\Documentos_Comuns\Arquivos_Diversos'

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


def _resolver_json_apoio(file_name: str) -> list[str]:
    base_dir = BASE_COMMON_FILES_PATH
    candidatos = []
    if _arquivo_entrada_eh_latam():
        stem, ext = os.path.splitext(file_name)
        candidatos.append(os.path.join(base_dir, f"{stem}_LATAM{ext}"))
        if file_name.lower() == "folgas.json":
            candidatos.append(os.path.join(base_dir, "folgas_regulamentares_LATAM.json"))
            candidatos.append(os.path.join(base_dir, "folgas_regulamentares.json"))
    candidatos.append(os.path.join(base_dir, file_name))
    existentes = [c for c in candidatos if os.path.exists(c)]
    return existentes if existentes else [candidatos[-1]]

def gerar_nome_csv_saida_base(nome_csv_entrada: str) -> str:
    """
    Gera o nome base do arquivo CSV de saída (sem timestamp), substituindo sufixos de etapas anteriores
    por '_REPOUSO'.
    """
    base_nome = os.path.basename(nome_csv_entrada)
    nome_sem_ext, _ = os.path.splitext(base_nome)

    # Lista de sufixos de etapas anteriores para remover
    previous_stage_suffixes = ['_APRESENTACAO', '_OPERACAO', '_TEMPO_CORTE', '_TEMPO_SOLO', '_QUARTA_VERSAO']
    
    cleaned_name = nome_sem_ext
    for suffix in previous_stage_suffixes:
        if suffix in cleaned_name:
            cleaned_name = cleaned_name.replace(suffix, '')
    
    # Remove qualquer timestamp existente para garantir um nome base limpo
    timestamp_pattern = r'_\d{8}_\d{6}$' # Exemplo: _YYYYMMDD_HHMMSS
    cleaned_name = re.sub(timestamp_pattern, '', cleaned_name)

    # Garante que o nome termine com o sufixo correto para esta etapa
    if not cleaned_name.endswith('_REPOUSO'):
        return f"{cleaned_name}_REPOUSO.csv"
    
    return f"{cleaned_name}.csv" # Caso já termine com _REPOUSO

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
        title="Selecione o arquivo CSV de entrada para processar",
        filetypes=[("Arquivos CSV", "*.csv")]
    )

    if not input_file_path:
        messagebox.showwarning("Seleção Cancelada", "Nenhum arquivo de entrada selecionado. O script será encerrado.")
        return None, None

    output_dir = os.path.dirname(input_file_path)

    return input_file_path, output_dir

def parse_date_from_excel_serial(serial_value):
    """Converte um número de série do Excel para datetime.datetime."""
    # Pandas to_datetime handles Excel serials well with origin
    # Excel's epoch is 1899-12-30 for dates, so for serial numbers, it's relative to that.
    # We must ensure the input is a numeric type for this to work.
    if pd.isna(serial_value):
        return pd.NaT
    try:
        # Convert to float first to handle potential string representations of numbers
        num_val = float(serial_value)
        # Dates before 1900 are handled differently by Excel (Excel bug with 1900 being leap year)
        # pandas to_datetime with origin='1899-12-30' is generally correct for Excel serials.
        return pd.to_datetime(num_val, unit='D', origin='1899-12-30')
    except (ValueError, TypeError):
        return pd.NaT


def load_json_to_set(file_name: str, type_expected: str = 'string') -> set:
    """
    Carrega um arquivo JSON e tenta extrair um conjunto de valores.
    'type_expected' pode ser 'string' (para tipos_voo) ou 'date' (para feriados).
    """
    file_candidates = _resolver_json_apoio(file_name)
    data = None
    file_path = file_candidates[0]

    for idx, candidato in enumerate(file_candidates):
        file_path = candidato
        print(f"Tentando carregar arquivo de configuração: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            break
        except json.JSONDecodeError as e:
            if idx < len(file_candidates) - 1:
                print(f"Aviso: JSON inválido em {file_path}: {e}. Tentando fallback...")
                continue
            raise

    try:
        if data is None:
            raise FileNotFoundError(file_path)

        extracted_values = set()
        
        def process_item(item):
            if type_expected == 'string':
                if isinstance(item, str):
                    extracted_values.add(item.strip().upper()) # Normalização forte para strings
                elif isinstance(item, dict):
                    # Tenta encontrar chaves como 'atividade', 'Activity', 'name'
                    for key in ['atividade', 'Activity', 'name']:
                        if key in item and isinstance(item[key], str):
                            extracted_values.add(item[key].strip().upper())
                            return
            elif type_expected == 'date':
                parsed_date = pd.NaT
                if isinstance(item, str):
                    # Tentar parsear string de data
                    formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d']
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(item, fmt).date()
                            break
                        except ValueError:
                            continue
                    if pd.isna(parsed_date) and item.replace('.', '').isdigit(): # Tentativa para strings que parecem números
                         try:
                             parsed_date = parse_date_from_excel_serial(float(item)).date()
                         except:
                             pass

                elif isinstance(item, (int, float)):
                    # Tentar parsear número de série do Excel
                    try:
                        parsed_date = parse_date_from_excel_serial(item).date()
                    except:
                        pass
                
                elif isinstance(item, dict):
                    # Tenta encontrar chaves como 'date', 'data'
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
            # Procura por listas aninhadas, ou processa valores do dict
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
    """
    total_overlap = timedelta(0)
    
    # Se o evento ou o período forem inválidos, retorna 0
    if pd.isna(event_start_dt) or pd.isna(event_end_dt) or event_start_dt >= event_end_dt:
        return timedelta(0)

    # Garante que as horas e minutos estejam no intervalo de 0-23 e 0-59
    period_start_hour %= 24
    period_end_hour %= 24
    period_start_minute %= 60
    period_end_minute %= 60

    period_start_time = time(period_start_hour, period_start_minute)
    period_end_time = time(period_end_hour, period_end_minute)

    # Determine the starting day for iteration.
    # If the repeating period crosses midnight (e.g., 21:00-09:00),
    # and the event starts in the "morning" part of this period (before period_end_time),
    # then the relevant repeating period instance started on the *previous* calendar day.
    current_day_iter_dt = event_start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if period_end_time < period_start_time and event_start_dt.time() < period_end_time:
        current_day_iter_dt -= timedelta(days=1)
    
    # Iterar dia a dia que o evento abrange
    # A iteração vai até o dia seguinte ao final do evento para capturar períodos que cruzam a meia-noite
    # e garantir que todo o intervalo do evento seja coberto.
    while current_day_iter_dt.date() <= event_end_dt.date() + timedelta(days=1): 
        
        # Define o início e fim do período para o dia atual da iteração
        period_start_on_current_day = datetime.combine(current_day_iter_dt.date(), period_start_time)
        period_end_on_current_day = datetime.combine(current_day_iter_dt.date(), period_end_time)

        # Se o período cruza a meia-noite (ex: 18:00 para 06:00 do dia seguinte), ajusta o fim do período
        if period_end_time < period_start_time:
            period_end_on_current_day += timedelta(days=1)

        # Calcula a sobreposição entre o intervalo do evento e a instância atual do período diário
        overlap_start = max(event_start_dt, period_start_on_current_day)
        overlap_end = min(event_end_dt, period_end_on_current_day)

        if overlap_end > overlap_start:
            total_overlap += (overlap_end - overlap_start)
            
        current_day_iter_dt += timedelta(days=1) # Move para o próximo dia calendário
    
    return total_overlap

# Função generalizada para calcular durações de atividade principal e pagamento
def calculate_main_activity_and_payment_durations(activity_start_dt: datetime, activity_end_dt: datetime, holidays_set: set) -> tuple:
    """
    Calcula os tempos diurnos/noturnos (normais e especiais) para Repouso e Pagamento
    de um determinado intervalo (activity_start_dt, activity_end_dt).
    
    Períodos especiais (total 24h):
    - Sábado: 21:00 sáb → 18:00 dom (21h)
    - Domingo: 18:00 dom → 21:00 dom (3h)
    - Véspera feriado: 21:00 véspera → 18:00 feriado (21h)
    - Feriado: 18:00 feriado → 21:00 feriado (3h)
    
    Segue a mesma lógica de calculate_apresentacao_and_payment_durations do CRIA VALORES FINAIS APRESENTACAO.
    """
    # Retorna zeros se as datas são inválidas ou o intervalo é zero/negativo
    if pd.isna(activity_start_dt) or pd.isna(activity_end_dt) or activity_start_dt >= activity_end_dt:
        return (timedelta(0),) * 8

    # Duração total do evento (activity_start_dt ao activity_end_dt)
    total_event_duration = activity_end_dt - activity_start_dt

    # --- Cálculo de Tempos Diurno/Noturno Padrão ---
    # Repouso: Noturno 18:00 - 06:00
    main_activity_night_total = get_interval_overlap_with_repeating_period(activity_start_dt, activity_end_dt, 18, 0, 6, 0)
    main_activity_day_total = total_event_duration - main_activity_night_total

    # Pagamento: Noturno 21:00 - 09:00
    pay_night_total = get_interval_overlap_with_repeating_period(activity_start_dt, activity_end_dt, 21, 0, 9, 0)
    pay_day_total = total_event_duration - pay_night_total

    # --- Cálculo de Tempos Diurno/Noturno Especiais ---
    main_activity_special_day = timedelta(0)
    main_activity_special_night = timedelta(0)
    pay_special_day = timedelta(0)
    pay_special_night = timedelta(0)

    # Itera minuto a minuto para precisão absoluta (necessário para cálculos trabalhistas)
    current_dt = activity_start_dt
    while current_dt < activity_end_dt:
        next_dt = current_dt + timedelta(minutes=1)
        if next_dt > activity_end_dt:
            delta = activity_end_dt - current_dt
            next_dt = activity_end_dt
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
            # Repouso: verificar se é noturno (18:00-06:00)
            if current_hour >= 18 or current_hour < 6:
                main_activity_special_night += delta
            else:
                main_activity_special_day += delta
            
            # Pagamento: verificar se é noturno (21:00-09:00)
            if current_hour >= 21 or current_hour < 9:
                pay_special_night += delta
            else:
                pay_special_day += delta
        
        current_dt = next_dt

    return (main_activity_day_total, main_activity_night_total, main_activity_special_day, main_activity_special_night,
            pay_day_total, pay_night_total, pay_special_day, pay_special_night)

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
    print("Carregando arquivos de apoio (tipos_voo.json, tipos_plantao.json, tipos_reserva.json, tipos_treinamentos.json, folgas.json, feriados.json)...")
    try:
        tipos_voo_data = load_json_to_set('tipos_voo.json', type_expected='string')
        tipos_plantao_data = load_json_to_set('tipos_plantao.json', type_expected='string')
        tipos_reserva_data = load_json_to_set('tipos_reserva.json', type_expected='string')
        tipos_treinamentos_data = load_json_to_set('tipos_treinamentos.json', type_expected='string')
        folgas_data = load_json_to_set('folgas.json', type_expected='string')
        feriados_data = load_json_to_set('feriados.json', type_expected='date')
        
        # Combinar todos os tipos válidos para retomada de cálculo
        tipos_validos = set()
        if tipos_voo_data:
            tipos_validos.update(tipos_voo_data)
        if tipos_plantao_data:
            tipos_validos.update(tipos_plantao_data)
        if tipos_reserva_data:
            tipos_validos.update(tipos_reserva_data)
        if tipos_treinamentos_data:
            tipos_validos.update(tipos_treinamentos_data)
            
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
        # Esta lista deve conter o NOME EXATO das colunas como elas *podem* vir no CSV de entrada
        # e seu respectivo nome interno em snake_case.
        column_map_input_to_internal = {
            'Activity': 'activity', 'Id_Leg': 'id_leg', 'Checkin': 'checkin',
            'Start': 'start', 'Dep': 'dep', 'Arr': 'arr', 'End': 'end',
            'Checkout': 'checkout',
            'ACVer': 'acver', 'DD': 'dd', 'CAT': 'cat', 'Crew': 'crew'
        }

        # Renomeia as colunas do DataFrame para os nomes internos em snake_case
        # Cria um mapeamento reverso para lidar com variações de capitalização na entrada
        current_columns_lower = {col.lower(): col for col in df.columns}
        
        rename_dict = {}
        for input_col_expected, internal_col_name in column_map_input_to_internal.items():
            if input_col_expected in df.columns: # Caso a capitalização original esteja correta
                rename_dict[input_col_expected] = internal_col_name
            elif input_col_expected.lower() in current_columns_lower: # Caso a capitalização seja diferente
                rename_dict[current_columns_lower[input_col_expected.lower()]] = internal_col_name
            else:
                # Se a coluna não for encontrada, avisar ou criar uma coluna vazia
                print(f"Aviso: Coluna '{input_col_expected}' não encontrada no arquivo CSV. Será tratada como ausente.")
                df[internal_col_name] = np.nan # Cria a coluna como NaN para evitar KeyError

        df.rename(columns=rename_dict, inplace=True)

        # Garante que as colunas essenciais para o processamento existam com os nomes internos
        # 'end' e 'start' são cruciais para esta nova tarefa de Tempo Solo
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

    # Otimizar tipos de colunas para reduzir tamanho em memória
    # Colunas com strings repetitivas
    for col in ['activity', 'dep', 'arr', 'acver', 'dd', 'cat']:
        if col in df.columns and df[col].dtype == 'object':
            df[col] = df[col].astype('category')
    
    # Converter colunas de data/hora para o formato datetime
    datetime_internal_cols = ['checkin', 'start', 'end', 'checkout'] # Dep e Arr NÃO estão aqui, pois não são datas
    for col in datetime_internal_cols:
        if col in df.columns:
            def parse_dt_value(val):
                if pd.isna(val) or val == '':
                    return pd.NaT
                try:
                    # Tenta converter para float (número de série do Excel)
                    num_val = float(val)
                    if num_val > 0: 
                        return parse_date_from_excel_serial(num_val)
                except (ValueError, TypeError):
                    pass # Não é um número, tentar como string

                # Se não for número, tenta parser como string datetime
                try:
                    # Tenta formatos comuns primeiro para robustez
                    formats = ['%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', 
                               '%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M', 
                               '%H:%M:%S', '%m/%d/%Y %H:%M:%S', '%Y-%m-%d']
                    for fmt in formats:
                        try:
                            # Usa datetime.strptime para todos os formatos
                            parsed_dt = datetime.strptime(str(val), fmt)
                            return parsed_dt
                        except ValueError:
                            continue
                    # Fallback para inferir formato
                    return pd.to_datetime(str(val), errors='coerce')
                except (ValueError, TypeError):
                    return pd.NaT # Falha total na conversão
            
            df[col] = df[col].apply(parse_dt_value)
        else:
            df[col] = pd.NaT # Cria a coluna como NaT se não existir

    print("Colunas de data/hora convertidas.")
    print("Amostra de colunas de tempo após conversão:")
    print(df[['checkin', 'start', 'end', 'checkout']].head().to_string())

    # --- 5. Filtragem por tipos válidos E Id_Leg ---
    initial_row_count = len(df)
    
    # Função para verificar se Activity inicia com tipos válidos
    def activity_starts_with_valid_tipos(activity_str):
        if pd.isna(activity_str) or not tipos_validos:
            return False
        activity_clean = str(activity_str).strip().upper()
        return any(activity_clean.startswith(tipo) for tipo in tipos_validos)
    
    # Função para verificar se Activity inicia com folga
    def activity_starts_with_folga(activity_str):
        if pd.isna(activity_str) or not folgas_data:
            return False
        activity_clean = str(activity_str).strip().upper()
        return any(activity_clean.startswith(folga) for folga in folgas_data)

    # Condição 1: 'activity' deve iniciar com tipos válidos OU folgas
    activity_filter_condition = df['activity'].apply(lambda x: activity_starts_with_valid_tipos(x) or activity_starts_with_folga(x))
    
    # Condição 2: 'id_leg' deve terminar com '-F' ou '-IF' (INCLUSÃO NO DATAFRAME)
    id_leg_filter_condition_for_inclusion = df['id_leg'].notna() & df['id_leg'].astype(str).str.endswith(('-F', '-IF'))

    # Combina as duas condições para incluir as linhas no DataFrame de saída
    if tipos_validos or folgas_data:
        df_processed = df[activity_filter_condition & id_leg_filter_condition_for_inclusion].copy()
        print(f"Total de linhas lidas: {initial_row_count}. Linhas após filtrar por tipos válidos/folgas E Id_Leg (terminando com '-F' ou '-IF'): {len(df_processed)}")

        # Fallback para LATAM: códigos de voo como LA3128 podem não casar com tipos_validos.
        nome_arquivo_upper = os.path.basename(input_csv_path).upper()
        if len(df_processed) == 0 and "LATAM" in nome_arquivo_upper:
            print("Aviso: filtro por tipos válidos retornou 0 linhas para LATAM. Aplicando fallback por padrão de número de voo + Id_Leg.")
            atividade_voo_latam = (
                df['activity']
                .astype(str)
                .str.strip()
                .str.upper()
                .str.match(r'^[A-Z]{2,3}\d{2,5}[A-Z]?$', na=False)
            )
            df_processed = df[atividade_voo_latam & id_leg_filter_condition_for_inclusion].copy()
            print(f"Linhas após fallback LATAM: {len(df_processed)}")

        if initial_row_count - len(df_processed) > 0:
            print(f"{initial_row_count - len(df_processed)} linhas foram removidas (não atendem aos critérios de filtro).")
        else:
            print("Todas as linhas atendem aos critérios de filtro.")
    else:
        df_processed = df[id_leg_filter_condition_for_inclusion].copy()
        print(f"Aviso: Dados de tipos ausentes/vazios. Filtragem aplicada apenas por Id_Leg. Total de linhas lidas: {initial_row_count}. Linhas após filtrar por Id_Leg: {len(df_processed)}")

    # --- 6. Calcular Tempo Repouso e as 8 Novas Colunas (Tempo Repouso e Pagamento) ---
    print("Calculando Tempo de Repouso e os novos tempos de pagamento...")

    # --- Passo especial para Tempo Repouso: Ordenar e Obter dados da Próxima Linha ---
    # Assegura que os dados estão ordenados por 'checkout' para obter corretamente a próxima linha
    df_processed = df_processed.sort_values(by=['checkout']).reset_index(drop=True)
    
    # Normalizar Id_Leg e Activity seguindo o padrão do CALCULOS VALORES INICIAIS 22082025 PASSO 4
    df_processed['id_leg_norm'] = df_processed['id_leg'].astype(str).str.strip().str.upper()
    
    # Extrair o prefixo alfabético da Activity para Activity_Norm
    # Isso vai transformar 'AD5046' em 'AD', 'FR' em 'FR', etc.
    df_processed['activity_norm'] = df_processed['activity'].astype(str).str.upper().str.extract(r'^([A-Z]+)', expand=False)
    # Para casos onde a atividade não começa com letras, usamos a Activity original em maiúsculas
    df_processed['activity_norm'] = df_processed['activity_norm'].fillna(df_processed['activity'].astype(str).str.upper())
    
    # Inicializa colunas de tempo repouso e pagamento com zero
    df_processed['tempo_repouso_total'] = pd.Timedelta(0) 
    new_internal_calculated_columns = [
        'main_activity_day_total', 'main_activity_night_total',
        'main_activity_special_day', 'main_activity_special_night',
        'pay_day_total', 'pay_night_total',
        'pay_special_day', 'pay_special_night'
    ]
    for col in new_internal_calculated_columns:
        df_processed[col] = pd.Timedelta(0) 

    # --- Cálculo de Tempo Repouso seguindo CALCULOS VALORES INICIAIS 22082025 PASSO 4 ---
    # Tempo Repouso = Checkin da próxima linha - Checkout da linha atual
    # Condição: Id_Leg_Norm in ['-IF', '-F'] AND Activity_Norm NOT in folgas
    df_processed['checkin_next_leg'] = df_processed['checkin'].shift(-1)
    
    cond_repouso = (
        df_processed['id_leg_norm'].isin(['-IF', '-F']) & 
        (~df_processed['activity_norm'].isin(folgas_data))
    )
    
    print(f"Linhas que atendem condição para cálculo de Repouso: {cond_repouso.sum()}")
    
    # Calcula o Tempo Repouso para as linhas válidas
    df_processed['tempo_repouso_total'] = pd.Timedelta(0)
    tempo_repouso_calculated = df_processed.loc[cond_repouso, 'checkin_next_leg'] - df_processed.loc[cond_repouso, 'checkout']
    df_processed.loc[cond_repouso, 'tempo_repouso_total'] = tempo_repouso_calculated
    
    # Aplica a função de cálculo para Tempo Repouso detalhado e Pagamento, APENAS para as linhas válidas
    # 'results' será um DataFrame com as 8 colunas calculadas
    if cond_repouso.any():
        results = df_processed.loc[cond_repouso].apply(
            lambda row: calculate_main_activity_and_payment_durations(row['checkout'], row['checkin_next_leg'], feriados_data), 
            axis=1,
            result_type='expand' 
        )

        results.columns = new_internal_calculated_columns

        # Atribui os resultados de volta ao DataFrame principal para as linhas correspondentes
        df_processed.loc[cond_repouso, new_internal_calculated_columns] = results
    else:
        print("Aviso: nenhuma linha válida para cálculo detalhado de repouso/pagamento.")

    # Garante que todas as colunas calculadas sejam Timedelta e preenche NaT com 0s
    df_processed['tempo_repouso_total'] = pd.to_timedelta(df_processed['tempo_repouso_total'], errors='coerce').fillna(pd.Timedelta(0))
    for col in new_internal_calculated_columns:
        df_processed[col] = pd.to_timedelta(df_processed[col], errors='coerce').fillna(pd.Timedelta(0))

    # Remove as colunas temporárias
    df_processed.drop(columns=['checkin_next_leg', 'id_leg_norm', 'activity_norm'], inplace=True, errors='ignore')

    print("Cálculos concluídos.")

    # --- 7. Preparar DataFrame para Saída (Ordem Corrigida e Novos Nomes) ---
    # Define as colunas desejadas no CSV de saída com seus nomes exatos e na ordem correta
    final_output_columns_pascal_case = [
        'Activity', 'Id_Leg', 'Checkin', 'Start', 'Dep', 'Arr', 'End', 'Checkout', 
        'Tempo Repouso', # Nova coluna total de Tempo Repouso
        'Tempo Repouso Diurno', 'Tempo Repouso Noturno',
        'Tempo Repouso Especial Diurno', 'Tempo Repouso Especial Noturno'
    ]

    # Mapeamento de nomes internos (snake_case) para nomes de saída (PascalCase)
    internal_to_output_name_map = {
        'activity': 'Activity', 'id_leg': 'Id_Leg', 'checkin': 'Checkin',
        'start': 'Start', 'end': 'End', 'dep': 'Dep', 'arr': 'Arr',
        'checkout': 'Checkout',
        'tempo_repouso_total': 'Tempo Repouso', # Mapeamento para a nova coluna total de Tempo Repouso
        'main_activity_day_total': 'Tempo Repouso Diurno', # Mapeia de generic para Tempo Repouso
        'main_activity_night_total': 'Tempo Repouso Noturno', # Mapeia de generic para Tempo Repouso
        'main_activity_special_day': 'Tempo Repouso Especial Diurno', # Mapeia de generic para Tempo Repouso
        'main_activity_special_night': 'Tempo Repouso Especial Noturno' # Mapeia de generic para Tempo Repouso
    }

    # Criar um DataFrame de saída vazio com as colunas na ordem desejada
    df_output = pd.DataFrame(columns=final_output_columns_pascal_case)

    # Preencher o DataFrame de saída com os dados processados
    for internal_col, output_col in internal_to_output_name_map.items():
        if internal_col in df_processed.columns:
            df_output[output_col] = df_processed[internal_col]
        else:
            # Se a coluna interna não existir, preenche com o valor padrão para o tipo
            if 'tempo' in internal_col or 'pagamento' in internal_col: # Assumindo que são Timedeltas
                df_output[output_col] = pd.Timedelta(0)
            elif 'date' in internal_col or 'time' in internal_col: # Assumindo que são Datetimes
                df_output[output_col] = pd.NaT
            else: # Outros tipos (strings, etc.)
                df_output[output_col] = '' # Ou np.nan, dependendo do que for mais apropriado

    # Debugging: Print dtypes before formatting
    print("\n--- dtypes of df_output before final formatting ---")
    print(df_output.dtypes)
    print("---------------------------------------------------\n")

    # Formatar colunas Timedelta para string 'HH:MM:SS' ou 'D days HH:MM:SS'
    timedelta_cols_for_format = [
        'Tempo Repouso', 
        'Tempo Repouso Diurno', 'Tempo Repouso Noturno',
        'Tempo Repouso Especial Diurno', 'Tempo Repouso Especial Noturno',
        'Pagamento Diurno', 'Pagamento Noturno',
        'Pagamento Especial Diurno', 'Pagamento Especial Noturno'
    ]
    for col in timedelta_cols_for_format:
        if col in df_output.columns:
            df_output[col] = df_output[col].apply(format_timedelta_to_hms)

    # Formatar APENAS colunas datetime para string 'YYYY-MM-DD HH:MM:SS'
    # ATENÇÃO: 'Dep' e 'Arr' são códigos de aeroporto e não devem ser formatados como datetime.
    datetime_cols_for_format = ['Checkin', 'Start', 'End', 'Checkout'] 
    for col in datetime_cols_for_format:
        if col in df_output.columns:
            df_output[col] = df_output[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    # --- IMPRIMIR AS PRIMEIRAS 5 LINHAS DO DATAFRAME FINAL ---
    print("\n--- Primeiras 5 linhas do DataFrame FINAL com colunas calculadas e formatadas ---")
    display_cols_example = [col for col in final_output_columns_pascal_case if col in df_output.columns]
    print(df_output[display_cols_example].head(5).to_string())
    print("---------------------------------------------------------------\n")

    # --- 8. Salvamento do Arquivo CSV de Saída ---
    # Preparar nome do arquivo de saída
    base_output_filename = gerar_nome_csv_saida_base(input_csv_path) 
    timestamp = datetime.now().strftime("%d%m%Y_%H%M%S") 
    
    # Insere o timestamp no nome do arquivo antes da extensão
    name_part, ext_part = os.path.splitext(base_output_filename)
    output_filename_with_timestamp = f"{name_part}_{timestamp}{ext_part}"
    
    output_file_path = os.path.join(output_dir, output_filename_with_timestamp)

    # Verificar se não há dados e exibir mensagem apropriada
    if df_processed.empty and not tipos_voo_data:
        messagebox.showinfo("Processamento Concluído", "Nenhuma linha foi processada, pois 'tipos_voo.json' está vazio ou não possui atividades para inclusão.\n\nO arquivo CSV será criado apenas com cabeçalhos.")
        print("Nenhuma linha foi processada, pois 'tipos_voo.json' está vazio ou não possui atividades para inclusão.")
        print("O arquivo CSV será criado apenas com cabeçalhos.\n")
    elif df_processed.empty:
        messagebox.showinfo("Processamento Concluído", "Nenhuma linha foi processada após a aplicação dos filtros.\n\nO arquivo CSV será criado apenas com cabeçalhos.")
        print("Nenhuma linha foi processada após a aplicação dos filtros.")
        print("O arquivo CSV será criado apenas com cabeçalhos.\n")

    # Salvar o arquivo CSV (mesmo que vazio, com apenas cabeçalhos)
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