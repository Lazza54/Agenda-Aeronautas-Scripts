# -*- coding: utf-8 -*-
"""
IMPORTA PDF DE ESCALA LATAM CREWTOPIA -> CSV (layout padrão PRIMEIRA_VERSAO)

Processa o texto extraído da nova escala LATAM CrewTopia gerando o formato esperado
com as colunas: Activity, Checkin, Start, Dep, Arr, End, Checkout, AcVer, DD, CAT, Crew.
"""

import os
import re
import warnings
from datetime import datetime, timedelta
import pandas as pd
import pdfplumber
import tkinter as tk
from tkinter import filedialog, messagebox

warnings.filterwarnings("ignore")

CSV_COLUMNS = ["Activity", "Checkin", "Start", "Dep", "Arr", "End", "Checkout", "AcVer", "DD", "CAT", "Crew"]

MONTHS_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

def selecionar_arquivo():
    env_pdf = os.environ.get("AERO_ESCALA_PDF")
    if env_pdf and os.path.isfile(env_pdf):
        return env_pdf

    root = tk.Tk()
    root.withdraw()
    caminho_pdf = filedialog.askopenfilename(
        title="Selecione o arquivo PDF da Escala LATAM CrewTopia",
        filetypes=[("Arquivos PDF", "*.pdf")]
    )
    root.destroy()
    return caminho_pdf

def extrair_texto_pdf(caminho_pdf):
    todas_linhas = []
    with pdfplumber.open(caminho_pdf) as pdf:
        page = pdf.pages[0]
        # Pega as bordas verticais que delimitam os dias (rects encostados na margem esquerda)
        rects = sorted([r for r in page.rects if r['x0'] < 10], key=lambda x: x['top'])
        
        if not rects:
            # Fallback se não encontrar os retângulos
            texto = page.extract_text(layout=True)
            return [l for l in texto.split('\n') if l.strip()]
            
        for r in rects:
            # Crop do dia inteiro
            crop = page.crop((0, r['top'], page.width, r['bottom']))
            texto = crop.extract_text(layout=True)
            if not texto: continue
            
            # Aplica o patch visual (reconstrução de voos deformados) neste dia específico
            words = crop.extract_words(keep_blank_chars=False)
            
            # Descobre qual é o dia através das palavras do PDF (margem esquerda)
            dia_atual = None
            day_words = [w for w in words if w['x0'] < 16 and w['text'].isdigit()]
            if day_words:
                day_str = ''.join([w['text'] for w in sorted(day_words, key=lambda x: x['x0'])])
                if len(day_str) >= 2:
                    # Procura o código do voo ou de outras atividades (ex: LA3350, DO, ASB, HSB) no crop
                    dia_atual = int(day_str[:2])
            
            for w in words:
                clean_w = w['text'].encode('ascii', 'ignore').decode('ascii').strip()
                m = re.search(r'^(LA\s*\d{4}|OFT_J|LOFT_J|DO|ASB|HSB|OFF|DOF|DR|CMA)$', clean_w)
                if m:
                    flight_raw = m.group(1)
                    flight_clean = 'LOFT_J J' if 'OFT' in flight_raw else flight_raw
                    # Agrupa as palavras espremidas
                    box = [o for o in words if w['top']-5 < o['top'] < w['bottom']+15 and w['x1'] < o['x0'] < w['x1']+100]
                    if box:
                        box = sorted(box, key=lambda x: x['top'])
                        groups = []
                        for b in box:
                            if not groups:
                                groups.append([b])
                            else:
                                if b['top'] - groups[-1][0]['top'] < 8:
                                    groups[-1].append(b)
                                else:
                                    groups.append([b])
                        if len(groups) >= 2:
                            dep_str = ''.join([x['text'] for x in sorted(groups[0], key=lambda x: x['x0']) if not '(' in x['text']])
                            arr_str = ''.join([x['text'] for x in sorted(groups[1], key=lambda x: x['x0']) if not '(' in x['text']])
                            if re.search(r'^[A-Z]{3}\d{2}:\d{2}', dep_str) and re.search(r'^[A-Z]{3}\d{2}:\d{2}', arr_str):
                                flight_regex = flight_raw.replace(' ', r'\s*')
                                padrao = r'(?m)^([ \t]*(?:\d{2})?[ \t]*)?.*?' + flight_regex + r'.*?$'
                                def repl(match):
                                    linha_inteira = match.group(0)
                                    prefix = match.group(1) or ""
                                    return f"{prefix}{flight_clean} {dep_str[:3]} {dep_str[3:8]}\n{prefix}{arr_str[:3]} {arr_str[3:8]}"
                                texto = re.sub(padrao, repl, texto)
            
            linhas_dia = [l for l in texto.split('\n') if l.strip()]
            
            # Adiciona os prefixos de data para facilitar o parse tradicional
            if dia_atual:
                for i in range(len(linhas_dia)):
                    l = linhas_dia[i]
                    if not re.search(r'^\s*(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*)?\d{2}', l):
                        linhas_dia[i] = f"{dia_atual:02d} {l.strip()}"
                        
            todas_linhas.extend(linhas_dia)
            
    return todas_linhas

