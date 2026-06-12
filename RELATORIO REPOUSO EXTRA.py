#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gerador de Relatório de Tempos de Repouso Extra
Sistema para gerar relatórios descritivos com sumarização semanal, mensal e anual
"""

import pandas as pd
from datetime import datetime, timedelta
import os
import sys
from collections import defaultdict
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

# Verificar e importar reportlab
try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
        PageBreak, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
except ImportError:
    print("❌ ERRO: Biblioteca 'reportlab' não encontrada!")
    print("\n📦 Para instalar, execute:")
    print("   pip install reportlab")
    print("\nOu:")
    print("   python -m pip install reportlab")
    sys.exit(1)

class RelatorioRepousoExtra:
    def __init__(self, arquivo_csv):
        """
        Inicializa o gerador de relatórios
        
        Args:
            arquivo_csv (str): Caminho para o arquivo CSV
        """
        self.arquivo_csv = arquivo_csv
        self.df = None
        self.dados_processados = {
            'semanal': defaultdict(list),
            'mensal': defaultdict(list),
            'anual': defaultdict(list)
        }
        self.nome_aeronauta = ""
        self.base = ""
        self.re = ""
        self._extrair_dados_aeronauta()
    
    def _extrair_dados_aeronauta(self):
        """Extrai nome do aeronauta, base e RE do nome do arquivo CSV selecionado"""
        try:
            # Usar o nome do arquivo CSV selecionado
            arquivo = os.path.basename(self.arquivo_csv)
            
            # Remover a extensão .csv
            nome_sem_extensao = os.path.splitext(arquivo)[0]
            
            # Verificar se o arquivo começa com 'escala_p_' ou 'escala_e_'
            if nome_sem_extensao.startswith('escala_p_') or nome_sem_extensao.startswith('escala_e_'):
                # Remover 'escala_p_' ou 'escala_e_'
                nome_sem_prefixo = nome_sem_extensao[9:]  # Remove 'escala_p_' ou 'escala_e_' (9 chars)
                partes = nome_sem_prefixo.split('_')
                
                # Formato esperado: PARTE1_PARTE2_BASE_RE_DATA_DATA
                # Após remover prefixo: PARTE1_PARTE2_BASE_RE_DATA_DATA
                # As últimas 2 partes são datas
                
                if len(partes) >= 6:
                    partes_sem_datas = partes[:-2]
                    if len(partes_sem_datas) >= 4:
                        self.nome_aeronauta = f"{partes_sem_datas[0]} {partes_sem_datas[1]}".upper()
                        self.base = partes_sem_datas[2].upper()
                        self.re = ""
                        for i in range(3, len(partes_sem_datas)):
                            if partes_sem_datas[i] and partes_sem_datas[i].strip():
                                self.re = partes_sem_datas[i].strip()
                                break
        except Exception as e:
            print(f"Aviso: Não foi possível extrair dados do aeronauta: {e}")
            self.nome_aeronauta = ""
            self.base = ""
            self.re = ""
        
    def carregar_dados(self):
        """Carrega e processa os dados do CSV"""
        try:
            # Carrega o CSV
            self.df = pd.read_csv(self.arquivo_csv)
            
            print(f"\n📊 DIAGNÓSTICO DO ARQUIVO CSV:")
            print(f"   Total de linhas carregadas: {len(self.df)}")
            print(f"   Colunas disponíveis: {list(self.df.columns)}")
            
            # Converte colunas de data/hora (SEM incluir Dep e Arr que são strings)
            colunas_datetime = ['Checkin', 'Start', 'End', 'Checkout']
            print(f"\n   Colunas de data/hora esperadas: {colunas_datetime}")
            print(f"   Colunas de data/hora encontradas: {[c for c in colunas_datetime if c in self.df.columns]}")
            
            # Mostrar amostra dos dados antes da conversão
            print(f"\n   📋 Amostra das primeiras linhas de Checkin:")
            if 'Checkin' in self.df.columns:
                print(f"      {self.df['Checkin'].head().tolist()}")
            
            for coluna in colunas_datetime:
                if coluna in self.df.columns:
                    # Tentar múltiplos formatos de data
                    self.df[coluna] = pd.to_datetime(self.df[coluna], errors='coerce')
                    valores_nulos = self.df[coluna].isna().sum()
                    print(f"      {coluna}: {valores_nulos} valores NaT de {len(self.df)}")
            
            # Garantir que Dep e Arr sejam strings
            for coluna in ['Dep', 'Arr']:
                if coluna in self.df.columns:
                    self.df[coluna] = self.df[coluna].astype(str).replace('nan', '').replace('None', '')
            
            # Detecta dinamicamente todas as colunas que contenham 'EXTRA' no nome
            colunas_tempo = [c for c in self.df.columns if 'EXTRA' in c.upper()]
            print(f"\n   Colunas de tempo detectadas (contendo 'EXTRA'): {colunas_tempo}")
            for coluna in colunas_tempo:
                self.df[coluna] = pd.to_timedelta(self.df[coluna], errors='coerce')
            
            print(f"\n   Registros antes de filtrar: {len(self.df)}")
            
            # Remove linhas com dados inválidos
            self.df = self.df.dropna(subset=['Checkin', 'Start'])
            
            print(f"   Registros após filtrar: {len(self.df)}")
            
            # Ordena por data de apresentação
            if len(self.df) > 0:
                self.df = self.df.sort_values('Checkin')
            
            print(f"\n✅ Dados carregados: {len(self.df)} registros válidos")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao carregar dados: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def agrupar_dados(self):
        """Agrupa dados por semana, mês e ano"""
        if self.df is None:
            return False
        
        for idx, row in self.df.iterrows():
            data_checkin = row['Checkin']
            
            # Agrupamento semanal (semana ISO)
            ano_semana = data_checkin.strftime('%Y-W%U')
            self.dados_processados['semanal'][ano_semana].append(row)
            
            # Agrupamento mensal
            ano_mes = data_checkin.strftime('%Y-%m')
            self.dados_processados['mensal'][ano_mes].append(row)
            
            # Agrupamento anual
            ano = data_checkin.strftime('%Y')
            self.dados_processados['anual'][ano].append(row)
        
        return True
    
    def formatar_tempo(self, tempo_delta):
        """Converte timedelta para string HH:MM (negativos retornam 00:00)"""
        if pd.isna(tempo_delta):
            return "00:00"
        
        total_seconds = int(tempo_delta.total_seconds())
        if total_seconds < 0:
            return "00:00"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
    def calcular_sumario(self, registros):
        """Calcula sumário para um grupo de registros"""
        # Detecta dinamicamente todas as colunas que contenham 'EXTRA' no nome
        colunas_extra = []
        if registros:
            if hasattr(registros[0], 'to_dict'):
                keys = registros[0].to_dict().keys()
            elif isinstance(registros[0], dict):
                keys = registros[0].keys()
            else:
                keys = []
            colunas_extra = [c for c in keys if 'EXTRA' in c.upper()]

        sumario = {}
        # Busca os nomes exatos das colunas
        def busca_coluna(nome):
            for c in colunas_extra:
                if c.strip().upper() == nome.upper():
                    return c
            return None

        def soma_coluna(col):
            total = pd.Timedelta(0)
            if col:
                for registro in registros:
                    if hasattr(registro, 'to_dict'):
                        registro = registro.to_dict()
                    if col in registro and not pd.isna(registro[col]):
                        valor = registro[col]
                        if valor > pd.Timedelta(0):
                            total += valor
            return total

        # --- SIMPLES ---
        col_simples_diurno = busca_coluna('Tempo Repouso Extra Simples Diurno')
        col_simples_noturno = busca_coluna('Tempo Repouso Extra Simples Noturno')
        col_simples_esp_diurno = busca_coluna('Tempo Repouso Extra Simples Especial Diurno')
        col_simples_esp_noturno = busca_coluna('Tempo Repouso Extra Simples Especial Noturno')

        sumario['Simples Diurno'] = soma_coluna(col_simples_diurno)
        sumario['Simples Noturno'] = soma_coluna(col_simples_noturno)
        sumario['Simples Especial Diurno'] = soma_coluna(col_simples_esp_diurno)
        sumario['Simples Especial Noturno'] = soma_coluna(col_simples_esp_noturno)
        sumario['Total Simples'] = (
            sumario['Simples Diurno'] + sumario['Simples Noturno'] +
            sumario['Simples Especial Diurno'] + sumario['Simples Especial Noturno']
        )

        # --- COMPOSTA ---
        col_composta_diurno = busca_coluna('Tempo Repouso Extra Composta Diurno')
        col_composta_noturno = busca_coluna('Tempo Repouso Extra Composta Noturno')
        col_composta_esp_diurno = busca_coluna('Tempo Repouso Extra Composta Especial Diurno')
        col_composta_esp_noturno = busca_coluna('Tempo Repouso Extra Composta Especial Noturno')

        sumario['Composta Diurno'] = soma_coluna(col_composta_diurno)
        sumario['Composta Noturno'] = soma_coluna(col_composta_noturno)
        sumario['Composta Especial Diurno'] = soma_coluna(col_composta_esp_diurno)
        sumario['Composta Especial Noturno'] = soma_coluna(col_composta_esp_noturno)
        sumario['Total Composta'] = (
            sumario['Composta Diurno'] + sumario['Composta Noturno'] +
            sumario['Composta Especial Diurno'] + sumario['Composta Especial Noturno']
        )

        # --- REVEZAMENTO ---
        col_revez_diurno = busca_coluna('Tempo Repouso Extra Revezamento Diurno')
        col_revez_noturno = busca_coluna('Tempo Repouso Extra Revezamento Noturno')
        col_revez_esp_diurno = busca_coluna('Tempo Repouso Extra Revezamento Especial Diurno')
        col_revez_esp_noturno = busca_coluna('Tempo Repouso Extra Revezamento Especial Noturno')

        sumario['Revezamento Diurno'] = soma_coluna(col_revez_diurno)
        sumario['Revezamento Noturno'] = soma_coluna(col_revez_noturno)
        sumario['Revezamento Especial Diurno'] = soma_coluna(col_revez_esp_diurno)
        sumario['Revezamento Especial Noturno'] = soma_coluna(col_revez_esp_noturno)
        sumario['Total Revezamento'] = (
            sumario['Revezamento Diurno'] + sumario['Revezamento Noturno'] +
            sumario['Revezamento Especial Diurno'] + sumario['Revezamento Especial Noturno']
        )

        # --- TOTAL GERAL ---
        sumario['Total Geral'] = (
            sumario['Total Simples'] + sumario['Total Composta'] + sumario['Total Revezamento']
        )

        return sumario
    
    def criar_tabela_registros(self, registros, styles):
        """Cria tabela com registros individuais"""
        # Cabeçalho da tabela
        cabecalho = [
            'Atividade', 'Apresentação', 'Partida', 'De', 'Para', 
            'Fim', 'Chegada', 'Repouso\nExtra\nSimples',
            'Repouso\nExtra\nComposta', 'Repouso\nExtra\nRevezam.'
        ]
        
        dados_tabela = [cabecalho]
        
        # Garante que cada registro é um dicionário (compatível com DataFrame ou lista de dicts)
        colunas_extra = []
        coluna_simples = None
        coluna_composta = None
        coluna_revezamento = None
        if registros:
            if hasattr(registros[0], 'to_dict'):
                keys = registros[0].to_dict().keys()
            elif isinstance(registros[0], dict):
                keys = registros[0].keys()
            else:
                keys = []
            colunas_extra = [c for c in keys if 'EXTRA' in c.upper()]
            # Busca as colunas exatas para cada tipo de tripulação
            for c in keys:
                cu = c.strip().upper()
                if cu == 'TEMPO REPOUSO EXTRA SIMPLES':
                    coluna_simples = c
                elif cu == 'TEMPO REPOUSO EXTRA COMPOSTA':
                    coluna_composta = c
                elif cu == 'TEMPO REPOUSO EXTRA REVEZAMENTO':
                    coluna_revezamento = c
        for registro in registros:
            if hasattr(registro, 'to_dict'):
                registro = registro.to_dict()
            # Obter valores Dep e Arr, tratando valores vazios
            dep_valor = registro.get('Dep', '')
            arr_valor = registro.get('Arr', '')
            
            # Tratar strings 'nan', 'NaT', 'None' etc
            if pd.isna(dep_valor) or str(dep_valor).lower() in ['nan', 'nat', 'none', '']:
                dep_valor = ''
            else:
                dep_valor = str(dep_valor).strip()
            
            if pd.isna(arr_valor) or str(arr_valor).lower() in ['nan', 'nat', 'none', '']:
                arr_valor = ''
            else:
                arr_valor = str(arr_valor).strip()
            
            # Valor da coluna Tempo Repouso Extra Simples (negativos desprezados)
            tempo_simples = pd.Timedelta(0)
            if coluna_simples and coluna_simples in registro and not pd.isna(registro[coluna_simples]):
                v = registro[coluna_simples]
                if v > pd.Timedelta(0):
                    tempo_simples = v

            # Valor da coluna Tempo Repouso Extra Composta (negativos desprezados)
            tempo_composta = pd.Timedelta(0)
            if coluna_composta and coluna_composta in registro and not pd.isna(registro[coluna_composta]):
                v = registro[coluna_composta]
                if v > pd.Timedelta(0):
                    tempo_composta = v

            # Valor da coluna Tempo Repouso Extra Revezamento (negativos desprezados)
            tempo_revezamento = pd.Timedelta(0)
            if coluna_revezamento and coluna_revezamento in registro and not pd.isna(registro[coluna_revezamento]):
                v = registro[coluna_revezamento]
                if v > pd.Timedelta(0):
                    tempo_revezamento = v
            
            linha = [
                str(registro.get('Activity', '')),
                registro['Checkin'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro['Checkin']) else '',
                registro['Start'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro['Start']) else '',
                dep_valor,
                arr_valor,
                registro['End'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro.get('End', pd.NaT)) else '',
                registro['Checkout'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro.get('Checkout', pd.NaT)) else '',
                self.formatar_tempo(tempo_simples),
                self.formatar_tempo(tempo_composta),
                self.formatar_tempo(tempo_revezamento)
            ]
            dados_tabela.append(linha)
        
        # Criação da tabela
        # 10 colunas: Atividade(1.8) Apresentação(2.4) Partida(2.4) De(1.1) Para(1.1) Fim(2.4) Chegada(2.4) Simples(1.8) Composta(1.8) Revezam(1.8) = 19cm
        tabela = Table(dados_tabela, colWidths=[1.8*cm, 2.4*cm, 2.4*cm, 1.1*cm, 1.1*cm, 2.4*cm, 2.4*cm, 1.8*cm, 1.8*cm, 1.8*cm])
        # Estilo da tabela
        estilo_tabela = TableStyle([
            # Cabeçalho
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            # Dados
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        tabela.setStyle(estilo_tabela)
        return tabela
    def criar_tabela_sumario(self, sumario, titulo_periodo):
        """Cria tabela de sumário com seções para Simples, Composta e Revezamento"""
        dados_sumario = [
            ['SUMÁRIO - ' + titulo_periodo, ''],
            ['Horas de Repouso Extra - TOTAL GERAL', self.formatar_tempo(sumario.get('Total Geral', pd.Timedelta(0)))],
            # --- SIMPLES ---
            ['TRIPULAÇÃO SIMPLES', ''],
            ['  Total Simples', self.formatar_tempo(sumario.get('Total Simples', pd.Timedelta(0)))],
            ['  Diurno', self.formatar_tempo(sumario.get('Simples Diurno', pd.Timedelta(0)))],
            ['  Noturno', self.formatar_tempo(sumario.get('Simples Noturno', pd.Timedelta(0)))],
            ['  Especial Diurno', self.formatar_tempo(sumario.get('Simples Especial Diurno', pd.Timedelta(0)))],
            ['  Especial Noturno', self.formatar_tempo(sumario.get('Simples Especial Noturno', pd.Timedelta(0)))],
            # --- COMPOSTA ---
            ['TRIPULAÇÃO COMPOSTA', ''],
            ['  Total Composta', self.formatar_tempo(sumario.get('Total Composta', pd.Timedelta(0)))],
            ['  Diurno', self.formatar_tempo(sumario.get('Composta Diurno', pd.Timedelta(0)))],
            ['  Noturno', self.formatar_tempo(sumario.get('Composta Noturno', pd.Timedelta(0)))],
            ['  Especial Diurno', self.formatar_tempo(sumario.get('Composta Especial Diurno', pd.Timedelta(0)))],
            ['  Especial Noturno', self.formatar_tempo(sumario.get('Composta Especial Noturno', pd.Timedelta(0)))],
            # --- REVEZAMENTO ---
            ['TRIPULAÇÃO DE REVEZAMENTO', ''],
            ['  Total Revezamento', self.formatar_tempo(sumario.get('Total Revezamento', pd.Timedelta(0)))],
            ['  Diurno', self.formatar_tempo(sumario.get('Revezamento Diurno', pd.Timedelta(0)))],
            ['  Noturno', self.formatar_tempo(sumario.get('Revezamento Noturno', pd.Timedelta(0)))],
            ['  Especial Diurno', self.formatar_tempo(sumario.get('Revezamento Especial Diurno', pd.Timedelta(0)))],
            ['  Especial Noturno', self.formatar_tempo(sumario.get('Revezamento Especial Noturno', pd.Timedelta(0)))],
        ]
        
        # 2 colunas: Descrição (13.5cm), Valor (3cm) = 16.5cm
        tabela_sumario = Table(dados_sumario, colWidths=[13.5*cm, 3*cm])
        
        estilo_sumario = TableStyle([
            # Título principal
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('SPAN', (0, 0), (-1, 0)),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Linha TOTAL GERAL
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFFFCC')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 9),
            
            # Cabeçalhos de seção (SIMPLES=row2, COMPOSTA=row8, REVEZAMENTO=row14)
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
            ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 2), (-1, 2), 9),
            ('SPAN', (0, 2), (-1, 2)),
            ('ALIGN', (0, 2), (-1, 2), 'CENTER'),
            
            ('BACKGROUND', (0, 8), (-1, 8), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 8), (-1, 8), colors.white),
            ('FONTNAME', (0, 8), (-1, 8), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 8), (-1, 8), 9),
            ('SPAN', (0, 8), (-1, 8)),
            ('ALIGN', (0, 8), (-1, 8), 'CENTER'),
            
            ('BACKGROUND', (0, 14), (-1, 14), colors.HexColor('#4472C4')),
            ('TEXTCOLOR', (0, 14), (-1, 14), colors.white),
            ('FONTNAME', (0, 14), (-1, 14), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 14), (-1, 14), 9),
            ('SPAN', (0, 14), (-1, 14)),
            ('ALIGN', (0, 14), (-1, 14), 'CENTER'),
            
            # Linhas de total de cada seção (rows 3, 9, 15)
            ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
            ('FONTNAME', (0, 9), (-1, 9), 'Helvetica-Bold'),
            ('FONTNAME', (0, 15), (-1, 15), 'Helvetica-Bold'),
            
            # Dados gerais
            ('FONTNAME', (0, 4), (-1, 7), 'Helvetica'),
            ('FONTNAME', (0, 10), (-1, 13), 'Helvetica'),
            ('FONTNAME', (0, 16), (-1, 19), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 3), (0, 7), colors.lightgrey),
            ('BACKGROUND', (0, 9), (0, 13), colors.lightgrey),
            ('BACKGROUND', (0, 15), (0, 19), colors.lightgrey),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ])
        
        tabela_sumario.setStyle(estilo_sumario)
        return tabela_sumario
    
    def gerar_relatorio_pdf(self, nome_arquivo="relatorio_repouso_extra.pdf"):
        """Gera o relatório PDF completo"""
        if not self.carregar_dados():
            return False
        
        if not self.agrupar_dados():
            return False
        
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
        titulo_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.darkblue
        )
        
        subtitulo_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=15,
            alignment=TA_LEFT,
            textColor=colors.darkred
        )
        
        # Conteúdo do relatório
        story = []
        
        # Título principal
        story.append(Paragraph("EXTRATO DEMONSTRATIVO DE HORAS DE REPOUSO EXTRA", titulo_style))
        
        # Informações do aeronauta
        if self.nome_aeronauta:
            info_style = ParagraphStyle(
                'InfoAeronauta',
                parent=styles['Normal'],
                fontSize=11,
                spaceAfter=5,
                alignment=TA_CENTER,
                textColor=colors.black
            )
            story.append(Paragraph(f"<b>Aeronauta:</b> {self.nome_aeronauta}", info_style))
            story.append(Paragraph(f"<b>Base:</b> {self.base} | <b>RE:</b> {self.re}", info_style))
        
        story.append(Spacer(1, 20))
        
        # Relatórios semanais
        story.append(Paragraph("RELATÓRIOS SEMANAIS", subtitulo_style))
        story.append(Spacer(1, 10))
        
        for periodo_semanal in sorted(self.dados_processados['semanal'].keys()):
            registros = self.dados_processados['semanal'][periodo_semanal]
            
            if registros:
                # Determinar período da semana (domingo a sábado)
                qualquer_data = registros[0]['Checkin']
                domingo = qualquer_data - timedelta(days=(qualquer_data.weekday() + 1) % 7)
                sabado = domingo + timedelta(days=6)
                titulo_periodo = f"Semana de {domingo.strftime('%d/%m/%Y')} a {sabado.strftime('%d/%m/%Y')}"
                
                # Título da semana
                story.append(Paragraph(f"<b>{titulo_periodo}</b>", styles['Heading3']))
                story.append(Spacer(1, 10))
                
                # Tabela de registros
                tabela_registros = self.criar_tabela_registros(registros, styles)
                story.append(tabela_registros)
                story.append(Spacer(1, 15))
                
                # Sumário semanal
                sumario = self.calcular_sumario(registros)
                tabela_sumario = self.criar_tabela_sumario(sumario, titulo_periodo)
                story.append(tabela_sumario)
                story.append(Spacer(1, 25))
        
        # Nova página para relatórios mensais
        story.append(PageBreak())
        story.append(Paragraph("RELATÓRIOS MENSAIS", subtitulo_style))
        story.append(Spacer(1, 10))
        
        for periodo_mensal in sorted(self.dados_processados['mensal'].keys()):
            registros = self.dados_processados['mensal'][periodo_mensal]
            
            if registros:
                # Determinar período do mês
                data_ref = datetime.strptime(periodo_mensal + '-01', '%Y-%m-%d')
                mes_ptbr = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'][data_ref.month - 1]
                titulo_periodo = f"Mês de {mes_ptbr} de {data_ref.year}"
                
                # Título do mês
                story.append(Paragraph(f"<b>{titulo_periodo}</b>", styles['Heading3']))
                story.append(Spacer(1, 10))
                
                # Tabela de registros (limitada para não ficar muito extensa)
                if len(registros) > 50:  # Se muitos registros, mostrar apenas sumário
                    story.append(Paragraph(f"<i>Período com {len(registros)} registros - Exibindo apenas sumário</i>", styles['Normal']))
                    story.append(Spacer(1, 10))
                else:
                    tabela_registros = self.criar_tabela_registros(registros, styles)
                    story.append(tabela_registros)
                    story.append(Spacer(1, 15))
                
                # Sumário mensal
                sumario = self.calcular_sumario(registros)
                tabela_sumario = self.criar_tabela_sumario(sumario, titulo_periodo)
                story.append(tabela_sumario)
                story.append(Spacer(1, 25))
        
        # Gerar o PDF
        try:
            doc.build(story)
            print(f"Relatório gerado com sucesso: {nome_arquivo}")
            return True
        except Exception as e:
            print(f"Erro ao gerar relatório: {e}")
            return False

def main():
    """Função principal"""
    print("="*60)
    print("🎯 GERADOR DE RELATÓRIO DE TEMPOS DE REPOUSO EXTRA")
    print("="*60)
    
    # Seletor de arquivo CSV
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    print("\n📂 Selecione o arquivo CSV com os dados de Tempos de Repouso Extra...")
    arquivo_csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    arquivo_csv = arquivo_csv_env if (arquivo_csv_env and os.path.isfile(arquivo_csv_env)) else filedialog.askopenfilename(
        title="Selecione o arquivo CSV de Tempos de Repouso Extra",
        filetypes=[
            ("Arquivos CSV", "*.csv"),
            ("Todos os arquivos", "*.*")
        ]
    )
    
    # Verifica se um arquivo foi selecionado
    if not arquivo_csv:
        print("\n❌ Nenhum arquivo selecionado. Operação cancelada.")
        return
    
    print(f"✅ Arquivo selecionado: {os.path.basename(arquivo_csv)}")
    
    # Verifica se o arquivo existe
    if not os.path.exists(arquivo_csv):
        print(f"❌ Arquivo não encontrado: {arquivo_csv}")
        messagebox.showerror("Erro", f"Arquivo não encontrado:\n{arquivo_csv}")
        return
    
    # Cria o gerador de relatório
    print("\n🔄 Processando dados...")
    gerador = RelatorioRepousoExtra(arquivo_csv)
    
    # Define nome do arquivo de saída
    diretorio = os.path.dirname(arquivo_csv)
    nome_base = os.path.splitext(os.path.basename(arquivo_csv))[0]
    nome_arquivo = os.path.join(
        diretorio,
        f"{nome_base}_RELATORIO_REPOUSO_EXTRA_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )
    
    # Gera o relatório
    print("📝 Gerando relatório PDF...")
    if gerador.gerar_relatorio_pdf(nome_arquivo):
        print(f"\n{'='*60}")
        print("✅ RELATÓRIO GERADO COM SUCESSO!")
        print(f"{'='*60}")
        print(f"📄 Arquivo: {os.path.basename(nome_arquivo)}")
        print(f"📁 Local: {os.path.dirname(nome_arquivo)}")
        print(f"{'='*60}\n")
        
        messagebox.showinfo(
            "Sucesso", 
            f"Relatório gerado com sucesso!\n\n{os.path.basename(nome_arquivo)}"
        )
    else:
        print(f"\n{'='*60}")
        print("❌ FALHA NA GERAÇÃO DO RELATÓRIO")
        print(f"{'='*60}\n")
        messagebox.showerror("Erro", "Falha na geração do relatório.\nVerifique os dados e tente novamente.")

if __name__ == "__main__":
    main()
