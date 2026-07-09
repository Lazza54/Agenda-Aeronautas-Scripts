import os
import re
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, timedelta
import pandas as pd

# Taxas de pagamento (ajuste conforme a convenção/collectivo aplicável)
TAXA_DIURNO = 1.0
TAXA_NOTURNO = 1.2
TAXA_ESPECIAL_DIURNO = 1.5
TAXA_ESPECIAL_NOTURNO = 1.8

SUFIXO_SAIDA = '_processado'

COLUNAS_SAIDA = [
    'Activity', 'Id_Leg', 'Checkin', 'Start', 'Dep', 'Arr', 'End', 'Checkout',
    'Tempo Jornada', 'Tempo Jornada Diurno', 'Tempo Jornada Noturno',
    'Tempo Jornada Especial Diurno', 'Tempo Jornada Especial Noturno',
    'Pagamento Diurno', 'Pagamento Noturno',
    'Pagamento Especial Diurno', 'Pagamento Especial Noturno'
]


def determinar_diretorio_e_arquivo():
    """Tenta pegar via ambiente ou abre a janela de seleção de arquivos do Tkinter e retorna o caminho escolhido."""
    env_csv = os.environ.get("AERO_ESCALA_CSV")
    if env_csv and os.path.exists(env_csv):
        return env_csv

    import sys
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        return sys.argv[1]

    root = tk.Tk()
    root.withdraw()
    arquivo = filedialog.askopenfilename(
        title="Selecione o arquivo CSV de entrada",
        filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")]
    )
    root.destroy()
    return arquivo


def parse_hora(valor):
    """Converte um valor em objeto time. Retorna None para valores vazios/inválidos."""
    if pd.isna(valor) or str(valor).strip() == '':
        return None
    s = str(valor).strip()
    # Formatos de data/hora completos e apenas hora
    formatos = (
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
        '%H:%M:%S', '%H:%M'
    )
    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def obter_data_base(row):
    """Tenta obter a data base da coluna 'Date'; caso contrário, usa a data atual."""
    if 'Date' in row.index:
        try:
            return pd.to_datetime(row['Date']).date()
        except Exception:
            pass
    return datetime.today().date()


def ajustar_datetime(dt_anterior, hora, data_base):
    """Combina data e hora, adicionando dias quando necessário para manter a sequência."""
    if hora is None:
        return None
    dt = datetime.combine(data_base, hora)
    if dt_anterior is not None and dt < dt_anterior:
        while dt < dt_anterior:
            dt += timedelta(days=1)
    return dt


def calcular_periodos(inicio, fim):
    """Calcula total, diurno, noturno e períodos especiais (fins de semana)."""
    if inicio is None or fim is None or fim <= inicio:
        return timedelta(0), timedelta(0), timedelta(0), timedelta(0), timedelta(0)

    total = fim - inicio
    diurno = timedelta(0)
    noturno = timedelta(0)
    especial_diurno = timedelta(0)
    especial_noturno = timedelta(0)

    atual = inicio
    while atual < fim:
        proximo = min(atual + timedelta(minutes=1), fim)
        hora = atual.hour
        eh_diurno = 6 <= hora < 22
        eh_especial = atual.weekday() >= 5  # sábado ou domingo
        delta = proximo - atual

        if eh_diurno:
            diurno += delta
            if eh_especial:
                especial_diurno += delta
        else:
            noturno += delta
            if eh_especial:
                especial_noturno += delta

        atual = proximo

    return total, diurno, noturno, especial_diurno, especial_noturno


def formatar_timedelta(td):
    """Formata timedelta como HH:MM."""
    if td is None or td == timedelta(0):
        return '00:00'
    total_segundos = int(td.total_seconds())
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    return f"{horas:02d}:{minutos:02d}"


def calcular_pagamento(td, taxa):
    """Calcula o pagamento em horas com base na taxa informada."""
    if td is None or td == timedelta(0):
        return '0.00'
    horas = td.total_seconds() / 3600
    return f"{horas * taxa:.2f}"