def parse_crewtopia(linhas, caminho_pdf):
    dados = []
    target_start = None
    target_end = None
    
    # Tentativa de extrair data base e período do nome do arquivo
    m_periodo = re.search(r'_(\d{2})(\d{2})(\d{4})_(\d{2})(\d{2})(\d{4})', os.path.basename(caminho_pdf))
    if m_periodo:
        d1, m1, y1 = int(m_periodo.group(1)), int(m_periodo.group(2)), int(m_periodo.group(3))
        d2, m2, y2 = int(m_periodo.group(4)), int(m_periodo.group(5)), int(m_periodo.group(6))
        target_start = datetime(y1, m1, d1)
        target_end = datetime(y2, m2, d2)
    
    # Inicia a data de leitura no mês anterior para que os voos "órfãos" do início do PDF (maio)
    # não ganhem a data de junho de carona antes do identificador oficial do dia 01.
    if target_start:
        current_date = target_start - pd.Timedelta(days=15)
    else:
        current_date = datetime.now()
        
    last_day = None
    
    current_checkin = ""
    current_checkout = ""
    temp_leg = {}
    prev_clean_linha = ""
    
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
            
        clean_linha = re.sub(r'[^\x00-\x7F\xC0-\xFF]+', '', linha)
        
        # Pega números de dia isolados na linha (ex: "31")
        m_only_day = re.search(r'^\s*(\d{2})\s*$', clean_linha)
        if m_only_day:
            day = int(m_only_day.group(1))
            if current_date:
                # Se o dia for muito maior que o anterior, pode ser recuo de mês, mas
                # geralmente apenas atualizamos o dia no mês atual, a não ser que vire.
                if last_day is not None and day < last_day and last_day >= 28:
                    current_date = current_date + pd.DateOffset(months=1)
                current_date = current_date.replace(day=day)
                last_day = day

        # Apresentação (Checkin)
        m_apres = re.search(r'Apresenta..o:\s*(\d{2}:\d{2})', clean_linha, re.IGNORECASE)
        if m_apres:
            current_checkin = m_apres.group(1)
            
            # REGRA CRONOLÓGICA (Previne erro de dia omitido após jornada que cruza meia-noite):
            # Se a apresentação for num horário que parece "antes" do término da última jornada, 
            # significa que é obrigatoriamente no dia seguinte (o dia não foi impresso no PDF).
            if dados and current_date:
                last_flight = dados[-1]
                chk_out_to_use = last_flight.get('Checkout_time') or last_flight.get('End_time')
                if chk_out_to_use:
                    try:
                        chk_dt = datetime.strptime(chk_out_to_use, '%H:%M')
                        new_chk_dt = datetime.strptime(current_checkin, '%H:%M')
                        
                        # Data do checkout do último voo
                        checkout_date = last_flight['Date_start']
                        if last_flight.get('Start_time'):
                            last_start_dt = datetime.strptime(last_flight['Start_time'], '%H:%M')
                            if chk_dt.time() < last_start_dt.time():
                                checkout_date += pd.Timedelta(days=1)
                                
                        # Compara cronologicamente
                        new_chk_full = datetime.combine(current_date.date(), new_chk_dt.time())
                        last_chk_full = datetime.combine(checkout_date.date(), chk_dt.time())
                        
                        # Se a nova apresentação (na data atual) for anterior ao checkout anterior,
                        # ou seja impossivelmente próxima (ex: menos de 2 horas de repouso),
                        # então com certeza já estamos no dia seguinte!
                        if new_chk_full < last_chk_full + pd.Timedelta(hours=2):
                            current_date += pd.Timedelta(days=1)
                            last_day = current_date.day
                    except ValueError:
                        pass
                        
            # REGRA DO MADRUGADÃO / VIRADA DE MÊS:
            # Se a data atual for o último dia do mês anterior ao alvo, a nova apresentação 
            # já pertence ao dia 01 do mês alvo.
            if target_start and current_date:
                ultimo_dia_mes_ant = target_start - pd.Timedelta(days=1)
                if current_date.date() == ultimo_dia_mes_ant.date():
                    current_date = target_start
                    last_day = 1
            continue
            
        # Término da Jornada (Checkout)
        m_term = re.search(r'T.rminodaJornada:\s*(\d{2}:\d{2})', clean_linha, re.IGNORECASE)
        if m_term:
            current_checkout = m_term.group(1)
            if dados:
                dados[-1]['Checkout_time'] = current_checkout
            continue

        # Identifica Voos e Atividades (LA3350, DO, OFF, DOF, ASB, etc)
        m_act = re.search(r'^(?:\s*(\d{2})\s+)?(?:.*?\s+)?(LA\s*\d{4}|DO|OFF|DOF|ASB|HSB|DR|CMA|LOFT_[A-Z0-9_ ]+)\s+([A-Z]{3})\s+(\d{2}:\d{2})', clean_linha)
        if m_act:
            day_str = m_act.group(1)
            act = m_act.group(2)
            if act.startswith('LA'): 
                act = act.replace(' ', '')
                if 'extra' in clean_linha.lower():
                    act = f"{act} (Extra)"
            dep = m_act.group(3)
            start_time = m_act.group(4)
            
            if day_str:
                day = int(day_str)
                if last_day is None and target_start:
                    if day > 20 and target_start.day < 10:
                        mes = target_start.month - 1
                        ano = target_start.year
                        if mes == 0:
                            mes = 12
                            ano -= 1
                        current_date = datetime(ano, mes, day)
                    else:
                        current_date = datetime(target_start.year, target_start.month, day)
                elif last_day is not None:
                    if day < last_day and last_day >= 28:
                        mes = current_date.month + 1
                        ano = current_date.year
                        if mes == 13:
                            mes = 1
                            ano += 1
                        current_date = datetime(ano, mes, day)
                    else:
                        try:
                            current_date = current_date.replace(day=day)
                        except ValueError:
                            pass
                last_day = day
            
            temp_leg = {
                'Activity': act,
                'Dep': dep,
                'Start_time': start_time,
                'Date_start': current_date,
                'Checkin_time': current_checkin
            }
            current_checkin = ""
            
            continue
            
        # Chegada do Voo
        m_arr = re.search(r'^(?:\s*\d{2}\s+)?(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+)?(?:\d{2}\s+)?(?:Extra\s+)?([A-Z]{3})\s+(\d{2}:\d{2})', clean_linha, re.IGNORECASE)
        if m_arr:
            if temp_leg and 'Arr' not in temp_leg:
                if 'extra' in clean_linha.lower() and str(temp_leg.get('Activity', '')).startswith('LA') and '(Extra)' not in str(temp_leg.get('Activity', '')):
                    temp_leg['Activity'] = f"{temp_leg['Activity']} (Extra)"
                temp_leg['Arr'] = m_arr.group(1)
                temp_leg['End_time'] = m_arr.group(2)
                dados.append(temp_leg.copy())
                temp_leg = {}
            elif not temp_leg and 'extra' in clean_linha.lower() and dados:
                if str(dados[-1].get('Activity', '')).startswith('LA') and '(Extra)' not in str(dados[-1].get('Activity', '')):
                    dados[-1]['Activity'] = f"{dados[-1]['Activity']} (Extra)"
            
        prev_clean_linha = clean_linha
        continue

    # Pós-processamento de continuidade de atividades (ex: ASB colado em Voo ou gaps < 12h)
    def gap_hours(t1_str, t2_str):
        try:
            t1 = pd.to_datetime(t1_str, format="%H:%M")
            t2 = pd.to_datetime(t2_str, format="%H:%M")
            diff = (t2 - t1).total_seconds() / 3600.0
            return diff if diff >= 0 else diff + 24.0
        except:
            return 999

    for i in range(1, len(dados)):
        prev = dados[i-1]
        curr = dados[i]
        
        chk = curr.get('Checkin_time') or curr.get('Start_time')
        if prev.get('End_time') and chk:
            is_checkin_equal_start = (curr.get('Checkin_time') == curr.get('Start_time'))
            if is_checkin_equal_start and gap_hours(prev['End_time'], chk) < 12:
                # 1. Alinhar a data da atividade solta para pertencer ao mesmo dia cronológico
                if curr.get('Date_start') and prev.get('Date_start'):
                    prev_end_date = curr['Date_start']
                    if pd.to_datetime(chk, format="%H:%M") < pd.to_datetime(prev['End_time'], format="%H:%M"):
                        prev_end_date -= pd.Timedelta(days=1)
                        
                    if prev.get('Start_time', '') <= prev['End_time']:
                        prev['Date_start'] = prev_end_date
                    else:
                        prev['Date_start'] = prev_end_date - pd.Timedelta(days=1)
                
                # 2. Herdar o horário de início da primeira atividade para a apresentação da segunda
                if prev.get('Start_time'):
                    curr['Checkin_time'] = prev['Start_time']
                    prev['Checkin_time'] = prev['Start_time']

    # Preencher dias vazios no período
    if target_start and target_end and dados:
        dias_presentes = set(row.get('Date_start').date() for row in dados if row.get('Date_start'))
        dias_totais = pd.date_range(start=target_start, end=target_end)
        for dt in dias_totais:
            if dt.date() not in dias_presentes:
                dados.append({
                    'Activity': '',
                    'Dep': '',
                    'Start_time': '',
                    'Date_start': dt.to_pydatetime(),
                    'Checkin_time': ''
                })
        # Reordena para manter a cronologia correta com os dias em branco no meio
        dados = sorted(dados, key=lambda x: (x.get('Date_start') or datetime.max, x.get('Start_time') or '25:00'))

    processed_data = []
    
    # Filtro de período (descarta dias do mês anterior ou posterior caso existam na extração)
    if target_start and target_end:
        dados = [row for row in dados if row.get('Date_start') and target_start <= row['Date_start'] <= target_end]
    elif target_start:
        dados = [row for row in dados if row.get('Date_start') and row['Date_start'] >= target_start]
        
    for row in dados:
        dt_start = row.get('Date_start')
        
        if not row.get('Activity'):
            # É uma linha vazia gerada para cobrir um dia sem atividade
            processed_data.append({
                'Activity': '',
                'Checkin': '',
                'Start': dt_start.strftime('%d/%m/%Y') if dt_start else '',
                'Dep': '',
                'Arr': '',
                'End': '',
                'Checkout': '',
                'AcVer': "",
                'DD': "",
                'CAT': "",
                'Crew': ""
            })
            continue
            
        def format_dt(time_str):
            if not time_str: return ""
            if not dt_start: return time_str # Fallback para retornar só a hora se não houver data
            return f"{dt_start.strftime('%d/%m/%Y')} {time_str}"

        end_time_str = row.get('End_time', '')
        start_time_str = row.get('Start_time', '')
        
        dt_end_formated = format_dt(end_time_str)
        if start_time_str and end_time_str and end_time_str < start_time_str and dt_start:
             dt_end = dt_start + timedelta(days=1)
             dt_end_formated = f"{dt_end.strftime('%d/%m/%Y')} {end_time_str}"
             
        chk_out = format_dt(row.get('Checkout_time', ''))
        # Fix checkout day wrap
        if row.get('Checkout_time', '') and start_time_str and row.get('Checkout_time', '') < start_time_str and dt_start:
             dt_chk = dt_start + timedelta(days=1)
             chk_out = f"{dt_chk.strftime('%d/%m/%Y')} {row.get('Checkout_time', '')}"

        start_formatted = format_dt(start_time_str)
        checkin_formatted = format_dt(row.get('Checkin_time', ''))
        
        is_la_flight = str(row.get('Activity', '')).strip().upper().startswith('LA')

        if not is_la_flight:
            if not checkin_formatted:
                checkin_formatted = start_formatted
            if not chk_out:
                chk_out = dt_end_formated

        processed_data.append({
            'Activity': row.get('Activity', ''),
            'Checkin': checkin_formatted,
            'Start': start_formatted,
            'Dep': row.get('Dep', ''),
            'Arr': row.get('Arr', ''),
            'End': dt_end_formated,
            'Checkout': chk_out,
            'AcVer': "",
            'DD': "",
            'CAT': "",
            'Crew': ""
        })

    return processed_data


