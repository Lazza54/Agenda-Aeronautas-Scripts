# -*- coding: utf-8 -*-
"""
Relatório Detalhado de Horas de Repouso Extra - Diurnas, Noturnas e Especiais
Gera PDF com análise detalhada das horas de repouso extra divididas por períodos
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
from config_caminhos import BASE_COMMON_FILES_PATH

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass


class RelatorioRepousoExtraDetalhado:
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
        """Carrega e processa os dados do CSV"""
        try:
            self.df = pd.read_csv(self.arquivo_csv)
            
            # --- NOVO: Filtrar folgas ---
            import json
            base_dir = str(BASE_COMMON_FILES_PATH)
            is_latam = 'LATAM' in str(self.arquivo_csv).upper()
            candidatos_folgas = []
            if is_latam:
                candidatos_folgas.extend([
                    os.path.join(base_dir, "folgas_LATAM.json"),
                    os.path.join(base_dir, "folgas_regulamentares_LATAM.json")
                ])
            candidatos_folgas.extend([
                os.path.join(base_dir, "folgas_regulamentares.json"),
                os.path.join(base_dir, "folgas.json")
            ])
            
            folgas_set = set()
            for cand in candidatos_folgas:
                if os.path.exists(cand):
                    try:
                        with open(cand, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        if isinstance(data, dict):
                            for v in data.values():
                                if isinstance(v, list):
                                    data = v
                                    break
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

            # Colunas Simples (obrigatórias)
            colunas_simples = [
                'Tempo Repouso Extra Simples Diurno', 'Tempo Repouso Extra Simples Noturno',
                'Tempo Repouso Extra Simples Especial Diurno', 'Tempo Repouso Extra Simples Especial Noturno'
            ]
            
            colunas_faltantes = [col for col in colunas_simples if col not in self.df.columns]
            if colunas_faltantes:
                print(f"Aviso: Colunas faltantes: {colunas_faltantes}")
                print(f"\nColunas disponiveis no arquivo:")
                print(list(self.df.columns))
                return False
            
            # Colunas Composta e Revezamento (opcionais)
            colunas_composta = [
                'Tempo Repouso Extra Composta Diurno', 'Tempo Repouso Extra Composta Noturno',
                'Tempo Repouso Extra Composta Especial Diurno', 'Tempo Repouso Extra Composta Especial Noturno'
            ]
            colunas_revezamento = [
                'Tempo Repouso Extra Revezamento Diurno', 'Tempo Repouso Extra Revezamento Noturno',
                'Tempo Repouso Extra Revezamento Especial Diurno', 'Tempo Repouso Extra Revezamento Especial Noturno'
            ]
            
            # Criar colunas opcionais se não existirem
            for col in colunas_composta + colunas_revezamento:
                if col not in self.df.columns:
                    self.df[col] = pd.Timedelta(0)
            
            todas_colunas = colunas_simples + colunas_composta + colunas_revezamento
            
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

            for col in todas_colunas:
                if col in self.df.columns:
                    self.df[col] = self.df[col].apply(robust_to_timedelta)
            
            # Preencher NaN
            self.df[todas_colunas] = self.df[todas_colunas].fillna(pd.Timedelta(0))
            # ---------------------------
            
            # Desprezar valores negativos (clipar em zero)
            for col in todas_colunas:
                # Forçar tipo timedelta64[ns] para garantir compatibilidade com clip
                self.df[col] = self.df[col].astype('timedelta64[ns]')
                self.df[col] = self.df[col].clip(lower=pd.Timedelta(0))
            
            print(f"Dados carregados: {len(self.df)} registros")
            return True
            
        except Exception as e:
            print(f"Erro ao carregar dados: {e}")
            return False
    
    def _formatar_timedelta(self, td):
        """Converte timedelta ou string para formato HH:MM (negativos retornam 00:00)"""
        import pandas as pd
        if isinstance(td, str):
            try:
                td = pd.to_timedelta(td, errors='coerce')
            except Exception:
                return "00:00"
        if pd.isna(td) or td <= pd.Timedelta(0):
            return "00:00"
        try:
            total_seconds = int(td.total_seconds())
        except Exception:
            return "00:00"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
    def _montar_tabela_resumo(self, label, t_d, t_n, t_ed, t_en, bg_data=None):
        """Monta tabela de resumo para um tipo de tripulação"""
        if bg_data is None:
            bg_data = colors.beige
        t_esp = t_ed + t_en
        t_total = t_d + t_n
        t_d_calc = t_d + (t_ed * 2)
        t_n_calc = (t_n * 2) + (t_en * 2)
        t_geral_c = t_d_calc + t_n_calc
        data = [
            [label, 'DIURNO', 'NOTURNO', 'TOTAL', 'TOTAL\nPAGAMENTO'],
            ['Repouso Extra\nTotal',
             self._formatar_timedelta(t_d),
             self._formatar_timedelta(t_n),
             self._formatar_timedelta(t_total),
             self._formatar_timedelta(t_d + (t_n * 2))],
            ['Repouso Extra\nEspecial',
             self._formatar_timedelta(t_ed),
             self._formatar_timedelta(t_en),
             self._formatar_timedelta(t_esp),
             self._formatar_timedelta((t_ed * 2) + (t_en * 2))],
            ['SOMATORIA',
             self._formatar_timedelta(t_d_calc),
             self._formatar_timedelta(t_n_calc),
             self._formatar_timedelta(t_total + t_esp),
             self._formatar_timedelta(t_geral_c)]
        ]
        tbl = Table(data, colWidths=[4.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 3*cm])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -2), bg_data),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d0e0f0')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        return tbl
    
    def gerar_relatorio_pdf(self, nome_arquivo="relatorio_repouso_extra_detalhado.pdf"):
        """Gera o relatório PDF completo"""
        if not self.carregar_dados():
            return False
        
        # Se não há registros, gerar relatório vazio com marca dagua
        if self.df is None or len(self.df) == 0:
            return self._gerar_relatorio_vazio(nome_arquivo)
        
        # Configuração do documento
        doc = SimpleDocTemplate(
            nome_arquivo,
            pagesize=A4,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Estilos
        styles = getSampleStyleSheet()
        story = []
        
        # Título
        titulo_style = ParagraphStyle(
            'TituloCustom',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        story.append(Paragraph("EXTRATO DEMONSTRATIVO DETALHADO DE HORAS DE REPOUSO EXTRA", titulo_style))
        story.append(Paragraph("DIURNAS, NOTURNAS E ESPECIAIS", titulo_style))
        story.append(Spacer(1, 0.3*cm))
        
        # Subtítulo com dados do aeronauta
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
        
        # Adicionar coluna de ano
        self.df['ano'] = pd.to_datetime(self.df['Checkin']).dt.year
        
        # Calcular totais gerais - SIMPLES
        total_s_diurno_geral = self.df['Tempo Repouso Extra Simples Diurno'].sum()
        total_s_noturno_geral = self.df['Tempo Repouso Extra Simples Noturno'].sum()
        total_s_esp_diurno_geral = self.df['Tempo Repouso Extra Simples Especial Diurno'].sum()
        total_s_esp_noturno_geral = self.df['Tempo Repouso Extra Simples Especial Noturno'].sum()
        
        # Calcular totais gerais - COMPOSTA
        total_c_diurno_geral = self.df['Tempo Repouso Extra Composta Diurno'].sum()
        total_c_noturno_geral = self.df['Tempo Repouso Extra Composta Noturno'].sum()
        total_c_esp_diurno_geral = self.df['Tempo Repouso Extra Composta Especial Diurno'].sum()
        total_c_esp_noturno_geral = self.df['Tempo Repouso Extra Composta Especial Noturno'].sum()
        
        # Calcular totais gerais - REVEZAMENTO
        total_r_diurno_geral = self.df['Tempo Repouso Extra Revezamento Diurno'].sum()
        total_r_noturno_geral = self.df['Tempo Repouso Extra Revezamento Noturno'].sum()
        total_r_esp_diurno_geral = self.df['Tempo Repouso Extra Revezamento Especial Diurno'].sum()
        total_r_esp_noturno_geral = self.df['Tempo Repouso Extra Revezamento Especial Noturno'].sum()
        
        # Agrupar dados por ano
        anos = sorted(self.df['ano'].unique())
        
        # CRIAR INDICE REMISSIVO POR ANO
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
            
            # Observação sobre a Lei 13.475
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
            
            # Criar tabela de índice
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
                indice_data.append([
                    Paragraph(link_text, styles['Normal']),
                    Paragraph(f'Detalhamento de Repouso Extra - {ano_int}', styles['Normal'])
                ])
            
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
        
        # Processar cada ano
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
            # Calcular totais do ano - SIMPLES
            total_s_diurno = df_ano['Tempo Repouso Extra Simples Diurno'].sum()
            total_s_noturno = df_ano['Tempo Repouso Extra Simples Noturno'].sum()
            total_s_esp_diurno = df_ano['Tempo Repouso Extra Simples Especial Diurno'].sum()
            total_s_esp_noturno = df_ano['Tempo Repouso Extra Simples Especial Noturno'].sum()
            
            # Calcular totais do ano - COMPOSTA
            total_c_diurno = df_ano['Tempo Repouso Extra Composta Diurno'].sum()
            total_c_noturno = df_ano['Tempo Repouso Extra Composta Noturno'].sum()
            total_c_esp_diurno = df_ano['Tempo Repouso Extra Composta Especial Diurno'].sum()
            total_c_esp_noturno = df_ano['Tempo Repouso Extra Composta Especial Noturno'].sum()
            
            # Calcular totais do ano - REVEZAMENTO
            total_r_diurno = df_ano['Tempo Repouso Extra Revezamento Diurno'].sum()
            total_r_noturno = df_ano['Tempo Repouso Extra Revezamento Noturno'].sum()
            total_r_esp_diurno = df_ano['Tempo Repouso Extra Revezamento Especial Diurno'].sum()
            total_r_esp_noturno = df_ano['Tempo Repouso Extra Revezamento Especial Noturno'].sum()
            
            # Título do ano
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
            story.append(Paragraph(f'<a name="ano_{int(ano)}"/><b>ANO: {int(ano)}</b>', ano_style))
            story.append(Spacer(1, 0.3*cm))
            
            # Tabelas de Resumo do Ano - por tipo de tripulação
            story.append(self._montar_tabela_resumo('TRIPULAÇÃO SIMPLES',
                total_s_diurno, total_s_noturno, total_s_esp_diurno, total_s_esp_noturno))
            story.append(Spacer(1, 0.3*cm))
            story.append(self._montar_tabela_resumo('TRIPULAÇÃO COMPOSTA',
                total_c_diurno, total_c_noturno, total_c_esp_diurno, total_c_esp_noturno))
            story.append(Spacer(1, 0.3*cm))
            story.append(self._montar_tabela_resumo('TRIPULAÇÃO DE\nREVEZAMENTO',
                total_r_diurno, total_r_noturno, total_r_esp_diurno, total_r_esp_noturno))
            story.append(Spacer(1, 0.5*cm))
            
            # Tabela Detalhada por Registro do Ano
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
            
            # Preparar dados detalhados do ano (Simples detalhado + totais Composta e Revezamento)
            detalhes_data = [['DATA', 'ORIG-\nDEST', 'SIMPLES\nDIURNO', 'SIMPLES\nNOTURNO', 
                              'SIMPLES\nESP. D.', 'SIMPLES\nESP. N.', 'TOTAL\nSIMP.', 'TOTAL\nCOMP.', 'TOTAL\nREVEZ.']]
            
            for idx, row in df_ano.iterrows():
                # Extrair data
                data_str = ""
                if 'Checkin' in self.df.columns:
                    try:
                        data_obj = pd.to_datetime(row['Checkin'])
                        data_str = data_obj.strftime('%d/%m/%Y')
                    except:
                        data_str = str(row.get('Checkin', ''))[:10]
                
                # Extrair origem e destino
                origem_destino = ""
                if 'Dep' in self.df.columns and 'Arr' in self.df.columns:
                    origem_destino = f"{row.get('Dep', '')}-{row.get('Arr', '')}"
                
                d = self._formatar_timedelta(row['Tempo Repouso Extra Simples Diurno'])
                n = self._formatar_timedelta(row['Tempo Repouso Extra Simples Noturno'])
                ed = self._formatar_timedelta(row['Tempo Repouso Extra Simples Especial Diurno'])
                en = self._formatar_timedelta(row['Tempo Repouso Extra Simples Especial Noturno'])
                
                total_s_linha = (row['Tempo Repouso Extra Simples Diurno'] + 
                              (row['Tempo Repouso Extra Simples Noturno'] * 2) +
                              (row['Tempo Repouso Extra Simples Especial Diurno'] * 2) + 
                              (row['Tempo Repouso Extra Simples Especial Noturno'] * 3))
                
                total_c_linha = (row['Tempo Repouso Extra Composta Diurno'] + 
                              (row['Tempo Repouso Extra Composta Noturno'] * 2) +
                              (row['Tempo Repouso Extra Composta Especial Diurno'] * 2) + 
                              (row['Tempo Repouso Extra Composta Especial Noturno'] * 3))
                
                total_r_linha = (row['Tempo Repouso Extra Revezamento Diurno'] + 
                              (row['Tempo Repouso Extra Revezamento Noturno'] * 2) +
                              (row['Tempo Repouso Extra Revezamento Especial Diurno'] * 2) + 
                              (row['Tempo Repouso Extra Revezamento Especial Noturno'] * 3))
                
                detalhes_data.append([
                    data_str,
                    origem_destino,
                    d, n, ed, en,
                    self._formatar_timedelta(total_s_linha),
                    self._formatar_timedelta(total_c_linha),
                    self._formatar_timedelta(total_r_linha)
                ])
            
            # Adicionar linha de totais do ano
            total_s_det = (total_s_diurno + (total_s_noturno * 2) + 
                          (total_s_esp_diurno * 2) + (total_s_esp_noturno * 3))
            total_c_det = (total_c_diurno + (total_c_noturno * 2) + 
                          (total_c_esp_diurno * 2) + (total_c_esp_noturno * 3))
            total_r_det = (total_r_diurno + (total_r_noturno * 2) + 
                          (total_r_esp_diurno * 2) + (total_r_esp_noturno * 3))
            detalhes_data.append([
                'TOTAL', '',
                self._formatar_timedelta(total_s_diurno),
                self._formatar_timedelta(total_s_noturno),
                self._formatar_timedelta(total_s_esp_diurno),
                self._formatar_timedelta(total_s_esp_noturno),
                self._formatar_timedelta(total_s_det),
                self._formatar_timedelta(total_c_det),
                self._formatar_timedelta(total_r_det)
            ])
            
            detalhes_table = Table(detalhes_data, colWidths=[1.8*cm, 2.2*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 2*cm, 2*cm, 2*cm])
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
            
            # Link para retornar ao índice
            story.append(Spacer(1, 0.3*cm))
            retorno_style = ParagraphStyle(
                'RetornoIndice',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#1f4788'),
                alignment=TA_RIGHT
            )
            story.append(Paragraph('<link href="#indice" color="blue">Voltar ao Indice</link>', retorno_style))
            
            # Quebra de página entre anos
            if idx_ano < len(anos) - 1:
                story.append(PageBreak())
        
        # Adicionar resumo geral final se houver mais de um ano
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
            
            # Calcular totais com multiplicadores - Resumo geral por tipo de tripulação
            story.append(self._montar_tabela_resumo('GERAL - TRIPULAÇÃO SIMPLES',
                total_s_diurno_geral, total_s_noturno_geral,
                total_s_esp_diurno_geral, total_s_esp_noturno_geral, colors.lightgreen))
            story.append(Spacer(1, 0.3*cm))
            story.append(self._montar_tabela_resumo('GERAL - TRIPULAÇÃO COMPOSTA',
                total_c_diurno_geral, total_c_noturno_geral,
                total_c_esp_diurno_geral, total_c_esp_noturno_geral, colors.lightgreen))
            story.append(Spacer(1, 0.3*cm))
            story.append(self._montar_tabela_resumo('GERAL - TRIPULAÇÃO\nDE REVEZAMENTO',
                total_r_diurno_geral, total_r_noturno_geral,
                total_r_esp_diurno_geral, total_r_esp_noturno_geral, colors.lightgreen))

        
        # Gerar PDF
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
        """Gera relatorio vazio com marca dagua diagonal"""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            
            # Criar canvas
            c = canvas.Canvas(nome_arquivo, pagesize=A4)
            width, height = A4
            
            # Título principal
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(colors.darkblue)
            c.drawCentredString(width/2, height - 100, "EXTRATO DEMONSTRATIVO DETALHADO DE HORAS DE REPOUSO EXTRA")
            c.drawCentredString(width/2, height - 120, "DIURNAS, NOTURNAS E ESPECIAIS")
            
            # Informações do aeronauta
            if self.nome_aeronauta:
                c.setFont("Helvetica", 11)
                c.setFillColor(colors.black)
                c.drawCentredString(width/2, height - 150, f"Aeronauta: {self.nome_aeronauta}")
                c.drawCentredString(width/2, height - 170, f"Base: {self.base} | RE: {self.re}")
            
            # Marca dagua diagonal SEM DADOS
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
    """Funcao principal"""
    print("="*80)
    print("GERADOR DE RELATORIO DETALHADO DE REPOUSO EXTRA")
    print("Diurnas, Noturnas e Especiais")
    print("="*80)
    print()
    print("IMPORTANTE: Selecione o arquivo CSV PROCESSADO que foi gerado pelo")
    print("script 'CRIA VALORES FINAIS REPOUSO EXTRA.py'")
    print("Esse arquivo deve conter as colunas de tempo calculadas.")
    print("="*80)
    print()
    
    # Criar janela root oculta
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)  # Trazer para frente
    root.update()
    
    # Selecionar arquivo CSV
    arquivo_csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    arquivo_csv = arquivo_csv_env if (arquivo_csv_env and os.path.isfile(arquivo_csv_env)) else filedialog.askopenfilename(
        title="Selecione o arquivo CSV PROCESSADO de Repouso Extra (com tempos calculados)",
        filetypes=[("Arquivos CSV", "*REPOUSO_EXTRA*.csv"), ("Todos os arquivos", "*.csv")],
        parent=root
    )
    
    root.attributes('-topmost', False)
    root.update()
    
    if not arquivo_csv:
        messagebox.showwarning("Cancelado", "Nenhum arquivo selecionado.")
        return
    
    print(f"Arquivo selecionado: {os.path.basename(arquivo_csv)}")
    print()
    
    # Criar nome do arquivo de saída
    dir_saida = os.path.dirname(arquivo_csv)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Gerar relatório
    relatorio = RelatorioRepousoExtraDetalhado(arquivo_csv)
    nome_prefixo = f"{relatorio.nome_aeronauta} {relatorio.re} SUMARIO_HORAS_REPOUSO_EXTRA {relatorio.empresa} {relatorio.cargo} {relatorio.periodo}".strip()
    nome_saida = os.path.join(dir_saida, f"{nome_prefixo} {timestamp}.pdf")
    
    if relatorio.gerar_relatorio_pdf(nome_saida):
        messagebox.showinfo("Sucesso", f"Relatorio gerado com sucesso!\n\n{nome_saida}")
    else:
        messagebox.showerror("Erro", "Erro ao gerar relatorio. Verifique o console para detalhes.")


if __name__ == "__main__":
    main()
