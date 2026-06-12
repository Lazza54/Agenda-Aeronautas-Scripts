# -*- coding: utf-8 -*-
"""
Relatório Detalhado de Horas em Solo - Diurnas, Noturnas e Especiais
Gera PDF com análise detalhada das horas em solo divididas por períodos
"""

import pandas as pd
import os
import glob
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import tkinter as tk
from tkinter import filedialog, messagebox
import sys

# Importar módulo Supabase
try:
    import SUPABASE_CONEXAO_DEV as supabase_dev
except ImportError:
    print("⚠️  Aviso: SUPABASE_CONEXAO_DEV não disponível. Consultas ao Supabase serão desabilitadas.")
    supabase_dev = None

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass


class RelatorioTempoSoloDetalhado:
    def __init__(self, arquivo_csv):
        self.arquivo_csv = arquivo_csv
        self.df = None
        self.df_primeira_versao = None
        self.nome_aeronauta = ""
        self.base = ""
        self.re = ""
        self.funcao_arquivo = None
        self.df_tabela_hora = None      # tabela TABELA_VALORES_HORA_VOO_2017_AZUL_ATUAL.csv
        self.cargos_historico = None    # Histórico de funções do Supabase (JSON parseado)
        self.periodos_funcao = {}       # Dict com períodos e funções {funcao: [(inicio, fim), ...]}
        self.empresa = ""
        self.cargo = ""
        self.periodo = ""
        self._extrair_dados_aeronauta()
        self._consultar_supabase()
    
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
            self.funcao_arquivo = None

    def _extrair_funcao_por_nome_arquivo(self, nome_sem_extensao):
        """Extrai função pela 8ª posição do nome do CSV fonte.

        Regra solicitada:
          - FA   -> COMISSARIO
          - CMTE -> CMTE
          - FO   -> COPILOTO
        """
        try:
            mapa_funcoes = {
                'FA': 'COMISSARIO',
                'CMTE': 'CMTE',
                'FO': 'COPILOTO',
            }

            nome_base = str(nome_sem_extensao)

            # Usa a parte anterior ao sufixo de etapa (preferência: _QUARTA_VERSAO)
            marcadores = ['_QUARTA_VERSAO', '_TEMPO_SOLO', '_OPERACAO', '_APRESENTACAO']
            for marcador in marcadores:
                if marcador in nome_base:
                    nome_base = nome_base.split(marcador)[0]
                    break

            # Tentativa 1: 8ª posição no nome completo (inclui prefixos, se houver)
            partes_full = [p for p in nome_base.split('_') if p != '']
            token_funcao = None
            if len(partes_full) >= 8:
                token_funcao = partes_full[7].strip().upper()  # 8ª posição (índice 7)
                funcao = mapa_funcoes.get(token_funcao)
                if funcao:
                    print(f"✅ Função identificada pelo nome do arquivo (8ª posição): {token_funcao} -> {funcao}")
                    return funcao

            # Tentativa 2: 8ª posição após remover prefixo escala_p_/escala_e_
            nome_sem_prefixo = nome_base
            if nome_sem_prefixo.startswith('escala_p_') or nome_sem_prefixo.startswith('escala_e_'):
                nome_sem_prefixo = nome_sem_prefixo[9:]
            partes_sem_prefixo = [p for p in nome_sem_prefixo.split('_') if p != '']
            if len(partes_sem_prefixo) >= 8:
                token_funcao = partes_sem_prefixo[7].strip().upper()
                funcao = mapa_funcoes.get(token_funcao)
                if funcao:
                    print(f"✅ Função identificada pelo nome do arquivo (8ª posição sem prefixo): {token_funcao} -> {funcao}")
                    return funcao

            # Tentativa 3 (fallback): buscar token conhecido da direita para a esquerda
            # antes do sufixo de etapa, para manter robustez entre layouts de nome.
            for token in reversed(partes_full):
                token_up = token.strip().upper()
                if token_up in mapa_funcoes:
                    funcao = mapa_funcoes[token_up]
                    print(f"✅ Função identificada por fallback no nome do arquivo: {token_up} -> {funcao}")
                    return funcao

            if token_funcao:
                print(f"⚠️  8ª posição do nome do arquivo sem mapeamento de função: {token_funcao}")
            else:
                print("⚠️  Não foi possível identificar função no nome do arquivo.")
            return None
        except Exception:
            return None
    
    def _consultar_supabase(self):
        """Consulta dados do associado no Supabase e extrai histórico de funções"""
        try:
            if supabase_dev is None:
                print("⚠️  Módulo Supabase não disponível. Histórico de funções não será carregado.")
                return
            
            # Extrair matrícula do nome do arquivo
            arquivo = os.path.basename(self.arquivo_csv)
            matricula = supabase_dev.extrair_matricula_do_nome_arquivo(arquivo)
            
            if not matricula:
                print("⚠️  Não foi possível extrair matrícula do arquivo.")
                return
            
            print(f"📋 Matrícula extraída: {matricula}")
            
            # Buscar associado no Supabase
            associado = supabase_dev.buscar_associado_por_matricula(matricula)
            
            if not associado:
                print(f"⚠️  Associado com matrícula {matricula} não encontrado no Supabase.")
                return
            
            nome_assoc = (
                associado.get('nome')
                or associado.get('nome_completo')
                or associado.get('full_name')
                or 'N/A'
            )
            print(f"✅ Associado encontrado: {nome_assoc}")
            
            # Extrair histórico de funções (cargos_historico)
            cargos_json = associado.get('cargos_historico')
            if not cargos_json:
                print("⚠️  Campo 'cargos_historico' não encontrado ou vazio.")
                return
            
            # Parse do JSON se for string
            try:
                if isinstance(cargos_json, str):
                    self.cargos_historico = json.loads(cargos_json)
                else:
                    self.cargos_historico = cargos_json
            except Exception as e:
                print(f"⚠️  Erro ao fazer parse de cargos_historico: {e}")
                return
            
            # Processar histórico em períodos por função
            self._processar_periodos_funcao()
            print(f"✅ Histórico de funções carregado: {len(self.periodos_funcao)} função(ões)")
            
        except Exception as e:
            print(f"⚠️  Erro ao consultar Supabase: {e}")
            import traceback
            traceback.print_exc()
    
    def _processar_periodos_funcao(self):
        """Processa cargos_historico em dict de períodos por função
        Formato de entrada: [{"funcao": "...", "inicio": "YYYY-MM-DD", "fim": "YYYY-MM-DD ou None"}, ...]
        Formato de saída: {"FUNCAO": [(data_inicio, data_fim), ...], ...}
        """
        self.periodos_funcao = {}
        
        if not self.cargos_historico or not isinstance(self.cargos_historico, list):
            return
        
        for cargo in self.cargos_historico:
            # Payload pode vir com 'funcao' ou 'cargo' (caso real do Supabase)
            funcao_raw = (
                cargo.get('funcao')
                or cargo.get('cargo')
                or cargo.get('categoria')
                or ''
            )
            funcao_nome = str(funcao_raw).strip().upper()
            inicio_str = cargo.get('inicio', '').strip()
            fim_str = cargo.get('fim', '').strip() if cargo.get('fim') else None
            
            if not funcao_nome or not inicio_str:
                continue
            
            try:
                inicio = pd.to_datetime(inicio_str).date()
                fim = pd.to_datetime(fim_str).date() if fim_str and fim_str.lower() != 'none' else None
                
                if funcao_nome not in self.periodos_funcao:
                    self.periodos_funcao[funcao_nome] = []
                
                self.periodos_funcao[funcao_nome].append((inicio, fim))
                print(f"  • {funcao_nome}: {inicio} até {fim if fim else 'vigente'}")
            except Exception as e:
                print(f"⚠️  Erro ao processar período: {e}")
    
    def _obter_funcao_na_data(self, data_consulta):
        """Retorna a função ativa em uma data específica
        Retorna None se nenhuma função ativa for encontrada"""
        if not self.periodos_funcao:
            return None
        
        try:
            if isinstance(data_consulta, str):
                data_consulta = pd.to_datetime(data_consulta).date()
            elif isinstance(data_consulta, pd.Timestamp):
                data_consulta = data_consulta.date()
        except:
            return None
        
        for funcao, periodos in self.periodos_funcao.items():
            for inicio, fim in periodos:
                if inicio <= data_consulta:
                    if fim is None or data_consulta <= fim:
                        return funcao
        
        return None
    
    def _segmentar_horas_por_funcao(self, df_periodo, ano=None):
        """Segmenta horas de um período por função, usando cargos_historico.
        Retorna dict: {funcao: total_horas_timedelta, ...}
        Se não houver histórico, retorna dict com função predominante."""
        
        resultado = {}
        
        # Se não há histórico ou períodos, usar função predominante (fallback)
        if not self.periodos_funcao or df_periodo is None or len(df_periodo) == 0:
            funcao_fallback = self.funcao_arquivo
            if funcao_fallback:
                # Somar todas as horas
                td_total = (
                    df_periodo['Tempo Solo Diurno'].sum() +
                    df_periodo['Tempo Solo Noturno'].sum() +
                    df_periodo['Tempo Solo Especial Diurno'].sum() +
                    df_periodo['Tempo Solo Especial Noturno'].sum()
                )
                resultado[funcao_fallback] = td_total
            return resultado
        
        # Com histórico: agrupar registros por função em cada data
        try:
            # Converter Checkin para datetime se necessário
            if 'Checkin_dt' not in df_periodo.columns:
                df_periodo = df_periodo.copy()
                df_periodo['Checkin_dt'] = pd.to_datetime(df_periodo['Checkin'], errors='coerce')
            
            for idx, row in df_periodo.iterrows():
                data_voo = row['Checkin_dt']
                
                # Obter função ativa nessa data
                funcao_ativa = self._obter_funcao_na_data(data_voo)
                
                # Se não encontrar função, usar fallback
                if funcao_ativa is None:
                    funcao_ativa = self.funcao_arquivo
                
                if funcao_ativa is None:
                    continue
                
                # Normalizar nome da função
                funcao_ativa = str(funcao_ativa).upper()
                
                # Somar horas dessa linha para a função
                td_linha = (
                    row['Tempo Solo Diurno'] +
                    row['Tempo Solo Noturno'] +
                    row['Tempo Solo Especial Diurno'] +
                    row['Tempo Solo Especial Noturno']
                )
                
                if pd.isna(td_linha):
                    td_linha = pd.Timedelta(0)
                
                if funcao_ativa not in resultado:
                    resultado[funcao_ativa] = pd.Timedelta(0)
                
                resultado[funcao_ativa] += td_linha
        
        except Exception as e:
            print(f"⚠️  Erro ao segmentar horas por função: {e}")
            # Fallback: retornar com função predominante
            funcao_fallback = self.funcao_arquivo
            if funcao_fallback:
                td_total = (
                    df_periodo['Tempo Solo Diurno'].sum() +
                    df_periodo['Tempo Solo Noturno'].sum() +
                    df_periodo['Tempo Solo Especial Diurno'].sum() +
                    df_periodo['Tempo Solo Especial Noturno'].sum()
                )
                resultado[funcao_fallback] = td_total
        
        return resultado

    def _normalizar_funcao_historico(self, funcao):
        """Normaliza rótulos de função para CMTE/COPILOTO/COMISSARIO."""
        s = str(funcao or '').strip().upper()
        if not s:
            return None
        if 'CMTE' in s or 'COMANDANTE' in s:
            return 'CMTE'
        if 'COPILOTO' in s or ' - FO' in s or s.endswith('FO'):
            return 'COPILOTO'
        if 'COMISS' in s or s in ('FA', 'COM'):
            return 'COMISSARIO'
        return s

    def _calcular_valor_hora_ano_por_regras(self, df_ano, ano, equipamento_fallback=None, funcao_fallback=None):
        import pandas as pd
        """Aplica regra de função única vs múltiplas funções para calcular valor-hora do ano.

        Regra:
        - Se houve apenas uma função no período: usa valor da tabela para essa função no ano.
        - Se houve mais de uma função no período: calcula valor-hora efetivo ponderado por horas
          de cada registro, considerando a função ativa na data (início/fim de função).
        """
        if self.df_tabela_hora is None or df_ano is None or len(df_ano) == 0:
            return None

        base = df_ano.copy()
        if 'Checkin_dt' not in base.columns:
            base['Checkin_dt'] = pd.to_datetime(base['Checkin'], errors='coerce')

        # Equipamento de referência
        equipamento_ref = equipamento_fallback
        if equipamento_ref is None and 'AcVer' in base.columns:
            eq_vals = base['AcVer'].dropna().apply(self._determinar_equipamento).dropna()
            if not eq_vals.empty:
                equipamento_ref = eq_vals.mode().iloc[0]

        funcoes_no_periodo = []
        registros = []

        for _, row in base.iterrows():
            data_ref = row.get('Checkin_dt')
            func_row = self._obter_funcao_na_data(data_ref) if self.periodos_funcao else None
            func_row = self._normalizar_funcao_historico(func_row)
            if func_row is None:
                func_row = self._normalizar_funcao_historico(funcao_fallback or self.funcao_arquivo)
            if func_row is None:
                continue

            equip_row = None
            if 'AcVer' in base.columns:
                equip_row = self._determinar_equipamento(row.get('AcVer'))
            if equip_row is None:
                equip_row = equipamento_ref

            td_pag = (
                row.get('Tempo Solo Diurno', pd.Timedelta(0)) +
                (row.get('Tempo Solo Noturno', pd.Timedelta(0)) * 2) +
                (row.get('Tempo Solo Especial Diurno', pd.Timedelta(0)) * 2) +
                (row.get('Tempo Solo Especial Noturno', pd.Timedelta(0)) * 2)
            )
            # Converter para Timedelta se for string
            import pandas as pd
            if isinstance(td_pag, str):
                try:
                    td_pag = pd.to_timedelta(td_pag)
                except Exception:
                    td_pag = pd.Timedelta(0)
            if pd.isna(td_pag) or td_pag <= pd.Timedelta(0):
                continue

            h_pag = self._timedelta_para_horas(td_pag)
            funcoes_no_periodo.append(func_row)
            registros.append((func_row, equip_row, h_pag))

        if not registros:
            return None

        funcoes_unicas = sorted(set(funcoes_no_periodo))

        # Caso 1: apenas uma função no período
        if len(funcoes_unicas) == 1:
            funcao_unica = funcoes_unicas[0]
            vh = self._obter_valor_hora(int(ano), equipamento_ref, funcao_unica)
            if vh is not None:
                print(f"INFO Ano {int(ano)}: função única no período = {funcao_unica}; valor tabela = {self._formatar_moeda(vh)}")
            return vh

        # Caso 2: múltiplas funções no período (valor efetivo por data/função)
        total_valor = 0.0
        total_horas = 0.0
        for func_row, equip_row, h_pag in registros:
            vh_row = self._obter_valor_hora(int(ano), equip_row, func_row)
            if vh_row is None:
                continue
            total_horas += h_pag
            total_valor += (h_pag * vh_row)

        if total_horas <= 0:
            return None

        vh_efetivo = total_valor / total_horas
        print(f"INFO Ano {int(ano)}: múltiplas funções no período {funcoes_unicas}; valor efetivo = {self._formatar_moeda(vh_efetivo)}")
        return vh_efetivo
        
    def carregar_dados(self):
        """Carrega e processa os dados do CSV"""
        try:
            # Carrega o CSV
            self.df = pd.read_csv(self.arquivo_csv)
            
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

            # Verificar se colunas necessárias existem
            colunas_necessarias = [
                'Tempo Solo Diurno', 'Tempo Solo Noturno',
                'Tempo Solo Especial Diurno', 'Tempo Solo Especial Noturno'
            ]
            
            colunas_faltantes = [col for col in colunas_necessarias if col not in self.df.columns]
            if colunas_faltantes:
                print(f"Aviso: Colunas faltantes: {colunas_faltantes}")
                return False
            
            # Converter colunas de Pagamento para timedelta, se presentes no CSV
            colunas_pagamento = [
                'Pagamento Diurno', 'Pagamento Noturno',
                'Pagamento Especial Diurno', 'Pagamento Especial Noturno'
            ]
            colunas_pag_presentes = [c for c in colunas_pagamento if c in self.df.columns]
            
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

            for col in colunas_necessarias + colunas_pag_presentes:
                if col in self.df.columns:
                    self.df[col] = self.df[col].apply(robust_to_timedelta)
            
            # Preencher valores NaN com timedelta zero
            self.df[colunas_necessarias] = self.df[colunas_necessarias].fillna(pd.Timedelta(0))
            if colunas_pag_presentes:
                self.df[colunas_pag_presentes] = self.df[colunas_pag_presentes].fillna(pd.Timedelta(0))
            # ---------------------------

            print(f"✅ Dados carregados: {len(self.df)} registros")
            self._carregar_tabela_hora_voo()
            self._carregar_csv_primeira_versao()
            self._exibir_periodos_copiloto_e_valor()
            return True
            
        except Exception as e:
            print(f"❌ Erro ao carregar dados: {e}")
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

    # =========================================================================
    # MÉTODOS AUXILIARES – DEMONSTRATIVO DE PAGAMENTO
    # =========================================================================

    def _carregar_tabela_hora_voo(self):
        """Localiza e carrega TABELA_VALORES_HORA_VOO_2017_AZUL_ATUAL.csv"""
        nome_tabela = 'TABELA_VALORES_HORA_VOO_2017_AZUL_ATUAL.csv'
        diretorios_busca = [
            os.path.dirname(self.arquivo_csv),
            os.path.dirname(os.path.abspath(__file__)),
        ]
        for diretorio in diretorios_busca:
            caminho = os.path.join(diretorio, nome_tabela)
            if os.path.isfile(caminho):
                try:
                    self.df_tabela_hora = pd.read_csv(caminho)
                    print(f"✅ Tabela de hora de voo carregada: {caminho}")
                    return
                except Exception as e:
                    print(f"⚠️  Erro ao carregar tabela de hora de voo: {e}")
        print(f"⚠️  {nome_tabela} não encontrada. Demonstrativo de pagamento indisponível.")
        self.df_tabela_hora = None

    def _carregar_csv_primeira_versao(self):
        """Carrega CSV _PRIMEIRA_VERSAO para obter colunas AcVer/CAT."""
        try:
            dir_csv = os.path.dirname(self.arquivo_csv)
            nome_base = os.path.basename(self.arquivo_csv)
            prefixo = nome_base.split('_TEMPO_SOLO')[0]

            padrao_1 = os.path.join(dir_csv, f"{prefixo}_PRIMEIRA_VERSAO*.csv")
            candidatos = sorted(glob.glob(padrao_1))

            if not candidatos:
                padrao_2 = os.path.join(dir_csv, "*_PRIMEIRA_VERSAO*.csv")
                candidatos = sorted(glob.glob(padrao_2))

            if not candidatos:
                print("⚠️  CSV _PRIMEIRA_VERSAO não encontrado no diretório do arquivo selecionado.")
                self.df_primeira_versao = None
                return

            caminho = candidatos[-1]
            dfp = pd.read_csv(caminho)
            if 'Checkin' in dfp.columns:
                checkin_dt = pd.to_datetime(dfp['Checkin'], errors='coerce', dayfirst=True)
                dfp['Ano'] = checkin_dt.dt.year

            self.df_primeira_versao = dfp
            print(f"✅ CSV _PRIMEIRA_VERSAO carregado: {caminho}")

        except Exception as e:
            print(f"⚠️  Erro ao carregar CSV _PRIMEIRA_VERSAO: {e}")
            self.df_primeira_versao = None

    def _determinar_equipamento(self, acver):
        """Retorna o nome do equipamento a partir do valor da coluna AcVer.
        Regras:
          - Inicia com 'E'  → Ejet
          - Inicia com '32' → A320
          - Inicia com '33' → A330
          - Inicia com 'AT' → ATR
          - Inicia com 'B7' ou '73' → B737
          - Inicia com 'C2', 'CAR' ou valor = 'C208'/'CARAVAN' → Caravan
        """
        if pd.isna(acver) or str(acver).strip() == '':
            return None
        s = str(acver).strip().upper()
        if s.startswith('E'):
            return 'Ejet'
        if s.startswith('32'):
            return 'A320'
        if s.startswith('33'):
            return 'A330'
        if s.startswith('AT'):
            return 'ATR'
        if s.startswith('B7') or s.startswith('73'):
            return 'B737'
        if s.startswith('C2') or s.startswith('CAR') or s in ('C208', 'CARAVAN'):
            return 'Caravan'
        return None

    def _determinar_funcao(self, cat):
        """Retorna a função do aeronauta a partir da coluna CAT.
        Regras:
          - 'CA'                              → CMTE
          - 'CO','SO','FO','CP','2P','OFI'    → COPILOTO
          - 'CS','CM','AF','ASV','COM'        → COMISSARIO
        """
        if pd.isna(cat) or str(cat).strip() == '':
            return None
        s = str(cat).strip().upper()
        if s == 'CA':
            return 'CMTE'
        if s in ('CO', 'SO', 'FO', 'CP', '2P', 'OFI'):
            return 'COPILOTO'
        if s in ('CS', 'CM', 'AF', 'ASV', 'COM'):
            return 'COMISSARIO'
        return None

    def _obter_valor_hora(self, ano, equipamento, funcao):
        """Consulta Valor_Hora_Voo na tabela para (ano, equipamento, funcao).
        Se não encontrar para o ano, usa o ano válido mais próximo na tabela
        para o mesmo equipamento/função.
        Regra: COPILOTO = 60% do valor de CMTE (mesmo ano/equipamento).
        Retorna float ou None se não encontrado / não preenchido."""
        # Regra solicitada: COPILOTO = 60% do CMTE
        if funcao and 'COPILOTO' in str(funcao).upper():
            valor_cmte = self._obter_valor_hora(ano, equipamento, 'CMTE')
            if valor_cmte is not None:
                return round(valor_cmte * 0.60, 2)
            return None
        
        if self.df_tabela_hora is None or funcao is None:
            return None

        df_base = self.df_tabela_hora.copy()

        # Normalização defensiva para arquivo com layout reduzido/colunas deslocadas:
        # Exemplo observado: Ano,Equipamento,Funcao,Valor_Hora_Voo com linhas "2009,CMTE,61.37"
        # Nesse caso, Funcao vem como valor e Equipamento como função.
        if {'Equipamento', 'Funcao', 'Valor_Hora_Voo'}.issubset(df_base.columns):
            try:
                valor_col_vazia = df_base['Valor_Hora_Voo'].isna().all()
                funcao_numerica = pd.to_numeric(df_base['Funcao'], errors='coerce').notna().mean() > 0.8
                if valor_col_vazia and funcao_numerica:
                    df_base['Valor_Hora_Voo'] = df_base['Funcao']
                    df_base['Funcao'] = df_base['Equipamento']
                    df_base['Equipamento'] = ''
            except Exception:
                pass

        equipamento = str(equipamento).strip()
        funcao = str(funcao).strip().upper()

        # Filtra por função
        if 'Funcao' not in df_base.columns:
            return None
        df_func = df_base[df_base['Funcao'].astype(str).str.strip().str.upper() == funcao].copy()

        # Se houver coluna Equipamento preenchida, prioriza match por equipamento;
        # se não houver match, mantém fallback por função.
        df_ref = df_func
        if 'Equipamento' in df_func.columns:
            equip_series = df_func['Equipamento'].astype(str).str.strip()
            tem_equip_preenchido = equip_series.replace({'': None}).notna().any()
            if tem_equip_preenchido:
                df_eq = df_func[equip_series.str.upper() == equipamento.upper()].copy()
                if not df_eq.empty:
                    df_ref = df_eq

        if df_ref.empty:
            return None

        def _parse_valor(v):
            if pd.isna(v) or str(v).strip() == '':
                return None
            try:
                return float(str(v).replace(',', '.').replace(' ', ''))
            except (ValueError, TypeError):
                return None

        df_ref['ValorNum'] = df_ref['Valor_Hora_Voo'].apply(_parse_valor)
        df_ref = df_ref.dropna(subset=['ValorNum'])
        if df_ref.empty:
            return None

        ano = int(ano)

        # 1) Tenta ano exato
        exato = df_ref[df_ref['Ano'] == ano]
        if not exato.empty:
            return float(exato.iloc[0]['ValorNum'])

        # 2) Tenta último ano <= ano solicitado
        anteriores = df_ref[df_ref['Ano'] <= ano].sort_values('Ano', ascending=False)
        if not anteriores.empty:
            ano_usado = int(anteriores.iloc[0]['Ano'])
            valor = float(anteriores.iloc[0]['ValorNum'])
            print(f"⚠️  Valor para {ano}/{equipamento}/{funcao} não encontrado. Usando valor de {ano_usado}: R$ {valor:.2f}")
            return valor

        # 3) Se o ano solicitado for anterior ao início da tabela, usa o primeiro ano disponível
        posteriores = df_ref[df_ref['Ano'] > ano].sort_values('Ano', ascending=True)
        if not posteriores.empty:
            ano_usado = int(posteriores.iloc[0]['Ano'])
            valor = float(posteriores.iloc[0]['ValorNum'])
            print(f"⚠️  Valor para {ano}/{equipamento}/{funcao} não encontrado. Usando primeiro ano disponível ({ano_usado}): R$ {valor:.2f}")
            return valor

        return None

    def _exibir_periodos_copiloto_e_valor(self):
        """Exibe no console os períodos de COPILOTO e o valor-hora aplicável em cada período."""
        try:
            if not self.periodos_funcao:
                print("ℹ️  Períodos de função não disponíveis (Supabase sem histórico carregado).")
                return

            # Tenta obter equipamento predominante como referência para consulta de tabela
            equipamento_ref = None
            if self.df_primeira_versao is not None and 'AcVer' in self.df_primeira_versao.columns:
                equip_vals = self.df_primeira_versao['AcVer'].dropna().apply(self._determinar_equipamento).dropna()
                if not equip_vals.empty:
                    equipamento_ref = equip_vals.mode().iloc[0]
            if equipamento_ref is None and self.df is not None and 'AcVer' in self.df.columns:
                equip_vals = self.df['AcVer'].dropna().apply(self._determinar_equipamento).dropna()
                if not equip_vals.empty:
                    equipamento_ref = equip_vals.mode().iloc[0]

            def _eh_copiloto(nome_funcao):
                s = str(nome_funcao).upper()
                return ('COPILOTO' in s) or (' - FO' in s) or s.endswith('FO')

            periodos_copiloto = []
            for funcao, periodos in self.periodos_funcao.items():
                if _eh_copiloto(funcao):
                    for inicio, fim in periodos:
                        periodos_copiloto.append((funcao, inicio, fim))

            if not periodos_copiloto:
                print("ℹ️  Nenhum período de COPILOTO encontrado no histórico de funções.")
                return

            print("\n📌 PERÍODOS COMO COPILOTO E VALOR DA HORA")
            for funcao, inicio, fim in periodos_copiloto:
                ano_inicio = int(inicio.year)
                ano_fim = int(fim.year) if fim is not None else int(datetime.now().year)
                anos = list(range(ano_inicio, ano_fim + 1))

                valores = []
                for ano in anos:
                    vh = self._obter_valor_hora(ano, equipamento_ref, funcao)
                    if vh is not None:
                        valores.append((ano, vh))

                fim_txt = fim.strftime('%d/%m/%Y') if fim is not None else 'vigente'
                inicio_txt = inicio.strftime('%d/%m/%Y')
                print(f"  • Função: {funcao}")
                print(f"    Período: {inicio_txt} até {fim_txt}")

                if valores:
                    for ano, vh in valores:
                        print(f"    Valor hora ({ano}): {self._formatar_moeda(vh)}")
                else:
                    # Para COPILOTO, aplica regra de 60% do valor de CMTE
                    vh_padrao = self._obter_valor_hora(ano_inicio, equipamento_ref, 'COPILOTO')
                    print(f"    Valor hora no período: {self._formatar_moeda(vh_padrao)}")

        except Exception as e:
            print(f"⚠️  Erro ao exibir períodos de copiloto: {e}")

    def _timedelta_para_horas(self, td):
        """Converte timedelta para número decimal de horas. Aceita timedelta ou string."""
        import pandas as pd
        if pd.isna(td) or td == pd.Timedelta(0):
            return 0.0
        # Se for string, tenta converter para timedelta
        if isinstance(td, str):
            try:
                td = pd.to_timedelta(td)
            except Exception:
                return 0.0
        if pd.isna(td) or td == pd.Timedelta(0):
            return 0.0
        return td.total_seconds() / 3600.0

    def _formatar_moeda(self, valor):
        """Formata valor monetário no padrão brasileiro R$ 1.234,56"""
        if valor is None:
            return "---"
        try:
            if not math.isfinite(float(valor)):
                return "---"
        except (ValueError, TypeError):
            return "---"
        s = f"{valor:,.2f}"
        s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"R$ {s}"

    def _obter_fatores_poupanca_anuais(self, ano_inicial, ano_final):
        """Obtém fatores anuais da POUPANÇA a partir da API do Banco Central.

        Usa série SGS de rendimento mensal da poupança e compõe os meses para
        formar o fator anual: fator_ano = Π(1 + taxa_mensal/100).
        Retorna dict {ano: fator_anual}.
        """
        fatores = {}
        try:
            params = {
                'formato': 'json',
                'dataInicial': f'01/01/{int(ano_inicial)}',
                'dataFinal': f'31/12/{int(ano_final)}',
            }
            # Série mais usada para rendimento mensal da poupança: SGS 195.
            # Fallback em SGS 4390 para ambientes em que a 195 não esteja disponível.
            series_candidatas = [195, 4390]

            dados = None
            for cod in series_candidatas:
                try:
                    base_url = f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados'
                    url = f"{base_url}?{urllib.parse.urlencode(params)}"
                    req = urllib.request.Request(
                        url,
                        headers={
                            'Accept': 'application/json',
                            'User-Agent': 'Mozilla/5.0'
                        }
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        conteudo = resp.read().decode('utf-8')
                    tentativa = json.loads(conteudo)
                    if isinstance(tentativa, list) and len(tentativa) > 0:
                        dados = tentativa
                        print(f"✅ Série POUPANÇA carregada do Banco Central (SGS {cod}).")
                        break
                except Exception:
                    continue

            if not isinstance(dados, list):
                return fatores

            # Capturar a ÚLTIMA taxa de cada mês (fechamento mensal)
            # para evitar multiplicar observações diárias/repetidas.
            fechamento_mes = {}  # (ano, mes) -> (data_obj, taxa_mensal)
            for item in dados:
                data_str = str(item.get('data', '')).strip()  # dd/mm/yyyy
                valor_raw = str(item.get('valor', '')).strip()
                if not data_str or not valor_raw:
                    continue

                # Parse robusto: API pode vir com decimal em vírgula ou ponto.
                if ',' in valor_raw:
                    valor_str = valor_raw.replace('.', '').replace(',', '.')
                else:
                    valor_str = valor_raw.replace(' ', '')

                try:
                    data_obj = datetime.strptime(data_str, '%d/%m/%Y')
                    ano = data_obj.year
                    mes = data_obj.month
                    taxa_mensal = float(valor_str)
                except (ValueError, TypeError):
                    continue

                # Faixa de sanidade para POUPANÇA mensal (%): evita parse incorreto
                # que geraria fatores absurdos e valores infinitos.
                if taxa_mensal < -5 or taxa_mensal > 10:
                    continue

                chave = (ano, mes)
                if chave not in fechamento_mes or data_obj > fechamento_mes[chave][0]:
                    fechamento_mes[chave] = (data_obj, taxa_mensal)

            # Compor fator anual com os 12 (ou menos) fechamentos mensais disponíveis
            por_ano = {}
            for (ano, _mes), (_data, taxa_mensal) in fechamento_mes.items():
                fator_mensal = 1.0 + (taxa_mensal / 100.0)
                if fator_mensal <= 0:
                    continue
                por_ano.setdefault(ano, 1.0)
                por_ano[ano] *= fator_mensal

            # Sanidade adicional: evita fatores anuais absurdos por eventual dado inconsistente
            for ano, fator in list(por_ano.items()):
                if fator <= 0 or fator > 2.0:
                    print(f"⚠️  Fator anual POUPANÇA fora da faixa em {ano}: {fator:.6f}. Ignorando ano.")
                    por_ano.pop(ano, None)

            for ano in range(int(ano_inicial), int(ano_final) + 1):
                if ano in por_ano:
                    fatores[ano] = por_ano[ano]

            if fatores:
                print(f"✅ Fatores anuais POUPANÇA carregados via Banco Central ({min(fatores)}-{max(fatores)}).")
            else:
                print("⚠️  Não foi possível montar fatores anuais da POUPANÇA a partir do Banco Central.")

        except Exception as e:
            print(f"⚠️  Erro ao consultar POUPANÇA no Banco Central: {e}")

        return fatores

    def _fator_poupanca_composto(self, fatores_anuais, ano_origem, ano_destino):
        """Retorna fator composto da POUPANÇA de ano_origem até ano_destino (inclusive)."""
        fator = 1.0
        for ano in range(int(ano_origem), int(ano_destino) + 1):
            fator *= fatores_anuais.get(ano, 1.0)
        return fator

    def _gerar_quadro_pagamento(self, story, df_ano, ano, styles):
        """Gera o quadro DEMONSTRATIVO DE PAGAMENTO ao fim da seção do ano.

        Identifica equipamento e função pelo valor mais frequente nas linhas com
        tempo solo > 0 (colunas AcVer e CAT do CSV). Consulta o valor da hora na
        TABELA_VALORES_HORA_VOO e calcula o total monetário por período de pagamento.
        """
        if self.df_tabela_hora is None:
            return

        # Fonte de AcVer/CAT: prioriza o próprio df_ano; fallback para _PRIMEIRA_VERSAO
        fonte_df = None
        if 'AcVer' in df_ano.columns and 'CAT' in df_ano.columns:
            fonte_df = df_ano
        elif self.df_primeira_versao is not None and 'AcVer' in self.df_primeira_versao.columns and 'CAT' in self.df_primeira_versao.columns:
            if 'Ano' in self.df_primeira_versao.columns:
                fonte_df = self.df_primeira_versao[self.df_primeira_versao['Ano'] == int(ano)]
            else:
                fonte_df = self.df_primeira_versao

        if fonte_df is None or len(fonte_df) == 0:
            return

        # ----- Filtrar somente linhas com tempo solo > 0 -----
        colunas_solo = [
            'Tempo Solo Diurno', 'Tempo Solo Noturno',
            'Tempo Solo Especial Diurno', 'Tempo Solo Especial Noturno'
        ]
        # Converter para Timedelta para evitar erro de comparação
        for col in colunas_solo:
            if df_ano[col].dtype == 'object':
                df_ano[col] = pd.to_timedelta(df_ano[col], errors='coerce')
            df_ano[col] = df_ano[col].fillna(pd.Timedelta(0))
            df_ano[col] = df_ano[col].astype('timedelta64[ns]')
        mask_solo = df_ano[colunas_solo].sum(axis=1) > pd.Timedelta(0)
        df_solo = df_ano[mask_solo]

        # ----- Equipamento e função predominantes (moda) -----
        if fonte_df is df_ano and len(df_solo) > 0:
            base_equip_func = df_solo
        else:
            base_equip_func = fonte_df

        equip_vals = base_equip_func['AcVer'].dropna().apply(self._determinar_equipamento).dropna()
        cat_vals   = base_equip_func['CAT'].dropna().apply(self._determinar_funcao).dropna()
        equipamento = equip_vals.mode().iloc[0] if not equip_vals.empty else None
        funcao      = self.funcao_arquivo if self.funcao_arquivo else (cat_vals.mode().iloc[0] if not cat_vals.empty else None)

        # ----- Valor hora pela regra solicitada (função única vs múltiplas funções) -----
        valor_hora = self._calcular_valor_hora_ano_por_regras(
            df_ano=df_ano,
            ano=int(ano),
            equipamento_fallback=equipamento,
            funcao_fallback=funcao,
        )

        # Fallback final
        if valor_hora is None:
            valor_hora = self._obter_valor_hora(int(ano), equipamento, funcao)

        # ----- Somar horas com a mesma base do quadro RESUMO do ano -----
        # Importante: usar Tempo Solo* garante consistência com o quadro resumo,
        # inclusive para Especial Diurno/Noturno.
        def _td_sum(col):
            if col in df_ano.columns:
                td = df_ano[col].sum()
                return td if isinstance(td, pd.Timedelta) else pd.Timedelta(0)
            return pd.Timedelta(0)

        td_d  = _td_sum('Tempo Solo Diurno')
        td_n  = _td_sum('Tempo Solo Noturno')
        td_ed = _td_sum('Tempo Solo Especial Diurno')
        td_en = _td_sum('Tempo Solo Especial Noturno')

        h_d  = self._timedelta_para_horas(td_d)
        h_n  = self._timedelta_para_horas(td_n)
        h_ed = self._timedelta_para_horas(td_ed)
        h_en = self._timedelta_para_horas(td_en)
        td_total = td_d + td_n + td_ed + td_en

        # ----- Montar quadro comparativo de cenários (100%, 75%, 50%) -----
        equip_str = equipamento or "Não identificado"
        func_str  = funcao      or "Não identificada"

        info_style = ParagraphStyle(
            'DemPagInfo',
            parent=styles['Normal'],
            fontSize=8,
            spaceAfter=4,
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor('#444444')
        )

        story.append(Spacer(1, 0.5*cm))

        pag_title_style = ParagraphStyle(
            'DemPagTitleComp',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=4,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2e6b35')
        )
        story.append(Paragraph(
            f"<b>DEMONSTRATIVO COMPARATIVO DE PAGAMENTO (100% / 75% / 50%) - {int(ano)}</b>",
            pag_title_style
        ))

        vh_100 = valor_hora
        vh_75 = (valor_hora * 0.75) if valor_hora is not None else None
        vh_50 = (valor_hora * 0.50) if valor_hora is not None else None

        story.append(Paragraph(
            f"Equipamento: <b>{equip_str}</b>  |  "
            f"Função: <b>{func_str}</b>  |  "
            f"Hora 100%: <b>{self._formatar_moeda(vh_100)}</b>  |  "
            f"Hora 75%: <b>{self._formatar_moeda(vh_75)}</b>  |  "
            f"Hora 50%: <b>{self._formatar_moeda(vh_50)}</b>",
            info_style
        ))
        story.append(Spacer(1, 0.15*cm))

        def calc(h, vh):
            return h * vh if vh is not None else None

        # Horas efetivamente pagas (mesma lógica do quadro RESUMO -> TOTAL PAGAMENTO)
        td_d_pag = td_d
        td_n_pag = td_n * 2
        td_ed_pag = td_ed * 2
        td_en_pag = td_en * 2
        td_total_pag = td_d_pag + td_n_pag + td_ed_pag + td_en_pag

        h_d_pag = self._timedelta_para_horas(td_d_pag)
        h_n_pag = self._timedelta_para_horas(td_n_pag)
        h_ed_pag = self._timedelta_para_horas(td_ed_pag)
        h_en_pag = self._timedelta_para_horas(td_en_pag)
        h_total_pag = self._timedelta_para_horas(td_total_pag)

        linhas_base = [
            ('Pagamento Diurno', td_d_pag, h_d_pag),
            ('Pagamento Noturno', td_n_pag, h_n_pag),
            ('Pagamento Especial Diurno', td_ed_pag, h_ed_pag),
            ('Pagamento Especial Noturno', td_en_pag, h_en_pag),
            ('TOTAL', td_total_pag, h_total_pag),
        ]

        pag_data = [[
            'PERÍODO', 'HORAS PAG.', 'TOTAL 100%', 'TOTAL 75%', 'TOTAL 50%'
        ]]

        for nome, td, h in linhas_base:
            pag_data.append([
                nome,
                self._formatar_timedelta(td),
                self._formatar_moeda(calc(h, vh_100)),
                self._formatar_moeda(calc(h, vh_75)),
                self._formatar_moeda(calc(h, vh_50)),
            ])

        # Linhas de diferença econômica entre cenários (foco no total anual)
        total_100 = calc(h_total_pag, vh_100)
        total_75 = calc(h_total_pag, vh_75)
        total_50 = calc(h_total_pag, vh_50)

        diff_100_75 = (total_100 - total_75) if total_100 is not None and total_75 is not None else None
        diff_100_50 = (total_100 - total_50) if total_100 is not None and total_50 is not None else None

        pag_data.append([
            'Diferença 100% - 75%',
            '',
            self._formatar_moeda(diff_100_75),
            '',
            ''
        ])
        pag_data.append([
            'Diferença 100% - 50%',
            '',
            self._formatar_moeda(diff_100_50),
            '',
            ''
        ])

        pag_table = Table(pag_data, colWidths=[4.7*cm, 2.4*cm, 2.8*cm, 2.8*cm, 2.8*cm])
        pag_table.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, 0),  colors.HexColor('#2e6b35')),
            ('TEXTCOLOR',    (0, 0), (-1, 0),  colors.white),
            ('ALIGN',        (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN',        (0, 1), (0, -2),  'LEFT'),
            ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
            ('FONTSIZE',     (0, 0), (-1, 0),  8),
            ('FONTSIZE',     (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING',(0, 0), (-1, 0),  10),
            ('TOPPADDING',   (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
            ('BACKGROUND',   (0, 1), (-1, -2), colors.HexColor('#f0f7f0')),
            ('BACKGROUND',   (0, -1),(-1, -1), colors.HexColor('#c8e6c9')),
            ('FONTNAME',     (0, -1),(-1, -1), 'Helvetica-Bold'),
            ('FONTNAME',     (0, -2),(-1, -2), 'Helvetica-Bold'),
            ('BACKGROUND',   (0, -2),(-1, -2), colors.HexColor('#dff0d8')),
            ('GRID',         (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',  (0, 1), (0, -2),  8),
        ]))
        story.append(pag_table)

    # =========================================================================
    # MÉTODOS AUXILIARES – QUADROS DE PERÍODOS (HORAS EM SOLO ENTRE ETAPAS)
    # =========================================================================

    def _gerar_quadros_periodos_solo(self, story, styles):
        """Gera dois quadros de Horas em Solo entre Etapas para períodos específicos:
        1. Período 1: Novembro 2017 até o final do arquivo.
        2. Período 2: Data do último registro até 5 anos para trás.
        """
        if self.df is None or len(self.df) == 0:
            return

        # Converter coluna Checkin para datetime
        try:
            self.df['Checkin_dt'] = pd.to_datetime(self.df['Checkin'])
        except:
            return

        def _calcular_demonstrativo_periodo(df_periodo):
            """Calcula valores sem correção e com POUPANÇA para um período.
            Usa o mesmo método do quadro 'TODOS OS ANOS'."""
            if df_periodo is None or len(df_periodo) == 0:
                return None, None, None, None, None, None, None

            df_periodo = df_periodo.copy()
            if 'Ano' not in df_periodo.columns:
                if 'Checkin_dt' in df_periodo.columns:
                    df_periodo['Ano'] = pd.to_datetime(df_periodo['Checkin_dt'], errors='coerce').dt.year
                elif 'Checkin' in df_periodo.columns:
                    df_periodo['Ano'] = pd.to_datetime(df_periodo['Checkin'], errors='coerce', dayfirst=True).dt.year

            anos_int = sorted([int(a) for a in df_periodo['Ano'].dropna().unique().tolist()])
            if not anos_int:
                return None, None, None, None, None, None, None

            ano_min = min(anos_int)
            ano_max = max(anos_int)
            fatores_poupanca = self._obter_fatores_poupanca_anuais(ano_min, ano_max)

            total_100_sem = 0.0
            total_75_sem = 0.0
            total_50_sem = 0.0
            total_100_poupanca = 0.0
            total_75_poupanca = 0.0
            total_50_poupanca = 0.0

            # Valor-hora médio de suporte no período
            valor_horas_encontrados = []
            equip_geral = None
            func_geral = self.funcao_arquivo
            dfp_periodo = None

            if self.df_primeira_versao is not None and self.df_tabela_hora is not None:
                dfp_periodo = self.df_primeira_versao.copy()
                if 'Checkin_dt' not in dfp_periodo.columns and 'Checkin' in dfp_periodo.columns:
                    dfp_periodo['Checkin_dt'] = pd.to_datetime(dfp_periodo['Checkin'], errors='coerce', dayfirst=True)
                if 'Ano' not in dfp_periodo.columns and 'Checkin_dt' in dfp_periodo.columns:
                    dfp_periodo['Ano'] = dfp_periodo['Checkin_dt'].dt.year

                # Limitar ao mesmo intervalo de datas do período
                if 'Checkin_dt' in dfp_periodo.columns and 'Checkin_dt' in df_periodo.columns:
                    ini = pd.to_datetime(df_periodo['Checkin_dt'], errors='coerce').min()
                    fim = pd.to_datetime(df_periodo['Checkin_dt'], errors='coerce').max()
                    if pd.notna(ini) and pd.notna(fim):
                        dfp_periodo = dfp_periodo[(dfp_periodo['Checkin_dt'] >= ini) & (dfp_periodo['Checkin_dt'] <= fim)]

                if 'AcVer' in dfp_periodo.columns:
                    equip_vals_geral = dfp_periodo['AcVer'].dropna().apply(self._determinar_equipamento).dropna()
                    equip_geral = equip_vals_geral.mode().iloc[0] if not equip_vals_geral.empty else None

                if func_geral is None and 'CAT' in dfp_periodo.columns:
                    cat_vals_geral = dfp_periodo['CAT'].dropna().apply(self._determinar_funcao).dropna()
                    func_geral = cat_vals_geral.mode().iloc[0] if not cat_vals_geral.empty else None

                if 'AcVer' in dfp_periodo.columns and 'CAT' in dfp_periodo.columns and 'Ano' in dfp_periodo.columns:
                    dfp_periodo['Equipamento_Map'] = dfp_periodo['AcVer'].apply(self._determinar_equipamento)
                    if self.funcao_arquivo:
                        dfp_periodo['Funcao_Map'] = self.funcao_arquivo
                    else:
                        dfp_periodo['Funcao_Map'] = dfp_periodo['CAT'].apply(self._determinar_funcao)

                    combos = dfp_periodo[['Ano', 'Equipamento_Map', 'Funcao_Map']].dropna().drop_duplicates()
                    for _, r in combos.iterrows():
                        vh = self._obter_valor_hora(int(r['Ano']), r['Equipamento_Map'], r['Funcao_Map'])
                        if vh is not None:
                            valor_horas_encontrados.append(vh)

            valor_hora_medio = (sum(valor_horas_encontrados) / len(valor_horas_encontrados)) if valor_horas_encontrados else None

            for ano_ref in anos_int:
                df_ref = df_periodo[df_periodo['Ano'] == ano_ref]
                d_ref = df_ref['Tempo Solo Diurno'].sum()
                n_ref = df_ref['Tempo Solo Noturno'].sum()
                ed_ref = df_ref['Tempo Solo Especial Diurno'].sum()
                en_ref = df_ref['Tempo Solo Especial Noturno'].sum()

                td_pag_ref = d_ref + (n_ref * 2) + (ed_ref * 2) + (en_ref * 2)
                h_pag_ref = self._timedelta_para_horas(td_pag_ref)

                valor_hora_ano = None
                if dfp_periodo is not None and len(dfp_periodo) > 0 and 'Ano' in dfp_periodo.columns:
                    fonte_ano = dfp_periodo[dfp_periodo['Ano'] == int(ano_ref)]
                    if len(fonte_ano) > 0:
                        equip_vals_ano = fonte_ano['AcVer'].dropna().apply(self._determinar_equipamento).dropna() if 'AcVer' in fonte_ano.columns else pd.Series(dtype=object)
                        cat_vals_ano = fonte_ano['CAT'].dropna().apply(self._determinar_funcao).dropna() if 'CAT' in fonte_ano.columns else pd.Series(dtype=object)
                        equip_ano = equip_vals_ano.mode().iloc[0] if not equip_vals_ano.empty else None
                        func_ano = self.funcao_arquivo if self.funcao_arquivo else (cat_vals_ano.mode().iloc[0] if not cat_vals_ano.empty else None)
                        valor_hora_ano = self._calcular_valor_hora_ano_por_regras(
                            df_ano=df_ref,
                            ano=int(ano_ref),
                            equipamento_fallback=equip_ano,
                            funcao_fallback=func_ano,
                        )

                if valor_hora_ano is None:
                    valor_hora_ano = self._obter_valor_hora(int(ano_ref), equip_geral, func_geral)
                if valor_hora_ano is None:
                    valor_hora_ano = valor_hora_medio
                if valor_hora_ano is None:
                    continue

                base_100 = h_pag_ref * valor_hora_ano
                base_75 = base_100 * 0.75
                base_50 = base_100 * 0.50

                fator_composto = self._fator_poupanca_composto(fatores_poupanca, int(ano_ref), int(ano_max))

                total_100_sem += base_100
                total_75_sem += base_75
                total_50_sem += base_50

                total_100_poupanca += (base_100 * fator_composto)
                total_75_poupanca += (base_75 * fator_composto)
                total_50_poupanca += (base_50 * fator_composto)

            if total_100_sem == 0.0 and total_75_sem == 0.0 and total_50_sem == 0.0:
                return None, None, None, None, None, None, None

            td_pag_total = (
                df_periodo['Tempo Solo Diurno'].sum() +
                (df_periodo['Tempo Solo Noturno'].sum() * 2) +
                (df_periodo['Tempo Solo Especial Diurno'].sum() * 2) +
                (df_periodo['Tempo Solo Especial Noturno'].sum() * 2)
            )

            return td_pag_total, total_100_sem, total_75_sem, total_50_sem, total_100_poupanca, total_75_poupanca, total_50_poupanca

        # ===== PERÍODO 1: Novembro 2017 até EOF =====
        data_inicio_p1 = pd.Timestamp(year=2017, month=11, day=1)
        data_fim_p1 = self.df['Checkin_dt'].max()
        
        if pd.isna(data_fim_p1) or data_fim_p1 < data_inicio_p1:
            data_fim_p1 = pd.Timestamp.now()

        # Filtrar dados para período 1
        df_p1 = self.df[(self.df['Checkin_dt'] >= data_inicio_p1) & (self.df['Checkin_dt'] <= data_fim_p1)]
        
        if not df_p1.empty:
            # Calcular totais para período 1
            total_diurno_p1 = df_p1['Tempo Solo Diurno'].sum()
            total_noturno_p1 = df_p1['Tempo Solo Noturno'].sum()
            total_espec_diurno_p1 = df_p1['Tempo Solo Especial Diurno'].sum()
            total_espec_noturno_p1 = df_p1['Tempo Solo Especial Noturno'].sum()
            total_geral_p1 = total_diurno_p1 + total_noturno_p1 + total_espec_diurno_p1 + total_espec_noturno_p1

            # Calcular com multiplicadores (igual lógica dos quadros)
            total_diurno_calc_p1 = total_diurno_p1 + (total_espec_diurno_p1 * 2)
            total_noturno_calc_p1 = (total_noturno_p1 * 2) + (total_espec_noturno_p1 * 2)
            total_calc_p1 = total_diurno_calc_p1 + total_noturno_calc_p1

            # Montar quadro período 1
            quadro_p1_titulo = ParagraphStyle(
                'QuadroP1Titulo',
                parent=styles['Normal'],
                fontSize=10,
                spaceAfter=6,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                textColor=colors.HexColor('#0b5394')
            )
            
            data_inicio_str = data_inicio_p1.strftime('%d/%m/%Y')
            data_fim_str = data_fim_p1.strftime('%d/%m/%Y')
            story.append(Paragraph(
                f"<b>HORAS EM SOLO ENTRE ETAPAS - Período: {data_inicio_str} até {data_fim_str}</b>",
                quadro_p1_titulo
            ))
            story.append(Spacer(1, 0.2*cm))

            quadro_p1_data = [
                ['PERÍODO', 'DIURNO', 'NOTURNO', 'TOTAL\nSIMPLES', 'TOTAL\nPAGAMENTO'],
                ['Tempo Solo Total', 
                 self._formatar_timedelta(total_diurno_p1),
                 self._formatar_timedelta(total_noturno_p1),
                 self._formatar_timedelta(total_diurno_p1 + total_noturno_p1),
                 self._formatar_timedelta(total_diurno_calc_p1 + total_noturno_calc_p1)],
                ['Tempo Solo Especial', 
                 self._formatar_timedelta(total_espec_diurno_p1),
                 self._formatar_timedelta(total_espec_noturno_p1),
                 self._formatar_timedelta(total_espec_diurno_p1 + total_espec_noturno_p1),
                 self._formatar_timedelta((total_espec_diurno_p1 * 2) + (total_espec_noturno_p1 * 2))],
                ['TOTAL GERAL',
                 self._formatar_timedelta(total_diurno_p1 + total_espec_diurno_p1),
                 self._formatar_timedelta(total_noturno_p1 + total_espec_noturno_p1),
                 self._formatar_timedelta(total_geral_p1),
                 self._formatar_timedelta(total_calc_p1)]
            ]

            quadro_p1_table = Table(quadro_p1_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm, 3*cm])
            quadro_p1_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b5394')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#cfe2f3')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#9fc5f8')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(quadro_p1_table)
            story.append(Spacer(1, 0.4*cm))

            # Aplicar mesmo método financeiro do quadro "TODOS OS ANOS"
            td_pag_p1, sem_100_p1, sem_75_p1, sem_50_p1, poup_100_p1, poup_75_p1, poup_50_p1 = _calcular_demonstrativo_periodo(df_p1)

            story.append(Spacer(1, 0.1*cm))
            quadro_p1_valores_data = [
                ['CENÁRIO', 'HORAS PAGAS (TOTAL)', 'VALOR SEM CORREÇÃO', 'VALOR COM POUPANÇA'],
                ['100%', self._formatar_timedelta(td_pag_p1) if td_pag_p1 is not None else '---', self._formatar_moeda(sem_100_p1), self._formatar_moeda(poup_100_p1)],
                ['75%', self._formatar_timedelta(td_pag_p1) if td_pag_p1 is not None else '---', self._formatar_moeda(sem_75_p1), self._formatar_moeda(poup_75_p1)],
                ['50%', self._formatar_timedelta(td_pag_p1) if td_pag_p1 is not None else '---', self._formatar_moeda(sem_50_p1), self._formatar_moeda(poup_50_p1)],
            ]
            quadro_p1_valores_table = Table(quadro_p1_valores_data, colWidths=[2.6*cm, 3.8*cm, 4.5*cm, 4.5*cm])
            quadro_p1_valores_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e6b35')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f7f0')),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(quadro_p1_valores_table)
            story.append(Spacer(1, 0.4*cm))

        # ===== PERÍODO 2: Último registro até 5 anos atrás =====
        data_ultima = self.df['Checkin_dt'].max()
        
        if not pd.isna(data_ultima):
            data_inicio_p2 = data_ultima - pd.DateOffset(years=5)
            
            # Filtrar dados para período 2
            df_p2 = self.df[(self.df['Checkin_dt'] >= data_inicio_p2) & (self.df['Checkin_dt'] <= data_ultima)]
            
            if not df_p2.empty:
                # Calcular totais para período 2
                total_diurno_p2 = df_p2['Tempo Solo Diurno'].sum()
                total_noturno_p2 = df_p2['Tempo Solo Noturno'].sum()
                total_espec_diurno_p2 = df_p2['Tempo Solo Especial Diurno'].sum()
                total_espec_noturno_p2 = df_p2['Tempo Solo Especial Noturno'].sum()
                total_geral_p2 = total_diurno_p2 + total_noturno_p2 + total_espec_diurno_p2 + total_espec_noturno_p2

                # Calcular com multiplicadores
                total_diurno_calc_p2 = total_diurno_p2 + (total_espec_diurno_p2 * 2)
                total_noturno_calc_p2 = (total_noturno_p2 * 2) + (total_espec_noturno_p2 * 2)
                total_calc_p2 = total_diurno_calc_p2 + total_noturno_calc_p2

                # Montar quadro período 2
                quadro_p2_titulo = ParagraphStyle(
                    'QuadroP2Titulo',
                    parent=styles['Normal'],
                    fontSize=10,
                    spaceAfter=6,
                    alignment=TA_CENTER,
                    fontName='Helvetica-Bold',
                    textColor=colors.HexColor('#b45f06')
                )
                
                data_inicio_p2_str = data_inicio_p2.strftime('%d/%m/%Y')
                data_ultima_str = data_ultima.strftime('%d/%m/%Y')
                story.append(Paragraph(
                    f"<b>HORAS EM SOLO ENTRE ETAPAS - Período: {data_inicio_p2_str} até {data_ultima_str} (últimos 5 anos)</b>",
                    quadro_p2_titulo
                ))
                story.append(Spacer(1, 0.2*cm))

                quadro_p2_data = [
                    ['PERÍODO', 'DIURNO', 'NOTURNO', 'TOTAL\nSIMPLES', 'TOTAL\nPAGAMENTO'],
                    ['Tempo Solo Total', 
                     self._formatar_timedelta(total_diurno_p2),
                     self._formatar_timedelta(total_noturno_p2),
                     self._formatar_timedelta(total_diurno_p2 + total_noturno_p2),
                     self._formatar_timedelta(total_diurno_calc_p2 + total_noturno_calc_p2)],
                    ['Tempo Solo Especial', 
                     self._formatar_timedelta(total_espec_diurno_p2),
                     self._formatar_timedelta(total_espec_noturno_p2),
                     self._formatar_timedelta(total_espec_diurno_p2 + total_espec_noturno_p2),
                     self._formatar_timedelta((total_espec_diurno_p2 * 2) + (total_espec_noturno_p2 * 2))],
                    ['TOTAL GERAL',
                     self._formatar_timedelta(total_diurno_p2 + total_espec_diurno_p2),
                     self._formatar_timedelta(total_noturno_p2 + total_espec_noturno_p2),
                     self._formatar_timedelta(total_geral_p2),
                     self._formatar_timedelta(total_calc_p2)]
                ]

                quadro_p2_table = Table(quadro_p2_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm, 3*cm])
                quadro_p2_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#b45f06')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('TOPPADDING', (0, 1), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                    ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#f4ccb4')),
                    ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8a87c')),
                    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                
                story.append(quadro_p2_table)
                story.append(Spacer(1, 0.4*cm))

                # Aplicar mesmo método financeiro do quadro "TODOS OS ANOS"
                td_pag_p2, sem_100_p2, sem_75_p2, sem_50_p2, poup_100_p2, poup_75_p2, poup_50_p2 = _calcular_demonstrativo_periodo(df_p2)

                story.append(Spacer(1, 0.1*cm))
                quadro_p2_valores_data = [
                    ['CENÁRIO', 'HORAS PAGAS (TOTAL)', 'VALOR SEM CORREÇÃO', 'VALOR COM POUPANÇA'],
                    ['100%', self._formatar_timedelta(td_pag_p2) if td_pag_p2 is not None else '---', self._formatar_moeda(sem_100_p2), self._formatar_moeda(poup_100_p2)],
                    ['75%', self._formatar_timedelta(td_pag_p2) if td_pag_p2 is not None else '---', self._formatar_moeda(sem_75_p2), self._formatar_moeda(poup_75_p2)],
                    ['50%', self._formatar_timedelta(td_pag_p2) if td_pag_p2 is not None else '---', self._formatar_moeda(sem_50_p2), self._formatar_moeda(poup_50_p2)],
                ]
                quadro_p2_valores_table = Table(quadro_p2_valores_data, colWidths=[2.6*cm, 3.8*cm, 4.5*cm, 4.5*cm])
                quadro_p2_valores_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e6b35')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f7f0')),
                    ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                story.append(quadro_p2_valores_table)
                story.append(Spacer(1, 0.4*cm))

    # =========================================================================

    def gerar_relatorio_pdf(self, nome_arquivo="relatorio_tempo_solo_detalhado.pdf"):
        """Gera o relatório PDF completo"""
        if not self.carregar_dados():
            return False
        
        # Se não há registros, gerar relatório vazio com marca d'água
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
        
        story.append(Paragraph("EXTRATO DEMONSTRATIVO DETALHADO DE HORAS EM SOLO", titulo_style))
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
        self.df['Ano'] = pd.to_datetime(self.df['Checkin']).dt.year
        
        # Calcular totais gerais
        total_diurno_geral = self.df['Tempo Solo Diurno'].sum()
        total_noturno_geral = self.df['Tempo Solo Noturno'].sum()
        total_especial_diurno_geral = self.df['Tempo Solo Especial Diurno'].sum()
        total_especial_noturno_geral = self.df['Tempo Solo Especial Noturno'].sum()
        
        total_especial_geral = total_especial_diurno_geral + total_especial_noturno_geral
        total_geral_geral = total_diurno_geral + total_noturno_geral
        
        # Agrupar dados por ano
        anos = sorted(self.df['Ano'].unique())
        
        # ========================================
        # CRIAR ÍNDICE REMISSIVO POR ANO
        # ========================================
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
            # Adicionar âncora no índice para permitir retorno
            story.append(Paragraph('<a name="indice"/>ÍNDICE REMISSIVO - ANOS', indice_style))
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
                '<i>Observação: Estão sendo consideradas datas após a publicação da Lei 13.475.</i>',
                obs_style
            ))
            story.append(Spacer(1, 0.3*cm))
            
            # Criar tabela de índice
            indice_data = [['ANO', 'DESCRIÇÃO']]
            for ano in anos:
                if pd.isna(ano):
                    continue
                ano_int = int(ano)
                # Link interno para a seção do ano usando bookmark
                link_text = f'<link href="#ano_{ano_int}" color="blue"><u>Ano {ano_int}</u></link>'
                indice_data.append([
                    Paragraph(link_text, styles['Normal']),
                    Paragraph(f'Detalhamento de Tempo em Solo - {ano_int}', styles['Normal'])
                ])

            # Link para a seção final de totalizações (quando houver mais de um ano)
            if len(anos) > 1:
                link_total = '<link href="#totalizacoes" color="blue"><u>Totalizações</u></link>'
                indice_data.append([
                    Paragraph(link_total, styles['Normal']),
                    Paragraph('Resumo Geral e Demonstrativo Comparativo - Todos os Anos', styles['Normal'])
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
            df_ano = self.df[self.df['Ano'] == ano]
            # Calcular totais do ano
            total_diurno = df_ano['Tempo Solo Diurno'].sum()
            total_noturno = df_ano['Tempo Solo Noturno'].sum()
            total_especial_diurno = df_ano['Tempo Solo Especial Diurno'].sum()
            total_especial_noturno = df_ano['Tempo Solo Especial Noturno'].sum()
            total_pag_especial_diurno = df_ano['Pagamento Especial Diurno'].sum()
            total_pag_especial_noturno = df_ano['Pagamento Especial Noturno'].sum()
            total_especial = total_especial_diurno + total_especial_noturno
            total_geral = total_diurno + total_noturno
            # Calcular totais com multiplicadores
            # Diurno normal = 1x, Noturno normal = 2x, Especial Diurno = 2x, Especial Noturno = 2x
            total_diurno_calculado = total_diurno + (total_especial_diurno * 2)
            total_noturno_calculado = (total_noturno * 2) + (total_especial_noturno * 3)
            total_geral_calculado = total_diurno_calculado + total_noturno_calculado
            
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
            # Adicionar bookmark/âncora para este ano (para links do índice)
            story.append(Paragraph(f'<a name="ano_{int(ano)}"/><b>ANO: {int(ano)}</b>', ano_style))
            story.append(Spacer(1, 0.3*cm))
            
            # Tabela de Resumo do Ano
            resumo_data = [
                ['CATEGORIA', 'DIURNO', 'NOTURNO', 'TOTAL\nSIMPLES', 'TOTAL\nPAGAMENTO'],
                ['Tempo Solo Total', 
                 self._formatar_timedelta(total_diurno),
                 self._formatar_timedelta(total_noturno),
                 self._formatar_timedelta(total_geral),
                 self._formatar_timedelta(total_diurno + (total_noturno * 2))],
                ['Tempo Solo Especial', 
                 self._formatar_timedelta(total_especial_diurno),
                 self._formatar_timedelta(total_especial_noturno),
                 self._formatar_timedelta(total_especial),
                 self._formatar_timedelta((total_especial_diurno * 2) + (total_especial_noturno * 3))],
                ['SOMATÓRIA', 
                  self._formatar_timedelta(total_diurno + total_especial_diurno),
                  self._formatar_timedelta(total_noturno + total_especial_noturno),
                 self._formatar_timedelta(total_geral + total_especial),
                 self._formatar_timedelta(total_geral_calculado)]
            ]
            
            resumo_table = Table(resumo_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm, 3*cm])
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
            
            # Preparar dados detalhados do ano
            detalhes_data = [['DATA', 'ORIGEM-DESTINO', 'DIURNO', 'NOTURNO', 
                              'ESPECIAL\nDIURNO', 'ESPECIAL\nNOTURNO', 'TOTAL']]
            
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
                    dep_valor = row.get('Dep', '')
                    arr_valor = row.get('Arr', '')
                    if pd.isna(dep_valor) or str(dep_valor).lower() in ['nan', 'none', '']:
                        dep_valor = ''
                    else:
                        dep_valor = str(dep_valor).strip()
                    if pd.isna(arr_valor) or str(arr_valor).lower() in ['nan', 'none', '']:
                        arr_valor = ''
                    else:
                        arr_valor = str(arr_valor).strip()
                    origem_destino = f"{dep_valor}-{arr_valor}"
                d = self._formatar_timedelta(row['Tempo Solo Diurno'])
                n = self._formatar_timedelta(row['Tempo Solo Noturno'])
                ed = self._formatar_timedelta(row['Tempo Solo Especial Diurno'])
                en = self._formatar_timedelta(row['Tempo Solo Especial Noturno'])
                # Filtra registros com tempo solo total nulo ou zero
                tempo_total = (
                    row['Tempo Solo Diurno'] +
                    row['Tempo Solo Noturno'] +
                    row['Tempo Solo Especial Diurno'] +
                    row['Tempo Solo Especial Noturno']
                )
                if pd.isna(tempo_total) or tempo_total == pd.Timedelta(0):
                    continue
                total_linha = (
                    row['Tempo Solo Diurno'] +
                    row['Tempo Solo Noturno'] +
                    row['Tempo Solo Especial Diurno'] +
                    row['Tempo Solo Especial Noturno']
                )

                detalhes_data.append([
                    data_str,
                    origem_destino,
                    d, n, ed, en,
                    self._formatar_timedelta(total_linha)
                ])
            
            # Adicionar linha de totais do ano
            total_detalhamento = (
                total_diurno +
                total_noturno +
                total_especial_diurno +
                total_especial_noturno
            )
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
            
            # Demonstrativo de Pagamento do ano
            self._gerar_quadro_pagamento(story, df_ano, ano, styles)

            # Link para retornar ao índice
            story.append(Spacer(1, 0.3*cm))
            retorno_style = ParagraphStyle(
                'RetornoIndice',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#1f4788'),
                alignment=TA_RIGHT
            )
            story.append(Paragraph('<link href="#indice" color="blue">↑ Voltar ao Índice</link>', retorno_style))
            
            # Quebra de página entre anos (exceto no último)
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
            story.append(Paragraph('<a name="totalizacoes"/>RESUMO GERAL - TODOS OS ANOS', resumo_geral_style))
            story.append(Spacer(1, 0.5*cm))
            
            # Calcular totais com multiplicadores
            total_diurno_calc_geral = total_diurno_geral + (total_especial_diurno_geral * 2)
            total_noturno_calc_geral = (total_noturno_geral * 2) + (total_especial_noturno_geral * 3)
            total_calc_geral = total_diurno_calc_geral + total_noturno_calc_geral
            
            resumo_geral_data = [
                ['CATEGORIA', 'DIURNO', 'NOTURNO', 'TOTAL\nSIMPLES', 'TOTAL\nPAGAMENTO'],
                ['Tempo Solo Total', 
                 self._formatar_timedelta(total_diurno_geral),
                 self._formatar_timedelta(total_noturno_geral),
                 self._formatar_timedelta(total_geral_geral),
                 self._formatar_timedelta(total_diurno_geral + (total_noturno_geral * 2))],
                ['Tempo Solo Especial', 
                 self._formatar_timedelta(total_especial_diurno_geral),
                 self._formatar_timedelta(total_especial_noturno_geral),
                 self._formatar_timedelta(total_especial_geral),
                 self._formatar_timedelta((total_especial_diurno_geral * 2) + (total_especial_noturno_geral * 3))],
                ['SOMATÓRIA',
                  self._formatar_timedelta(total_diurno_geral + total_especial_diurno_geral),
                  self._formatar_timedelta(total_noturno_geral + total_especial_noturno_geral),
                 self._formatar_timedelta(total_geral_geral + total_especial_geral),
                 self._formatar_timedelta(total_calc_geral)]
            ]
            
            resumo_geral_table = Table(resumo_geral_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm, 3*cm])
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

            # ================================================================
            # DEMONSTRATIVO COMPARATIVO DE PAGAMENTO - TODOS OS ANOS
            # ================================================================
            story.append(Spacer(1, 0.5*cm))

            comp_geral_style = ParagraphStyle(
                'CompGeralPagamento',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#2e6b35'),
                spaceAfter=6,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph(
                "<b>DEMONSTRATIVO COMPARATIVO DE PAGAMENTO (100% / 75% / 50%) - TODOS OS ANOS</b>",
                comp_geral_style
            ))

            # Quadro resumido de valores totais (composição financeira por POUPANÇA)
            h_total_pag_geral = self._timedelta_para_horas(total_calc_geral)

            valor_horas_encontrados = []
            if self.df_primeira_versao is not None and self.df_tabela_hora is not None:
                dfp = self.df_primeira_versao.copy()
                if 'Ano' not in dfp.columns and 'Checkin' in dfp.columns:
                    checkin_dt = pd.to_datetime(dfp['Checkin'], errors='coerce', dayfirst=True)
                    dfp['Ano'] = checkin_dt.dt.year

                if 'AcVer' in dfp.columns and 'CAT' in dfp.columns and 'Ano' in dfp.columns:
                    dfp['Equipamento_Map'] = dfp['AcVer'].apply(self._determinar_equipamento)
                    # Prioriza função identificada pelo nome do arquivo (regra do usuário).
                    # Fallback: função derivada da CAT.
                    if self.funcao_arquivo:
                        dfp['Funcao_Map'] = self.funcao_arquivo
                    else:
                        dfp['Funcao_Map'] = dfp['CAT'].apply(self._determinar_funcao)
                    dfp = dfp.dropna(subset=['Equipamento_Map', 'Funcao_Map', 'Ano'])

                    combos = dfp[['Ano', 'Equipamento_Map', 'Funcao_Map']].drop_duplicates()
                    for _, r in combos.iterrows():
                        vh = self._obter_valor_hora(int(r['Ano']), r['Equipamento_Map'], r['Funcao_Map'])
                        if vh is not None:
                            valor_horas_encontrados.append(vh)

            valor_hora_medio = (sum(valor_horas_encontrados) / len(valor_horas_encontrados)) if valor_horas_encontrados else None

            # Montar valor base por ano (sem correção), depois compor POUPANÇA ano a ano
            anos_int = sorted([int(a) for a in anos])
            ano_min = min(anos_int)
            ano_max = max(anos_int)

            fatores_poupanca = self._obter_fatores_poupanca_anuais(ano_min, ano_max)

            total_100_sem = 0.0
            total_75_sem = 0.0
            total_50_sem = 0.0
            total_100_poupanca = 0.0
            total_75_poupanca = 0.0
            total_50_poupanca = 0.0
            fatores_compostos_por_ano = {}

            # Predominância geral como fallback adicional (evita quadro vazio)
            equip_geral = None
            func_geral = self.funcao_arquivo
            if self.df_primeira_versao is not None:
                if 'AcVer' in self.df_primeira_versao.columns:
                    equip_vals_geral = self.df_primeira_versao['AcVer'].dropna().apply(self._determinar_equipamento).dropna()
                    equip_geral = equip_vals_geral.mode().iloc[0] if not equip_vals_geral.empty else None
                if func_geral is None and 'CAT' in self.df_primeira_versao.columns:
                    cat_vals_geral = self.df_primeira_versao['CAT'].dropna().apply(self._determinar_funcao).dropna()
                    func_geral = cat_vals_geral.mode().iloc[0] if not cat_vals_geral.empty else None

            for ano_ref in anos_int:
                df_ref = self.df[self.df['Ano'] == ano_ref]
                d_ref = df_ref['Tempo Solo Diurno'].sum()
                n_ref = df_ref['Tempo Solo Noturno'].sum()
                ed_ref = df_ref['Tempo Solo Especial Diurno'].sum()
                en_ref = df_ref['Tempo Solo Especial Noturno'].sum()

                td_pag_ref = d_ref + (n_ref * 2) + (ed_ref * 2) + (en_ref * 2)
                h_pag_ref = self._timedelta_para_horas(td_pag_ref)

                # valor hora do ano pela regra de função única/múltiplas funções
                valor_hora_ano = None
                if self.df_primeira_versao is not None and self.df_tabela_hora is not None and 'Ano' in self.df_primeira_versao.columns:
                    fonte_ano = self.df_primeira_versao[self.df_primeira_versao['Ano'] == int(ano_ref)]
                    if len(fonte_ano) > 0:
                        equip_vals_ano = fonte_ano['AcVer'].dropna().apply(self._determinar_equipamento).dropna() if 'AcVer' in fonte_ano.columns else pd.Series(dtype=object)
                        cat_vals_ano = fonte_ano['CAT'].dropna().apply(self._determinar_funcao).dropna() if 'CAT' in fonte_ano.columns else pd.Series(dtype=object)
                        equip_ano = equip_vals_ano.mode().iloc[0] if not equip_vals_ano.empty else None
                        func_ano = self.funcao_arquivo if self.funcao_arquivo else (cat_vals_ano.mode().iloc[0] if not cat_vals_ano.empty else None)
                        valor_hora_ano = self._calcular_valor_hora_ano_por_regras(
                            df_ano=df_ref,
                            ano=int(ano_ref),
                            equipamento_fallback=equip_ano,
                            funcao_fallback=func_ano,
                        )

                # fallback por predominância geral (tabela por ano + equip/função)
                if valor_hora_ano is None and self.df_tabela_hora is not None:
                    valor_hora_ano = self._obter_valor_hora(int(ano_ref), equip_geral, func_geral)

                if valor_hora_ano is None:
                    valor_hora_ano = valor_hora_medio

                if valor_hora_ano is None:
                    continue

                base_100 = h_pag_ref * valor_hora_ano
                base_75 = base_100 * 0.75
                base_50 = base_100 * 0.50

                fator_composto = self._fator_poupanca_composto(fatores_poupanca, int(ano_ref), int(ano_max))
                fatores_compostos_por_ano[int(ano_ref)] = fator_composto

                total_100_sem += base_100
                total_75_sem += base_75
                total_50_sem += base_50

                total_100_poupanca += (base_100 * fator_composto)
                total_75_poupanca += (base_75 * fator_composto)
                total_50_poupanca += (base_50 * fator_composto)

            # Se não houve base calculada, manter como não disponível
            if total_100_sem == 0.0 and total_75_sem == 0.0 and total_50_sem == 0.0:
                total_100_sem = None
                total_75_sem = None
                total_50_sem = None
                total_100_poupanca = None
                total_75_poupanca = None
                total_50_poupanca = None

            story.append(Spacer(1, 0.15*cm))
            quadro_valores_data = [
                ['CENÁRIO', 'HORAS PAGAS (TOTAL)', 'VALOR SEM CORREÇÃO', 'VALOR COM POUPANÇA'],
                ['100%', self._formatar_timedelta(total_calc_geral), self._formatar_moeda(total_100_sem), self._formatar_moeda(total_100_poupanca)],
                ['75%', self._formatar_timedelta(total_calc_geral), self._formatar_moeda(total_75_sem), self._formatar_moeda(total_75_poupanca)],
                ['50%', self._formatar_timedelta(total_calc_geral), self._formatar_moeda(total_50_sem), self._formatar_moeda(total_50_poupanca)],
            ]

            quadro_valores_table = Table(quadro_valores_data, colWidths=[2.6*cm, 3.8*cm, 4.5*cm, 4.5*cm])
            quadro_valores_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e6b35')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f7f0')),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(quadro_valores_table)
            story.append(Spacer(1, 0.2*cm))

            # Quadro de auditoria da POUPANÇA (ano a ano)
            def _fmt_perc(v):
                if v is None:
                    return '---'
                return f"{v:.4f}".replace('.', ',') + '%'

            auditoria_poupanca_data = [['ANO', 'POUPANÇA ANUAL', f'FATOR ACUMULADO ATÉ {ano_max}']]
            for ano_ref in anos_int:
                fator_ano = fatores_poupanca.get(int(ano_ref))
                fator_acum = fatores_compostos_por_ano.get(int(ano_ref))

                poupanca_anual_pct = ((fator_ano - 1.0) * 100.0) if fator_ano is not None else None
                fator_acum_pct = ((fator_acum - 1.0) * 100.0) if fator_acum is not None else None

                auditoria_poupanca_data.append([
                    str(int(ano_ref)),
                    _fmt_perc(poupanca_anual_pct),
                    _fmt_perc(fator_acum_pct)
                ])

            auditoria_poupanca_table = Table(auditoria_poupanca_data, colWidths=[2.6*cm, 5.0*cm, 8.3*cm])
            auditoria_poupanca_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#eef4ff')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            story.append(auditoria_poupanca_table)
            story.append(Spacer(1, 0.5*cm))

            # Adicionar quadros de períodos (Horas em Solo entre Etapas)
            self._gerar_quadros_periodos_solo(story, styles)

            obs_geral_style = ParagraphStyle(
                'ObsCompGeralPagamento',
                parent=styles['Normal'],
                fontSize=8.5,
                leading=11,
                spaceAfter=0,
                alignment=TA_LEFT,
                fontName='Helvetica',
                textColor=colors.HexColor('#333333')
            )
            obs_titulo_style = ParagraphStyle(
                'ObsCompGeralPagamentoTitulo',
                parent=styles['Normal'],
                fontSize=9,
                alignment=TA_LEFT,
                fontName='Helvetica-Bold',
                textColor=colors.HexColor('#8a6d1a')
            )

            obs_titulo = Paragraph("⚠️ OBSERVAÇÕES IMPORTANTES", obs_titulo_style)
            obs_texto = Paragraph(
                "Os valores aqui demonstrados não estão com as correções aplicadas "
                "pela Justiça do Trabalho da maneira correta; foi aplicada apenas a "
                "correção da POUPANÇA. Estamos efetuando os cálculos corretos utilizando "
                "a ferramenta da JT PjeCalc e postaremos aqui ao finalizar os cálculos. "
                "Então vamos utilizar o valor da POUPANÇA ano a ano provisoriamente. "
                "Aqui os cálculos foram feitos para os Tempos em Solo entre Etapas a partir "
                "da publicação da lei. Poderemos ter a interpretação de que o direito será "
                "dos últimos 5 (cinco) anos; portanto, teremos que ajustar os valores a serem "
                "pagos por hora em solo, o período e a correção adotada pela Justiça do "
                "Trabalho. Isso poderemos fazer muito rapidamente ao conhecermos esses valores. "
                "Nestes valores não estão computados os efeitos sobre os 13 salários, férias, "
                "FGTS, verbas rescisórias, etc, tudo terá que ser devidamente inserido nos "
                "cálculos finais. "
                "Dados e valores aqui utilizados são oriundos do arquivo das escalas que a "
                "empresa forneceu ao aeronauta; erros que por ventura existam no arquivo "
                "original são entendidos como dados e valores verdadeiros, o sistema não "
                "corrige nada nesta fase.",
                obs_geral_style
            )

            obs_box = Table([[obs_titulo], [obs_texto]], colWidths=[15.4*cm])
            obs_box.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff8e1')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d4a017')),
                ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.HexColor('#d4a017')),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))

            story.append(Spacer(1, 0.1*cm))
            story.append(obs_box)

        
        # Gerar PDF
        try:
            doc.build(story)
            print(f"\n✅ Relatório gerado com sucesso!")
            return True
        except Exception as e:
            print(f"❌ Erro ao gerar PDF: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _gerar_relatorio_vazio(self, nome_arquivo):
        """Gera relatório vazio com marca d'água diagonal"""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            
            # Criar canvas
            c = canvas.Canvas(nome_arquivo, pagesize=A4)
            width, height = A4
            
            # Título principal
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(colors.darkblue)
            c.drawCentredString(width/2, height - 100, "EXTRATO DEMONSTRATIVO DETALHADO DE HORAS EM SOLO")
            c.drawCentredString(width/2, height - 120, "DIURNAS, NOTURNAS E ESPECIAIS")
            
            # Informações do aeronauta
            if self.nome_aeronauta:
                c.setFont("Helvetica", 11)
                c.setFillColor(colors.black)
                c.drawCentredString(width/2, height - 150, f"Aeronauta: {self.nome_aeronauta}")
                c.drawCentredString(width/2, height - 170, f"Base: {self.base} | RE: {self.re}")
            
            # Marca d'água diagonal "SEM DADOS"
            c.saveState()
            c.translate(width/2, height/2)
            c.rotate(45)
            c.setFont("Helvetica-Bold", 60)
            c.setFillColorRGB(1, 0, 0, alpha=0.3)  # Vermelho com transparência
            text = "SEM DADOS"
            text_width = c.stringWidth(text, "Helvetica-Bold", 60)
            c.drawString(-text_width/2, 0, text)
            c.restoreState()
            
            c.save()
            print(f"\n✅ Relatório vazio gerado com sucesso!")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao gerar relatório vazio: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Função principal"""
    print("="*80)
    print("GERADOR DE RELATÓRIO DETALHADO DE TEMPO EM SOLO")
    print("Diurnas, Noturnas e Especiais")
    print("="*80)
    print()
    
    # Criar janela root oculta
    root = tk.Tk()
    root.withdraw()
    
    # Selecionar arquivo CSV
    arquivo_csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    arquivo_csv = arquivo_csv_env if (arquivo_csv_env and os.path.isfile(arquivo_csv_env)) else filedialog.askopenfilename(
        title="Selecione o arquivo CSV de Tempo em Solo",
        filetypes=[("Arquivos CSV", "*TEMPO_SOLO*.csv"), ("Todos os arquivos", "*.csv")]
    )
    
    if not arquivo_csv:
        messagebox.showwarning("Cancelado", "Nenhum arquivo selecionado.")
        return
    
    print(f"📄 Arquivo selecionado: {os.path.basename(arquivo_csv)}")
    print()
    
    # Criar nome do arquivo de saída
    dir_saida = os.path.dirname(arquivo_csv)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Gerar relatório
    relatorio = RelatorioTempoSoloDetalhado(arquivo_csv)
    nome_prefixo = f"{relatorio.nome_aeronauta} {relatorio.re} SUMARIO_HORAS_EM_SOLO {relatorio.empresa} {relatorio.cargo} {relatorio.periodo}".strip()
    nome_saida = os.path.join(dir_saida, f"{nome_prefixo} {timestamp}.pdf")
    
    if relatorio.gerar_relatorio_pdf(nome_saida):
        messagebox.showinfo("Sucesso", f"Relatório gerado com sucesso!\n\n{nome_saida}")
    else:
        messagebox.showerror("Erro", "Erro ao gerar relatório. Verifique o console para detalhes.")


if __name__ == "__main__":
    main()