def main():
    print("Iniciando Importador LATAM CrewTopia...")
    caminho_pdf = selecionar_arquivo()
    
    if not caminho_pdf:
        print("Operação cancelada.")
        return

    print(f"Lendo arquivo: {caminho_pdf}")
    linhas = extrair_texto_pdf(caminho_pdf)
    
    if not linhas:
        print("Erro: Nenhum texto pôde ser extraído do PDF.")
        return
        
    print("Analisando estrutura de voos...")
    dados = parse_crewtopia(linhas, caminho_pdf)
    
    if not dados:
        print("Erro: Nenhum voo reconhecido.")
        return
        
    df = pd.DataFrame(dados)
    df = df[CSV_COLUMNS]

    nome_base = os.path.splitext(os.path.basename(caminho_pdf))[0]
    data_proc = datetime.now().strftime("%d%m%Y_%H%M%S")
    
    # O arquivo deve ser obrigatoriamente gerado e armazenado no mesmo diretório do arquivo fonte
    pasta_destino = os.path.dirname(caminho_pdf)

    nome_arquivo_saida = f"{nome_base}_PRIMEIRA_VERSAO_{data_proc}.csv"
    caminho_saida = os.path.join(pasta_destino, nome_arquivo_saida)
    
    df.to_csv(caminho_saida, index=False, sep=";", encoding="latin1")
    print(f"\n[SUCESSO] Arquivo gerado: {caminho_saida}")

if __name__ == "__main__":
    main()
