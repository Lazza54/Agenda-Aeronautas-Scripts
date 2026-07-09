#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gerador de Relatório Comparativo de Escalas (Planejada vs Executada)
Versão 2.0: Unificando 10 relatórios e comparando todas as colunas.
"""

import pandas as pd
from datetime import datetime
import os
import sys
import re
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

MODO_AUTOMATICO = bool(os.environ.get("AERO_CSV_PLANEJADA")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
except ImportError:
    print("ERRO: Biblioteca 'reportlab' não encontrada!")
    sys.exit(1)

SUFIXOS_RELATORIOS = [
    "APRESENTACAO",
    "TEMPO_CORTE",
    "OPERACAO",
    "TEMPO_SOLO",
    "JORNADA",
    "REPOUSO_EXTRA",
    "RESERVA",
    "PLANTAO",
    "TREINAMENTO"
]

def selecionar_pasta():
    root = tk.Tk()
    root.withdraw()
    pasta = filedialog.askdirectory(title="Selecione a PASTA onde estão os arquivos Planejados e Executados")
    if not pasta: return None
    return pasta

def normalize_col(df):
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df

def unificar_csvs_da_pasta(caminho_pasta_ou_arquivo, tipo):
    """
    Busca os arquivos começando com 'escala_{tipo}_'.
    Se caminho_pasta_ou_arquivo for um arquivo, usa ele como base.
    """
    p = Path(caminho_pasta_ou_arquivo)
    if not p.exists():
        return None, None, {}
        
    if p.is_file():
        arquivo_base = p
        pasta = p.parent
    else:
        pasta = p
        todas_quartas = list(pasta.glob("*_QUARTA_VERSAO*.csv"))
        arquivos_quarta = [f for f in todas_quartas if f.name.lower().startswith(f"escala_{tipo}_")]
        if not arquivos_quarta:
            return None, None, {}
        arquivo_base = arquivos_quarta[0]
    try:
        df_base = pd.read_csv(arquivo_base)
    except:
        df_base = pd.read_csv(arquivo_base, encoding='latin1')
        
    df_base = normalize_col(df_base)
    
    chaves_merge = ['id_leg', 'activity']
    colunas_por_csv = {}
    
    for sufixo in SUFIXOS_RELATORIOS:
        todos_rel = list(pasta.glob(f"*{sufixo}*.csv"))
        arquivos_relatorio = [f for f in todos_rel if f.name.lower().startswith(f"escala_{tipo}_")]
        
        if arquivos_relatorio:
            try:
                df_rel = pd.read_csv(arquivos_relatorio[0])
            except:
                df_rel = pd.read_csv(arquivos_relatorio[0], encoding='latin1')
                
            df_rel = normalize_col(df_rel)
            
            chaves_comuns = [c for c in chaves_merge if c in df_rel.columns and c in df_base.columns]
            
            if not chaves_comuns:
                continue
                
            novas_colunas = [col for col in df_rel.columns if col not in df_base.columns]
            colunas_por_csv[sufixo] = novas_colunas
            
            cols_to_use = chaves_comuns + novas_colunas
            df_rel = df_rel.drop_duplicates(subset=chaves_comuns)
            
            df_base = pd.merge(df_base, df_rel[cols_to_use], on=chaves_comuns, how='left')
            
    return df_base, arquivo_base.name, colunas_por_csv

def extrair_mes_ano_nome(nome_arquivo):
    m = re.search(r"^escala_[pePE]_(.+?)_([A-Z]{3,4})_+(\d+)?", nome_arquivo)
    
    if m:
        nome_bruto = m.group(1)
        registro = m.group(3)
        nome = nome_bruto.replace("_", " ").title()
        nome_cabecalho = f"{nome} - Reg: {registro}" if registro else nome
        nome_arquivo_pdf = f"{nome}_{registro}" if registro else nome
    else:
        m2 = re.search(r"^escala_[pePE]_(.+?)_([A-Z]{3,4})", nome_arquivo)
        nome = m2.group(1).replace("_", " ").title() if m2 else "Aeronauta"
        nome_cabecalho = nome
        nome_arquivo_pdf = nome
        
    m_data = re.search(r"(\d{2})(\d{2})(\d{4})_\d{8}", nome_arquivo)
    mes_ano = f"{m_data.group(2)}{m_data.group(3)}" if m_data else ""
    mes_ano_formatado = f"{m_data.group(2)}/{m_data.group(3)}" if m_data else ""
    return nome_arquivo_pdf, nome_cabecalho, mes_ano, mes_ano_formatado

def alinhar_e_comparar(df_p, df_e, cols_p, cols_e):
    df_p = df_p.fillna('')
    df_e = df_e.fillna('')
    
    date_col = 'date_start' if 'date_start' in df_p.columns else 'data' if 'data' in df_p.columns else None
    
    if date_col and date_col in df_e.columns:
        df_p['date_clean'] = pd.to_datetime(df_p[date_col], format='%d/%m/%Y', errors='coerce').dt.strftime('%d/%m/%Y')
        df_e['date_clean'] = pd.to_datetime(df_e[date_col], format='%d/%m/%Y', errors='coerce').dt.strftime('%d/%m/%Y')
        
        df_p['dia_idx'] = df_p.groupby('date_clean').cumcount()
        df_e['dia_idx'] = df_e.groupby('date_clean').cumcount()
        
        df_merged = pd.merge(
            df_p.assign(orig='p'), 
            df_e.assign(orig='e'), 
            on=['date_clean', 'dia_idx'], 
            how='outer', 
            suffixes=('_p', '_e')
        ).sort_values(['date_clean', 'dia_idx'])
    else:
        df_p['idx'] = range(len(df_p))
        df_e['idx'] = range(len(df_e))
        df_merged = pd.merge(df_p, df_e, on='idx', how='outer', suffixes=('_p', '_e'))
        
    resultado = []
    
    cols_map = {}
    for sufixo in SUFIXOS_RELATORIOS:
        c_p = cols_p.get(sufixo, [])
        c_e = cols_e.get(sufixo, [])
        union = []
        for c in c_p + c_e:
            if "pagamento" in c.lower():
                continue
            if c not in union:
                union.append(c)
        cols_map[sufixo] = union
        
    for idx, row in df_merged.iterrows():
        dados_p = {}
        dados_e = {}
        tabelas_por_sufixo = {}
        
        orig_p = row.get('orig_p', 'p' if pd.notna(row.get('activity_p')) and str(row.get('activity_p')) != 'nan' else None)
        orig_e = row.get('orig_e', 'e' if pd.notna(row.get('activity_e')) and str(row.get('activity_e')) != 'nan' else None)
        
        for sufixo, cols in cols_map.items():
            if not cols: continue
            
            table_rows = []
            has_any_value = False
            for col in cols:
                val_p = str(row.get(f"{col}_p", "")).replace('.0', '')
                val_e = str(row.get(f"{col}_e", "")).replace('.0', '')
                if val_p == "nan": val_p = ""
                if val_e == "nan": val_e = ""
                
                def formatar_dias_em_horas(val):
                    if "day" in str(val).lower():
                        try:
                            td = pd.to_timedelta(val)
                            ts = int(td.total_seconds())
                            h = ts // 3600
                            m = (ts % 3600) // 60
                            s = ts % 60
                            if s > 0:
                                return f"{h:02d}:{m:02d}:{s:02d}"
                            return f"{h:02d}:{m:02d}"
                        except:
                            pass
                    return val

                val_p = formatar_dias_em_horas(val_p)
                val_e = formatar_dias_em_horas(val_e)

                if val_p or val_e:
                    has_any_value = True
                    
                diff_str = ""
                if val_p and val_e and ":" in val_p and ":" in val_e:
                    try:
                        def parse_to_sec(val):
                            if "days" not in val and len(val.split(":")) == 2:
                                val = val + ":00"
                            return int(pd.to_timedelta(val).total_seconds())

                        sec_p = parse_to_sec(val_p)
                        sec_e = parse_to_sec(val_e)
                        
                        diff_sec = abs(sec_p - sec_e)
                        sinal = "-" if sec_e < sec_p else ""
                        
                        dh = diff_sec // 3600
                        dm = (diff_sec % 3600) // 60
                        ds = diff_sec % 60
                        
                        if ds > 0:
                            diff_str = f"{sinal}{dh:02d}:{dm:02d}:{ds:02d}"
                        else:
                            diff_str = f"{sinal}{dh:02d}:{dm:02d}"
                    except:
                        if val_p != val_e: diff_str = "SIM"
                elif val_p != val_e:
                    if not val_e and ":" in val_p:
                        diff_str = "00:00"
                    else:
                        diff_str = "SIM"
                        
                if val_p.endswith(":00") and val_p.count(":") == 2:
                    val_p = val_p[:-3]
                if val_e.endswith(":00") and val_e.count(":") == 2:
                    val_e = val_e[:-3]
                    
                col_title = col.replace('_', ' ').title()
                table_rows.append([col_title, val_p, val_e, diff_str])
                
            if has_any_value:
                tabelas_por_sufixo[sufixo] = table_rows
                
        # preencher dados_p e dados_e basicos para cabecalho
        for c in ['activity', 'checkin', 'start_time', 'start', 'end_time', 'end', 'checkout']:
            dados_p[c] = str(row.get(f"{c}_p", "")).replace('nan', '')
            dados_e[c] = str(row.get(f"{c}_e", "")).replace('nan', '')
            
        # Pegar a data
        data_p = row.get(f"{date_col}_p", "") if date_col else ""
        if not data_p or str(data_p).lower() == 'nan':
            for c_name in ['start_p', 'checkin_p', 'start_time_p']:
                val = str(row.get(c_name, ''))
                if val and val.lower() != 'nan' and ' ' in val:
                    data_p = val.split(' ')[0]
                    break
                    
        data_e = row.get(f"{date_col}_e", "") if date_col else ""
        if not data_e or str(data_e).lower() == 'nan':
            for c_name in ['start_e', 'checkin_e', 'start_time_e']:
                val = str(row.get(c_name, ''))
                if val and val.lower() != 'nan' and ' ' in val:
                    data_e = val.split(' ')[0]
                    break
                    
        dados_p['date_start'] = str(data_p).replace('nan', '')
        dados_e['date_start'] = str(data_e).replace('nan', '')
                
        resultado.append({
            'p': dados_p,
            'e': dados_e,
            'tabelas': tabelas_por_sufixo,
            'apenas_em_p': orig_p and not orig_e,
            'apenas_em_e': orig_e and not orig_p
        })
        
    return resultado

def gerar_pdf(resultado, nome_aeronauta, mes_ano_formatado, pdf_path):
    from reportlab.platypus import Table, TableStyle
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=1, fontSize=16, spaceAfter=20)
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontSize=12, alignment=1, spaceAfter=20)
    
    text_style_p = ParagraphStyle('TextP', parent=styles['Normal'], fontSize=9, textColor=colors.black, leading=12)
    text_style_e = ParagraphStyle('TextE', parent=styles['Normal'], fontSize=9, textColor=colors.black, leading=12)
    text_style_nodiff = ParagraphStyle('NoDiff', parent=styles['Normal'], fontSize=9, textColor=colors.gray, spaceAfter=15, leading=12)
    
    elements = []
    
    elements.append(Paragraph(f"RELATÓRIO COMPARATIVO DE ESCALAS (P vs E)", title_style))
    elements.append(Paragraph(f"<b>Aeronauta:</b> {nome_aeronauta} &nbsp;&nbsp;&nbsp; <b>Mês/Ano:</b> {mes_ano_formatado}", header_style))
    
    for item in resultado:
        p_act = item['p'].get('activity', '')
        p_date = item['p'].get('date_start', item['p'].get('data', ''))
        e_act = item['e'].get('activity', '')
        e_date = item['e'].get('date_start', item['e'].get('data', ''))
        
        p_desc = f"[P] Data: {p_date} | Act: {p_act}"
        e_desc = f"[E] Data: {e_date} | Act: {e_act}"
        
        if item['apenas_em_p']:
            e_desc = "[E] [NÃO EXECUTADO]"
        if item['apenas_em_e']:
            p_desc = "[P] [NÃO PLANEJADO - EXTRA]"
            
        elements.append(Paragraph(p_desc, text_style_p))
        elements.append(Paragraph(e_desc, text_style_e))
        
        tabelas = item.get('tabelas', {})
        if tabelas:
            for sufixo, rows in tabelas.items():
                table_data = [["", "Tempo Planejado", "Tempo Executado", "Diferença"]]
                table_data.extend(rows)
                
                t = Table(table_data, colWidths=[200, 100, 100, 100])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#d9e6f2')),
                    ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
                    ('ALIGN', (1,0), (-1,-1), 'CENTER'),
                    ('ALIGN', (0,1), (0,-1), 'LEFT'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                    ('TOPPADDING', (0,0), (-1,-1), 3),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 10))
        else:
            elements.append(Paragraph("Sem dados ou diferenças calculadas", text_style_nodiff))
            elements.append(Spacer(1, 15))
            
        from reportlab.platypus import PageBreak
        elements.append(PageBreak())
        
    doc.build(elements)

def main():
    pasta_output = None
    if MODO_AUTOMATICO:
        csv_p_env = os.environ.get("AERO_CSV_PLANEJADA")
        csv_e_env = os.environ.get("AERO_CSV_EXECUTADA")
        output_dir_env = os.environ.get("AERO_OUTPUT_DIR")
        pasta_p = csv_p_env if csv_p_env else None
        pasta_e = csv_e_env if csv_e_env else None
        pasta_output = output_dir_env if output_dir_env else (os.path.dirname(csv_p_env) if csv_p_env else None)
    else:
        pasta = selecionar_pasta()
        pasta_p = pasta_e = pasta_output = pasta
        
    if not pasta_p or not os.path.exists(pasta_p):
        if not MODO_AUTOMATICO: messagebox.showerror("Erro", "Pasta não selecionada ou inválida.")
        sys.exit(1)
        
    print(f"Lendo CSV Planejado: {pasta_p}")
    df_p, nome_arquivo_p, cols_p = unificar_csvs_da_pasta(pasta_p, 'p')
    
    print(f"Lendo CSV Executado: {pasta_e}")
    df_e, nome_arquivo_e, cols_e = unificar_csvs_da_pasta(pasta_e, 'e')
    
    if df_p is None or df_e is None:
        print("Erro: Não foi possível encontrar as bases QUARTA_VERSAO Planejada e Executada na pasta.")
        if not MODO_AUTOMATICO: messagebox.showerror("Erro", "Não foi possível encontrar arquivos Planejados e Executados na pasta selecionada.")
        sys.exit(1)
        
    resultado = alinhar_e_comparar(df_p, df_e, cols_p, cols_e)
    
    nome_arquivo_pdf, nome_cabecalho, mes_ano, mes_ano_formatado = extrair_mes_ano_nome(nome_arquivo_p)
    
    # Tratamento para evitar erro de permissão (arquivo aberto)
    timestamp_geracao = datetime.now().strftime('%H%M%S')
    nome_pdf = f"RELATORIO_COMPARATIVO_{nome_arquivo_pdf.replace(' ', '_')}_{mes_ano}_{timestamp_geracao}.pdf"
    
    pdf_path = os.path.join(pasta_output, nome_pdf)
    
    try:
        gerar_pdf(resultado, nome_cabecalho, mes_ano_formatado, pdf_path)
    except PermissionError:
        print(f"ERRO: Sem permissão para salvar {pdf_path}. O arquivo pode estar aberto em outro programa.")
        sys.exit(1)
    
    print(f"Relatório gerado em: {pdf_path}")
    if MODO_AUTOMATICO:
        print(f"OUTPUT_PDF={pdf_path}")
    else:
        messagebox.showinfo("Sucesso", f"Relatório comparativo gerado:\n{pdf_path}")

if __name__ == "__main__":
    main()
