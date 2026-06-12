#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gerador de Relatório de Horas de Apresentação
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

class RelatorioApresentacao:
    def __init__(self, arquivo_csv, arquivo_pdf=None):
        """
        Inicializa o gerador de relatórios
        
        Args:
            arquivo_csv (str): Caminho para o arquivo CSV
            arquivo_pdf (str, optional): Caminho para o arquivo PDF de escala
        """
        self.arquivo_csv = arquivo_csv
        self.arquivo_pdf = arquivo_pdf
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
                nome_sem_prefixo = nome_sem_extensao[9:]  # Remove 'escala_p_' ou 'escala_e_' (9 chars)
                partes = nome_sem_prefixo.split('_')
                # O RE estará sempre após o quinto grupo de '_'
                # Busca o RE após três underscores consecutivos
                partes = nome_sem_prefixo.split('_')
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
                else:
                    self.nome_aeronauta = ""
                    self.base = ""
                    self.re = ""
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
            
            # Converte colunas de data/hora (SEM incluir Dep e Arr que são strings)
            colunas_datetime = ['Checkin', 'Start', 'End', 'Checkout']
            for coluna in colunas_datetime:
                if coluna in self.df.columns:
                    self.df[coluna] = pd.to_datetime(self.df[coluna], errors='coerce')
            
            # Garantir que Dep e Arr sejam strings
            for coluna in ['Dep', 'Arr']:
                if coluna in self.df.columns:
                    self.df[coluna] = self.df[coluna].astype(str).replace('nan', '').replace('None', '')
            
            # Converte colunas de tempo para timedelta
            colunas_tempo = [
                'Tempo Apresentacao', 'Tempo Apresentacao Diurno',
                'Tempo Apresentacao Noturno', 'Tempo Apresentacao Especial Diurno',
                'Tempo Apresentacao Especial Noturno'
            ]
            
            for coluna in colunas_tempo:
                if coluna in self.df.columns:
                    self.df[coluna] = pd.to_timedelta(self.df[coluna], errors='coerce')
            
            # Remove linhas com dados inválidos
            self.df = self.df.dropna(subset=['Checkin', 'Start'])
            
            # Ordena por data de apresentação
            self.df = self.df.sort_values('Checkin')
            
            print(f"Dados carregados: {len(self.df)} registros válidos")
            return True
            
        except Exception as e:
            print(f"Erro ao carregar dados: {e}")
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
        """Converte timedelta para string HH:MM"""
        if pd.isna(tempo_delta):
            return "00:00"
        
        total_seconds = int(tempo_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
    def calcular_sumario(self, registros):
        """Calcula sumário para um grupo de registros"""
        colunas_tempo = [
            'Tempo Apresentacao', 'Tempo Apresentacao Diurno',
            'Tempo Apresentacao Noturno', 'Tempo Apresentacao Especial Diurno',
            'Tempo Apresentacao Especial Noturno'
        ]
        
        sumario = {}
        for coluna in colunas_tempo:
            total = pd.Timedelta(0)
            for registro in registros:
                if coluna in registro and not pd.isna(registro[coluna]):
                    total += registro[coluna]
            sumario[coluna] = total
        
        return sumario
    
    def criar_tabela_registros(self, registros, styles):
        """Cria tabela com registros individuais"""
        # Cabeçalho da tabela
        cabecalho = [
            'Atividade', 'Apresentação', 'Partida', 'De', 'Para', 
            'Fim', 'Chegada', 'Tempo\nde\nApresentação'
        ]
        
        dados_tabela = [cabecalho]
        
        for registro in registros:
            # Obter valores Dep e Arr, tratando valores vazios
            dep_valor = registro.get('Dep', '')
            arr_valor = registro.get('Arr', '')
            
            # Tratar strings 'nan', 'NaT', 'None' etc (NAT será considerado valor válido)
            if pd.isna(dep_valor) or str(dep_valor).lower() in ['nan', 'none', '']:
                dep_valor = ''
            else:
                dep_valor = str(dep_valor).strip()
            
            if pd.isna(arr_valor) or str(arr_valor).lower() in ['nan', 'none', '']:
                arr_valor = ''
            else:
                arr_valor = str(arr_valor).strip()
            
            linha = [
                str(registro.get('Activity', '')),
                registro['Checkin'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro['Checkin']) else '',
                registro['Start'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro['Start']) else '',
                dep_valor,
                arr_valor,
                registro['End'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro.get('End', pd.NaT)) else '',
                registro['Checkout'].strftime('%d/%m/%Y %H:%M') if not pd.isna(registro.get('Checkout', pd.NaT)) else '',
                self.formatar_tempo(registro.get('Tempo Apresentacao'))
            ]
            dados_tabela.append(linha)
        
        # Criação da tabela
        # 8 colunas: Atividade (2.2cm), Apresentação (2.6cm), Partida (2.6cm), De (1.3cm), Para (1.3cm), Fim (2.6cm), Chegada (2.6cm), Tempo de Apresentação (2.8cm) = 18cm
        tabela = Table(dados_tabela, colWidths=[2.2*cm, 2.6*cm, 2.6*cm, 1.3*cm, 1.3*cm, 2.6*cm, 2.6*cm, 2.8*cm])
        
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
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Alternância de cores nas linhas
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.beige, colors.white])
        ])
        
        tabela.setStyle(estilo_tabela)
        return tabela
    
    def criar_tabela_sumario(self, sumario, titulo_periodo):
        """Cria tabela de sumário"""
        dados_sumario = [
            ['SUMÁRIO - ' + titulo_periodo, ''],
            ['Horas na Apresentação', self.formatar_tempo(sumario['Tempo Apresentacao'])],
            ['Horas na Apresentação Diurnas', self.formatar_tempo(sumario['Tempo Apresentacao Diurno'])],
            ['Horas na Apresentação Noturnas', self.formatar_tempo(sumario['Tempo Apresentacao Noturno'])],
            ['Horas na Apresentação Especiais Diurnas', self.formatar_tempo(sumario['Tempo Apresentacao Especial Diurno'])],
            ['Horas na Apresentação Especiais Noturnas', self.formatar_tempo(sumario['Tempo Apresentacao Especial Noturno'])]
        ]
        
        # 2 colunas: Descrição (13.5cm), Valor (3cm) = 16.5cm
        tabela_sumario = Table(dados_sumario, colWidths=[13.5*cm, 3*cm])
        
        estilo_sumario = TableStyle([
            # Título
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('SPAN', (0, 0), (-1, 0)),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Dados do sumário
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
        ])
        
        tabela_sumario.setStyle(estilo_sumario)
        return tabela_sumario
    
    def gerar_relatorio_pdf(self, nome_arquivo="relatorio_apresentacao.pdf"):
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
        story.append(Paragraph("EXTRATO DEMONSTRATIVO DE HORAS NA APRESENTAÇÃO", titulo_style))
        
        # Informações do aeronauta
        info_style = ParagraphStyle(
            'InfoAeronauta',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=5,
            alignment=TA_CENTER,
            textColor=colors.black
        )
        if self.nome_aeronauta:
            story.append(Paragraph(f"<b>Aeronauta:</b> {self.nome_aeronauta} - <b>Base:</b> {self.base} - <b>RE:</b> {self.re}", info_style))
            if not self.re or self.re.strip() == "":
                story.append(Paragraph("<b>Aviso:</b> RE não extraído do nome do arquivo. Verifique o padrão do arquivo CSV.", info_style))
        else:
            story.append(Paragraph("<b>Aviso:</b> Não foi possível extrair os dados do aeronauta (nome/base/RE) do arquivo CSV.", info_style))
        story.append(Spacer(1, 20))
        
        # Relatórios semanais
        story.append(Paragraph("RELATÓRIOS SEMANAIS", subtitulo_style))
        story.append(Spacer(1, 10))
        
        for periodo_semanal in sorted(self.dados_processados['semanal'].keys()):
            registros = self.dados_processados['semanal'][periodo_semanal]
            
            if registros:
                # Determinar semana civil completa (domingo a sábado)
                primeira_data = min(r['Checkin'] for r in registros)
                domingo = primeira_data - timedelta(days=(primeira_data.weekday() + 1) % 7)
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
    """Função principal para teste"""
    print("="*60)
    print("🎯 GERADOR DE RELATÓRIO DE HORAS DE APRESENTAÇÃO")
    print("="*60)
    
    arquivo_csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    if arquivo_csv_env and os.path.isfile(arquivo_csv_env):
        arquivo_csv = arquivo_csv_env
        print(f"\n📂 Arquivo CSV de apresentação (ENV): {os.path.basename(arquivo_csv)}")
    else:
        # Seletor de arquivo
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # Selecionar arquivo CSV
        print("\n📂 Selecione o arquivo CSV com os dados de apresentação...")
        arquivo_csv = filedialog.askopenfilename(
            title="Selecione o arquivo CSV de Apresentação",
            filetypes=[
                ("Arquivos CSV", "*.csv"),
                ("Todos os arquivos", "*.*")
            ]
        )
    
    # Verifica se um arquivo CSV foi selecionado
    if not arquivo_csv:
        print("\n❌ Nenhum arquivo selecionado. Operação cancelada.")
        return
    
    print(f"✅ Arquivo selecionado: {os.path.basename(arquivo_csv)}")
    
    # Verifica se o arquivo existe
    if not os.path.exists(arquivo_csv):
        print(f"❌ Arquivo não encontrado: {arquivo_csv}")
        if not MODO_AUTOMATICO:
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{arquivo_csv}")
        return
    
    # Cria o gerador de relatório
    print("\n🔄 Processando dados...")
    gerador = RelatorioApresentacao(arquivo_csv)
    
    # Define nome do arquivo de saída
    diretorio = os.path.dirname(arquivo_csv)
    nome_base = os.path.splitext(os.path.basename(arquivo_csv))[0]
    nome_arquivo = os.path.join(
        diretorio,
        f"{nome_base}_RELATORIO_APRESENTACAO_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
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

        if not MODO_AUTOMATICO:
            messagebox.showinfo(
                "Sucesso", 
                f"Relatório gerado com sucesso!\n\n{os.path.basename(nome_arquivo)}"
            )
    else:
        print(f"\n{'='*60}")
        print("❌ FALHA NA GERAÇÃO DO RELATÓRIO")
        print(f"{'='*60}\n")
        if not MODO_AUTOMATICO:
            messagebox.showerror("Erro", "Falha na geração do relatório.\nVerifique os dados e tente novamente.")

if __name__ == "__main__":
    main()