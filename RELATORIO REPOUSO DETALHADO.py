# -*- coding: utf-8 -*-
"""
SUMÁRIO_HORAS_REPOUSO
Relatório detalhado de horas de repouso (NÃO EXTRA) por ano, inspirado no layout e lógica do RELATORIO REPOUSO EXTRA DETALHADO.
"""

import pandas as pd
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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

class SumarioHorasRepousoDetalhado:
    def __init__(self, arquivo_csv):
        self.arquivo_csv = arquivo_csv
        self.df = None
        self.nome_aeronauta = ""
        self.base = ""
        self.re = ""
        self.empresa = ""
        self.cargo = ""
        self.periodo = ""
        self._extrair_dados_aeronauta()

    def _extrair_dados_aeronauta(self):
        """Extrai dados do aeronauta a partir do nome do arquivo CSV selecionado"""
        try:
            arquivo = os.path.basename(self.arquivo_csv)
            nome_sem_extensao = os.path.splitext(arquivo)[0]
            
            if nome_sem_extensao.startswith('escala_p_') or nome_sem_extensao.startswith('escala_e_'):
                nome_sem_prefixo = nome_sem_extensao[9:]
                partes = nome_sem_prefixo.split('_')
                partes_limpas = [p for p in partes if p.strip()]
                
                # Encontrar as duas datas consecutivas de 8 dígitos no nome do arquivo (ddmmaaaa)
                periodo_encontrado = ""
                for idx in range(len(partes_limpas) - 1):
                    p1 = partes_limpas[idx]
                    p2 = partes_limpas[idx + 1]
                    if len(p1) == 8 and p1.isdigit() and len(p2) == 8 and p2.isdigit():
                        periodo_encontrado = f"{p1}_{p2}"
                        break
                
                if len(partes_limpas) >= 8:
                    self.nome_aeronauta = f"{partes_limpas[0]}_{partes_limpas[1]}".upper()
                    self.base = partes_limpas[2].upper()
                    self.re = partes_limpas[3]
                    self.empresa = partes_limpas[4].upper()
                    self.cargo = partes_limpas[5].upper()
                    self.periodo = periodo_encontrado if periodo_encontrado else f"{partes_limpas[6]}_{partes_limpas[7]}"
                else:
                    # Fallback para nomes incompletos
                    self.nome_aeronauta = f"{partes_limpas[0]}_{partes_limpas[1]}".upper() if len(partes_limpas) > 1 else ""
                    self.base = partes_limpas[2].upper() if len(partes_limpas) > 2 else ""
                    self.re = partes_limpas[3] if len(partes_limpas) > 3 else ""
                    self.empresa = ""
                    self.cargo = ""
                    self.periodo = ""
                        
        except Exception as e:
            print(f"Aviso: Não foi possível extrair dados do aeronauta: {e}")
            self.nome_aeronauta = ""
            self.base = ""
            self.re = ""
            self.empresa = ""
            self.cargo = ""
            self.periodo = ""

    def carregar_dados(self):
        try:
            self.df = pd.read_csv(self.arquivo_csv)
            colunas_necessarias = [
                'Tempo Repouso Diurno', 'Tempo Repouso Noturno',
                'Tempo Repouso Especial Diurno', 'Tempo Repouso Especial Noturno'
            ]
            colunas_faltantes = [col for col in colunas_necessarias if col not in self.df.columns]
            if colunas_faltantes:
                print(f"Aviso: Colunas faltantes: {colunas_faltantes}")
                print(f"\nColunas disponíveis no arquivo:")
                print(list(self.df.columns))
                return False

            # --- NOVO: Filtrar folgas ---
            import json
            base_dir = r'R:\SPECTRUM_SYSTEM\Aeronautas\Documentos_Comuns\Arquivos_Diversos'
            candidatos_folgas = [
                os.path.join(base_dir, "folgas_LATAM.json"),
                os.path.join(base_dir, "folgas_regulamentares_LATAM.json"),
                os.path.join(base_dir, "folgas_regulamentares.json"),
                os.path.join(base_dir, "folgas.json")
            ]
            
            folgas_set = set()
            for cand in candidatos_folgas:
                if os.path.exists(cand):
                    try:
                        with open(cand, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, str):
                                    folgas_set.add(item.strip().upper())
                                elif isinstance(item, dict):
                                    for key in ['atividade', 'Activity', 'name']:
                                        if key in item and isinstance(item[key], str):
                                            folgas_set.add(item[key].strip().upper())
                        print(f"Folgas carregadas de {cand}")
                        break
                    except Exception as e:
                        print(f"Erro ao ler {cand}: {e}")

            if folgas_set and 'Activity' in self.df.columns:
                self.df['activity_upper'] = self.df['Activity'].astype(str).str.strip().str.upper()
                antes = len(self.df)
                self.df = self.df[~self.df['activity_upper'].isin(folgas_set)]
                self.df.drop(columns=['activity_upper'], inplace=True)
                print(f"Filtradas {antes - len(self.df)} atividades de folga.")
            # ---------------------------

            # --- NOVO: Conversão robusta de timedelta ---
            def robust_to_timedelta(val):
                import pandas as pd
                if pd.isna(val) or str(val).strip() == '':
                    return pd.Timedelta(0)
                val_str = str(val).strip()
                if len(val_str.split(':')) == 2:
                    val_str += ':00'
                try:
                    return pd.to_timedelta(val_str)
                except:
                    return pd.Timedelta(0)

            for col in colunas_necessarias:
                if col in self.df.columns:
                    self.df[col] = self.df[col].apply(robust_to_timedelta)
            
            # Preencher NaN
            self.df[colunas_necessarias] = self.df[colunas_necessarias].fillna(pd.Timedelta(0))
            # ---------------------------
            
            return True
        except Exception as e:
            print(f"Erro ao carregar dados: {e}")
            return False

    def _formatar_timedelta(self, td):
        """Converte timedelta para formato HH:MM, aceita timedelta ou string."""
        import pandas as pd
        if pd.isna(td) or td == pd.Timedelta(0):
            return "00:00"
        # Se for string, tenta converter para timedelta
        if isinstance(td, str):
            try:
                td = pd.to_timedelta(td)
            except Exception:
                return "00:00"
        if pd.isna(td) or td == pd.Timedelta(0):
            return "00:00"
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"

    def gerar_relatorio_pdf(self, nome_arquivo="SUMARIO_HORAS_REPOUSO.pdf"):
        if not self.carregar_dados():
            return False
        if self.df is None or len(self.df) == 0:
            return self._gerar_relatorio_vazio(nome_arquivo)
        doc = SimpleDocTemplate(
            nome_arquivo,
            pagesize=A4,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        styles = getSampleStyleSheet()
        story = []
        titulo_style = ParagraphStyle(
            'TituloCustom',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph("EXTRATO DEMONSTRATIVO DETALHADO DE HORAS DE REPOUSO", titulo_style))
        story.append(Spacer(1, 0.3*cm))
        if self.nome_aeronauta:
            subtitulo_style = ParagraphStyle(
                'Subtitulo',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_CENTER,
                spaceAfter=12
            )
            subtitulo_text = f"<b>Aeronauta:</b> {self.nome_aeronauta} - <b>Base:</b> {self.base} - <b>RE:</b> {self.re}"
            story.append(Paragraph(subtitulo_text, subtitulo_style))
        story.append(Spacer(1, 0.5*cm))
        self.df['ano'] = pd.to_datetime(self.df['Checkin']).dt.year
        total_diurno_geral = self.df['Tempo Repouso Diurno'].sum()
        total_noturno_geral = self.df['Tempo Repouso Noturno'].sum()
        total_especial_diurno_geral = self.df['Tempo Repouso Especial Diurno'].sum()
        total_especial_noturno_geral = self.df['Tempo Repouso Especial Noturno'].sum()
        total_especial_geral = total_especial_diurno_geral + total_especial_noturno_geral
        total_geral_geral = total_diurno_geral + total_noturno_geral
        anos = sorted(self.df['ano'].unique())
        if len(anos) > 0:
            indice_style = ParagraphStyle(
                'IndiceTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#1f4788'),
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph('<a name="indice"/>INDICE REMISSIVO - ANOS', indice_style))
            story.append(Spacer(1, 0.3*cm))
            obs_style = ParagraphStyle(
                'ObservacaoLei',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#666666'),
                alignment=TA_CENTER,
                fontName='Helvetica-Oblique',
                spaceAfter=12
            )
            story.append(Paragraph(
                '<i>Observacao: Estao sendo consideradas datas apos a publicacao da Lei 13.475.</i>',
                obs_style
            ))
            story.append(Spacer(1, 0.3*cm))
            from typing import Any
            indice_data: list[list[Any]] = [['ANO', 'DESCRICAO']]
            for ano in anos:
                if pd.isna(ano):
                    print(f"[DEBUG] Ano nulo ou inválido ignorado no índice remissivo: {ano}")
                    continue
                try:
                    ano_int = int(ano)
                except Exception as e:
                    print(f"[ERRO] Não foi possível converter ano '{ano}' para inteiro no índice remissivo: {e}")
                    continue
                link_text = f'<link href="#ano_{ano_int}" color="blue"><u>Ano {ano_int}</u></link>'
                try:
                    par_link = Paragraph(str(link_text), styles['Normal'])
                except Exception as e:
                    print(f"[ERRO] Falha ao criar Paragraph do link: {e}")
                    par_link = Paragraph(f"Ano {ano_int}", styles['Normal'])
                try:
                    par_desc = Paragraph(f'Detalhamento de Repouso - {ano_int}', styles['Normal'])
                except Exception as e:
                    print(f"[ERRO] Falha ao criar Paragraph da descrição: {e}")
                    par_desc = Paragraph(f"Erro descrição ano {ano_int}", styles['Normal'])
                indice_data.append([par_link, par_desc])
            indice_table = Table(indice_data, colWidths=[4*cm, 12*cm])
            indice_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(indice_table)
            story.append(PageBreak())
        for idx_ano, ano in enumerate(anos):
            # Ignorar anos inválidos (NaN)
            if pd.isna(ano):
                print(f"[DEBUG] Ano nulo ou inválido ignorado no processamento principal: {ano}")
                continue
            try:
                ano_int = int(ano)
            except Exception as e:
                print(f"[ERRO] Não foi possível converter ano '{ano}' para inteiro no processamento principal: {e}")
                continue
            df_ano = self.df[self.df['ano'] == ano]
            total_diurno = df_ano['Tempo Repouso Diurno'].sum()
            total_noturno = df_ano['Tempo Repouso Noturno'].sum()
            total_especial_diurno = df_ano['Tempo Repouso Especial Diurno'].sum()
            total_especial_noturno = df_ano['Tempo Repouso Especial Noturno'].sum()
            total_especial = total_especial_diurno + total_especial_noturno
            total_geral = total_diurno + total_noturno
            if idx_ano > 0:
                story.append(Spacer(1, 1*cm))
            ano_style = ParagraphStyle(
                'AnoStyle',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#1f4788'),
                spaceAfter=8,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph(f'<a name="ano_{ano_int}"/><b>ANO: {ano_int}</b>', ano_style))
            story.append(Spacer(1, 0.3*cm))
            resumo_data = [
                ['CATEGORIA', 'DIURNO', 'NOTURNO', 'TOTAL'],
                ['Repouso Total', 
                 self._formatar_timedelta(total_diurno),
                 self._formatar_timedelta(total_noturno),
                 self._formatar_timedelta(total_geral)],
                ['Repouso Especial', 
                 self._formatar_timedelta(total_especial_diurno),
                 self._formatar_timedelta(total_especial_noturno),
                 self._formatar_timedelta(total_especial)],
                ['SOMATORIA', 
                 self._formatar_timedelta(total_diurno + total_especial_diurno),
                 self._formatar_timedelta(total_noturno + total_especial_noturno),
                 self._formatar_timedelta(total_geral + total_especial)]
            ]
            resumo_table = Table(resumo_data, colWidths=[4.5*cm, 2.5*cm, 2.5*cm, 3*cm])
            resumo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d0e0f0')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(resumo_table)
            story.append(Spacer(1, 0.5*cm))
            detalhes_ano_style = ParagraphStyle(
                'DetalheAno',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=6,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph(f"<b>DETALHAMENTO - {int(ano)}</b>", detalhes_ano_style))
            story.append(Spacer(1, 0.3*cm))
            detalhes_data = [['DATA', 'ORIGEM-DESTINO', 'DIURNO', 'NOTURNO', 
                              'ESPECIAL\nDIURNO', 'ESPECIAL\nNOTURNO', 'TOTAL']]
            for idx, row in df_ano.iterrows():
                data_str = ""
                if 'Checkin' in self.df.columns:
                    try:
                        data_obj = pd.to_datetime(row['Checkin'])
                        data_str = data_obj.strftime('%d/%m/%Y')
                    except:
                        data_str = str(row.get('Checkin', ''))[:10]
                origem_destino = ""
                if 'Dep' in self.df.columns and 'Arr' in self.df.columns:
                    origem_destino = f"{row.get('Dep', '')}-{row.get('Arr', '')}"
                d = self._formatar_timedelta(row['Tempo Repouso Diurno'])
                n = self._formatar_timedelta(row['Tempo Repouso Noturno'])
                ed = self._formatar_timedelta(row['Tempo Repouso Especial Diurno'])
                en = self._formatar_timedelta(row['Tempo Repouso Especial Noturno'])
                total_linha = (row['Tempo Repouso Diurno'] + row['Tempo Repouso Noturno'] +
                              row['Tempo Repouso Especial Diurno'] + row['Tempo Repouso Especial Noturno'])
                detalhes_data.append([
                    data_str,
                    origem_destino,
                    d, n, ed, en,
                    self._formatar_timedelta(total_linha)
                ])
            total_detalhamento = (total_diurno + total_noturno + total_especial_diurno + total_especial_noturno)
            detalhes_data.append([
                'TOTAL', '',
                self._formatar_timedelta(total_diurno),
                self._formatar_timedelta(total_noturno),
                self._formatar_timedelta(total_especial_diurno),
                self._formatar_timedelta(total_especial_noturno),
                self._formatar_timedelta(total_detalhamento)
            ])
            detalhes_table = Table(detalhes_data, colWidths=[2.2*cm, 3.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm])
            detalhes_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -2), colors.white),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d0e0f0')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(detalhes_table)
            story.append(Spacer(1, 0.3*cm))
            retorno_style = ParagraphStyle(
                'RetornoIndice',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#1f4788'),
                alignment=TA_RIGHT
            )
            story.append(Paragraph('<link href="#indice" color="blue">Voltar ao Indice</link>', retorno_style))
            if idx_ano < len(anos) - 1:
                story.append(PageBreak())
        if len(anos) > 1:
            story.append(PageBreak())
            story.append(Spacer(1, 1*cm))
            resumo_geral_style = ParagraphStyle(
                'ResumoGeral',
                parent=styles['Heading1'],
                fontSize=14,
                textColor=colors.HexColor('#1f4788'),
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph("RESUMO GERAL - TODOS OS ANOS", resumo_geral_style))
            story.append(Spacer(1, 0.5*cm))
            resumo_geral_data = [
                ['CATEGORIA', 'DIURNO', 'NOTURNO', 'TOTAL'],
                ['Repouso Total', 
                 self._formatar_timedelta(total_diurno_geral),
                 self._formatar_timedelta(total_noturno_geral),
                 self._formatar_timedelta(total_geral_geral)],
                ['Repouso Especial', 
                 self._formatar_timedelta(total_especial_diurno_geral),
                 self._formatar_timedelta(total_especial_noturno_geral),
                 self._formatar_timedelta(total_especial_geral)],
                ['SOMATORIA',
                 self._formatar_timedelta(total_diurno_geral + total_especial_diurno_geral),
                 self._formatar_timedelta(total_noturno_geral + total_especial_noturno_geral),
                 self._formatar_timedelta(total_geral_geral + total_especial_geral)]
            ]
            resumo_geral_table = Table(resumo_geral_data, colWidths=[4.5*cm, 2.5*cm, 2.5*cm, 3*cm])
            resumo_geral_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -2), colors.lightgreen),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#90EE90')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))
            story.append(resumo_geral_table)
        try:
            doc.build(story)
            print(f"\nRelatorio gerado com sucesso!")
            return True
        except Exception as e:
            print(f"Erro ao gerar PDF: {e}")
            import traceback
            traceback.print_exc()
            return False
    def _gerar_relatorio_vazio(self, nome_arquivo):
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            c = canvas.Canvas(nome_arquivo, pagesize=A4)
            width, height = A4
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(colors.darkblue)
            c.drawCentredString(width/2, height - 100, "EXTRATO DEMONSTRATIVO DETALHADO DE HORAS DE REPOUSO")
            if self.nome_aeronauta:
                c.setFont("Helvetica", 11)
                c.setFillColor(colors.black)
                c.drawCentredString(width/2, height - 150, f"Aeronauta: {self.nome_aeronauta}")
                c.drawCentredString(width/2, height - 170, f"Base: {self.base} | RE: {self.re}")
            c.saveState()
            c.translate(width/2, height/2)
            c.rotate(45)
            c.setFont("Helvetica-Bold", 60)
            c.setFillColorRGB(1, 0, 0, alpha=0.3)
            text = "SEM DADOS"
            text_width = c.stringWidth(text, "Helvetica-Bold", 60)
            c.drawString(-text_width/2, 0, text)
            c.restoreState()
            c.save()
            print(f"\nRelatorio vazio gerado com sucesso!")
            return True
        except Exception as e:
            print(f"Erro ao gerar relatorio vazio: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    print("="*80)
    print("GERADOR DE RELATORIO DETALHADO DE REPOUSO")
    print("="*80)
    print()
    print("IMPORTANTE: Selecione o arquivo CSV PROCESSADO que foi gerado pelo")
    print("script 'CRIA VALORES FINAIS REPOUSO.py'")
    print("Esse arquivo deve conter as colunas de tempo calculadas.")
    print("="*80)
    print()
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.update()
    arquivo_csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    arquivo_csv = arquivo_csv_env if (arquivo_csv_env and os.path.isfile(arquivo_csv_env)) else filedialog.askopenfilename(
        title="Selecione o arquivo CSV PROCESSADO de Repouso (com tempos calculados)",
        filetypes=[("Arquivos CSV", "*REPOUSO*.csv"), ("Todos os arquivos", "*.csv")],
        parent=root
    )
    root.attributes('-topmost', False)
    root.update()
    if not arquivo_csv:
        messagebox.showwarning("Cancelado", "Nenhum arquivo selecionado.")
        return
    print(f"Arquivo selecionado: {os.path.basename(arquivo_csv)}")
    print()
    dir_saida = os.path.dirname(arquivo_csv)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    relatorio = SumarioHorasRepousoDetalhado(arquivo_csv)
    nome_prefixo = f"{relatorio.nome_aeronauta} {relatorio.re} SUMARIO_HORAS_REPOUSO {relatorio.empresa} {relatorio.cargo} {relatorio.periodo}".strip()
    nome_saida = os.path.join(dir_saida, f"{nome_prefixo} {timestamp}.pdf")

    if relatorio.gerar_relatorio_pdf(nome_saida):
        messagebox.showinfo("Sucesso", f"Relatorio gerado com sucesso!\n\n{nome_saida}")
    else:
        messagebox.showerror("Erro", "Erro ao gerar relatorio. Verifique o console para detalhes.")

if __name__ == "__main__":
    main()