def processar_dados(df):
    """Processa o DataFrame aplicando busca retroativa e regras de exibição."""
    # Garante que todas as colunas de entrada esperadas existam
    for col in ['Activity', 'Id_Leg', 'Checkin', 'Start', 'Dep', 'Arr', 'End', 'Checkout']:
        if col not in df.columns:
            df[col] = ''

    n = len(df)
    dt_checkin = [None] * n
    dt_checkout = [None] * n
    checkin_substituto = [None] * n  # para linhas '-F' com busca retroativa

    last_checkin_dt = None
    last_checkin_str = None

    # Primeira passada: parse de horários e busca retroativa do Checkin '-I' anterior
    for i in range(n):
        row = df.iloc[i]
        id_leg = str(row.get('Id_Leg', '')).strip()
        data_base = obter_data_base(row)

        hora_checkin = parse_hora(row.get('Checkin', ''))
        current_dt = ajustar_datetime(None, hora_checkin, data_base)

        # Se for -F, herda o check-in do -I anterior ANTES de calcular o resto da linha
        if id_leg == '-F' and last_checkin_dt is not None:
            current_dt = last_checkin_dt
            checkin_substituto[i] = last_checkin_str
            
        dt_checkin[i] = current_dt

        hora_start = parse_hora(row.get('Start', ''))
        dt_start = ajustar_datetime(current_dt, hora_start, data_base)
        if dt_start: current_dt = dt_start

        hora_dep = parse_hora(row.get('Dep', ''))
        dt_dep = ajustar_datetime(current_dt, hora_dep, data_base)
        if dt_dep: current_dt = dt_dep

        hora_arr = parse_hora(row.get('Arr', ''))
        dt_arr = ajustar_datetime(current_dt, hora_arr, data_base)
        if dt_arr: current_dt = dt_arr

        hora_end = parse_hora(row.get('End', ''))
        dt_end = ajustar_datetime(current_dt, hora_end, data_base)
        if dt_end: current_dt = dt_end

        hora_checkout = parse_hora(row.get('Checkout', ''))
        dt_checkout[i] = ajustar_datetime(current_dt, hora_checkout, data_base)

        if id_leg == '-I':
            last_checkin_dt = dt_checkin[i]
            last_checkin_str = row.get('Checkin', '')

    # Segunda passada: monta as linhas de saída
    linhas = []
    for i in range(n):
        row = df.iloc[i]
        id_leg = str(row.get('Id_Leg', '')).strip()

        out = {}
        for col in ['Activity', 'Id_Leg', 'Start', 'Dep', 'Arr', 'End', 'Checkout']:
            out[col] = row.get(col, '')

        # Checkin: usa o substituto da busca retroativa quando '-F'
        if checkin_substituto[i] is not None:
            out['Checkin'] = checkin_substituto[i]
        else:
            out['Checkin'] = row.get('Checkin', '')

        # Regra de Exibição Seletiva: cálculos apenas nas linhas '-IF' e '-F'
        if id_leg in ('-IF', '-F'):
            total, diurno, noturno, esp_d, esp_n = calcular_periodos(
                dt_checkin[i], dt_checkout[i]
            )

            out['Tempo Jornada'] = formatar_timedelta(total)
            out['Tempo Jornada Diurno'] = formatar_timedelta(diurno)
            out['Tempo Jornada Noturno'] = formatar_timedelta(noturno)
            out['Tempo Jornada Especial Diurno'] = formatar_timedelta(esp_d)
            out['Tempo Jornada Especial Noturno'] = formatar_timedelta(esp_n)

            out['Pagamento Diurno'] = calcular_pagamento(diurno, TAXA_DIURNO)
            out['Pagamento Noturno'] = calcular_pagamento(noturno, TAXA_NOTURNO)
            out['Pagamento Especial Diurno'] = calcular_pagamento(esp_d, TAXA_ESPECIAL_DIURNO)
            out['Pagamento Especial Noturno'] = calcular_pagamento(esp_n, TAXA_ESPECIAL_NOTURNO)
        else:
            out['Tempo Jornada'] = ''
            out['Tempo Jornada Diurno'] = ''
            out['Tempo Jornada Noturno'] = ''
            out['Tempo Jornada Especial Diurno'] = ''
            out['Tempo Jornada Especial Noturno'] = ''
            out['Pagamento Diurno'] = ''
            out['Pagamento Noturno'] = ''
            out['Pagamento Especial Diurno'] = ''
            out['Pagamento Especial Noturno'] = ''

        linhas.append(out)

    df_out = pd.DataFrame(linhas, columns=COLUNAS_SAIDA)
    return df_out


def main():
    # Obtém o arquivo de entrada via janela do Tkinter, sem depender de sys.argv
    arquivo_entrada = determinar_diretorio_e_arquivo()
    if not arquivo_entrada:
        print("Nenhum arquivo foi selecionado. O script será encerrado.")
        return

    try:
        df = pd.read_csv(arquivo_entrada)
    except Exception as e:
        print(f"Erro ao ler o arquivo '{arquivo_entrada}': {e}")
        return

    df_out = processar_dados(df)

    # Salva no mesmo diretório formatando o nome de saída
    diretorio = os.path.dirname(os.path.abspath(arquivo_entrada))
    nome_base, ext = os.path.splitext(os.path.basename(arquivo_entrada))
    timestamp = datetime.now().strftime('%d%m%Y_%H%M%S')
    
    if 'QUARTA_VERSAO' in nome_base:
        nome_base_novo = re.sub(r'QUARTA_VERSAO.*', f'TEMPO_JORNADA_{timestamp}', nome_base)
        nome_saida = f"{nome_base_novo}{ext}"
    else:
        # Fallback caso não tenha a tag no nome
        nome_saida = f"{nome_base}_TEMPO_JORNADA_{timestamp}{ext}"
        
    caminho_saida = os.path.join(diretorio, nome_saida)

    df_out.to_csv(caminho_saida, index=False)
    print(f"Arquivo processado salvo em: {caminho_saida}")


if __name__ == '__main__':
    main()