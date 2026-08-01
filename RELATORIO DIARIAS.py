"""
Gerador de Relatório de Diárias a Receber
Sistema para calcular diárias nacionais e internacionais com base na CCT 2025/2026.

Regulamentação CCT (Diárias de Alimentação):
-------------------------------------------
2.3. Diárias
As diárias de alimentação, quando pagas diretamente ao aeronauta, no território nacional, serão
fixadas, a partir de 01 de dezembro de 2025, em R$ 109,95 (cento e nove reais e noventa e cinco
centavos), por refeição principal (almoço, jantar ou ceia).

Parágrafo Primeiro: A diária de alimentação relativa ao café da manhã será igual a 25% (vinte e
cinco por cento) do valor estabelecido para as refeições principais, não sendo devido seu
pagamento quando estiver incluído na conta do hotel;

Parágrafo Segundo: As diárias de alimentação serão pagas sempre que o aeronauta estiver
prestando serviço ou à disposição da empresa, no todo ou em parte, nos seguintes períodos:
I.   Café da manhã, das 05:00 às 08:00 horas inclusive;
II.  Almoço, das 11:00 às 13:00 horas inclusive;
III. Jantar, das 19:00 às 20:00 horas inclusive;
IV.  Ceia, entre 00:00 e 01:00 hora inclusive;

Exceções Regulamentares (Decisões Judiciais):
--------------------------------------------
Decisão TST (Sobreaviso):
Por decisão unânime da Seção Especializada em Dissídios Coletivos (SDC) do TST, publicada em 
27 de outubro de 2021, foi pacificado que não devem ser pagas diárias aos aeronautas em sobreaviso.
"""

import pandas as pd
import json
import os
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict
import tkinter as tk
from tkinter import filedialog, messagebox
from config_caminhos import BASE_COMMON_FILES_PATH

# ReportLab imports
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
except ImportError:
    print("❌ ERRO: Biblioteca 'reportlab' não encontrada!")
    print("\n📦 Para instalar, execute:")
    print("   pip install reportlab")
    sys.exit(1)

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass


class RelatorioDiarias:
    def __init__(self, arquivo_csv):
        self.arquivo_csv = arquivo_csv
        self.nome_aeronauta = "AERONAUTA"
        self.base = "VCP"
        self.re = ""
        self.periodo = ""
        self.df = None
        self.config = {}
        self.aeroportos_br = set()
        self.atividades_pagas_latam = set()
        self.atividades_sobreaviso_latam = set()
        self.folgas_azul = set()
        self.tipos_plantao_azul = set()
        self.tipos_reserva_azul = set()
        self.tipos_treinamento_azul = set()
        self.is_latam = "LATAM" in os.path.basename(self.arquivo_csv).upper()
        
        self._carregar_configuracao()
        self._carregar_configs_folga()
        self._carregar_aeroportos_brasil()
        self._extrair_dados_aeronauta()
        self._carregar_e_filtrar_dados()

    def _carregar_configuracao(self):
        """Carrega a tabela de valores de diárias do arquivo JSON de configuração."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "diarias_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                print("✅ Configuração de diárias carregada com sucesso!")
            except Exception as e:
                print(f"⚠️ Erro ao ler diarias_config.json, usando padrão: {e}")
                self._definir_config_padrao()
        else:
            self._definir_config_padrao()

    def _carregar_configs_folga(self):
        """Carrega a configuração de folgas/licenças correspondente à empresa."""
        dir_diversos = str(BASE_COMMON_FILES_PATH)
        
        # Se R: não existir, tenta o diretório atual do script como fallback
        if not os.path.exists(dir_diversos):
            dir_diversos = os.path.dirname(os.path.abspath(__file__))

        if self.is_latam:
            path_latam = os.path.join(dir_diversos, "AtividadesEscalaLATAM.json")
            if os.path.exists(path_latam):
                try:
                    with open(path_latam, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    activities = data.get("atividades", [])
                    for item in activities:
                        if isinstance(item, dict):
                            if item.get("atividade paga") == "S":
                                for key in ("codigo_iflight_neo", "descricao_resumida"):
                                    val = item.get(key)
                                    if val:
                                        self.atividades_pagas_latam.add(str(val).strip().upper())
                            
                            # Identifica se a atividade da LATAM é de sobreaviso
                            desc = str(item.get("descricao_textual") or "").upper()
                            resumo = str(item.get("descricao_resumida") or "").upper()
                            cod_ams = str(item.get("codigo_ams") or "").upper()
                            if "SOBRE AVISO" in desc or "SOBREAVISO" in desc or "SOBRE AVISO" in resumo or "SOBREAVISO" in resumo or "SOBRE AVISO" in cod_ams or "SOBREAVISO" in cod_ams:
                                for key in ("codigo_iflight_neo", "codigo_ams"):
                                    val = item.get(key)
                                    if val:
                                        self.atividades_sobreaviso_latam.add(str(val).strip().upper())
                                        
                    print(f"✅ Carregadas {len(self.atividades_pagas_latam)} chaves de atividades pagas LATAM.")
                    print(f"✅ Carregadas {len(self.atividades_sobreaviso_latam)} chaves de sobreaviso LATAM.")
                except Exception as e:
                    print(f"⚠️ Erro ao ler AtividadesEscalaLATAM.json: {e}")
        else:
            # AZUL ou demais
            path_azul = os.path.join(dir_diversos, "folgas_regulamentares.json")
            if os.path.exists(path_azul):
                try:
                    with open(path_azul, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for key in ("lista_folgas", "lista_folgas_regulamentares"):
                        v = data.get(key, [])
                        if isinstance(v, list):
                            self.folgas_azul.update(str(x).strip().upper() for x in v if x)
                    print(f"✅ Carregadas {len(self.folgas_azul)} siglas de folga da AZUL.")
                except Exception as e:
                    print(f"⚠️ Erro ao ler folgas_regulamentares.json: {e}")

            # Carrega tipos de plantão da Azul
            path_plantao = os.path.join(dir_diversos, "tipos_plantao.json")
            if os.path.exists(path_plantao):
                try:
                    with open(path_plantao, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    v = data.get("tipos_plantao", [])
                    if isinstance(v, list):
                        self.tipos_plantao_azul.update(str(x).strip().upper() for x in v if x)
                    print(f"✅ Carregados {len(self.tipos_plantao_azul)} tipos de plantão AZUL.")
                except Exception as e:
                    print(f"⚠️ Erro ao ler tipos_plantao.json: {e}")

            # Carrega tipos de reserva da Azul
            path_reserva = os.path.join(dir_diversos, "tipos_reserva.json")
            if os.path.exists(path_reserva):
                try:
                    with open(path_reserva, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    v = data.get("tipos_reserva", [])
                    if isinstance(v, list):
                        self.tipos_reserva_azul.update(str(x).strip().upper() for x in v if x)
                    print(f"✅ Carregados {len(self.tipos_reserva_azul)} tipos de reserva AZUL.")
                except Exception as e:
                    print(f"⚠️ Erro ao ler tipos_reserva.json: {e}")

            # Carrega tipos de treinamento da Azul
            path_treinamento = os.path.join(dir_diversos, "tipos_treinamentos.json")
            if not os.path.exists(path_treinamento):
                path_treinamento = os.path.join(dir_diversos, "tipos_treinamento.json")
            if os.path.exists(path_treinamento):
                try:
                    with open(path_treinamento, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    v = data.get("tipos_treinamentos", []) or data.get("tipos_treinamento", [])
                    if isinstance(v, list):
                        self.tipos_treinamento_azul.update(str(x).strip().upper() for x in v if x)
                    print(f"✅ Carregados {len(self.tipos_treinamento_azul)} tipos de treinamento AZUL.")
                except Exception as e:
                    print(f"⚠️ Erro ao ler tipos_treinamentos.json: {e}")

    def _definir_config_padrao(self):
        self.config = {
            "nacional": {
                "refeicao_principal": 109.95,
                "cafe_manha": 27.49
            },
            "internacional": {
                "america_sul_caribe": {"moeda": "USD", "refeicao_principal": 21.00, "cafe_manha": 5.25},
                "america_norte_mexico": {"moeda": "USD", "refeicao_principal": 23.00, "cafe_manha": 5.75},
                "europa": {"moeda": "EUR", "refeicao_principal": 23.00, "cafe_manha": 5.75},
                "inglaterra": {"moeda": "GBP", "refeicao_principal": 23.00, "cafe_manha": 5.75},
                "demais_paises": {"moeda": "USD", "refeicao_principal": 21.00, "cafe_manha": 5.25}
            }
        }

    def _carregar_aeroportos_brasil(self):
        """Carrega o banco de dados de aeroportos nacionais para classificar trechos internacionais."""
        path_aeroportos_br = r"R:\SPECTRUM_SYSTEM\Aeronautas\Documentos_Comuns\Arquivos_Diversos\aeroportos_brasil.csv"
        if os.path.exists(path_aeroportos_br):
            try:
                df_br = pd.read_csv(path_aeroportos_br, encoding="utf-8-sig")
                for col in ['IATA', 'ICAO']:
                    if col in df_br.columns:
                        self.aeroportos_br.update(df_br[col].dropna().astype(str).str.strip().str.upper().tolist())
                print(f"✅ Carregados {len(self.aeroportos_br)} códigos de aeroportos brasileiros.")
            except Exception as e:
                print(f"⚠️ Erro ao ler aeroportos_brasil.csv: {e}")
                self._carregar_aeroportos_brasil_fallback()
        else:
            self._carregar_aeroportos_brasil_fallback()

    def _carregar_aeroportos_brasil_fallback(self):
        self.aeroportos_br = {
            'CGH', 'SBSP', 'GRU', 'SBGR', 'VCP', 'SBKP', 'GIG', 'SBGL', 'SDU', 'SBRJ',
            'BSB', 'SBBR', 'CNF', 'SBCF', 'SSA', 'SBSV', 'POA', 'SBPA', 'REC', 'SBRF',
            'FOR', 'SBFZ', 'FLN', 'SBFL', 'BEL', 'SBBE', 'GYN', 'SBGO', 'CWB', 'SBCT',
            'IGU', 'SBFI', 'JPA', 'SBJP', 'JOI', 'SBJV', 'LDB', 'SBLO', 'MCZ', 'SBMO',
            'NAT', 'SBSG', 'NVT', 'SBNF', 'PMW', 'SBPJ', 'PVH', 'SBPV', 'RAO', 'SBRP',
            'SLZ', 'SBSL', 'THE', 'SBTE', 'UDI', 'SBUL', 'VIX', 'SBVT', 'CGB', 'SBCY',
            'MAO', 'SBEG', 'MCP', 'SBMQ', 'MGF', 'SBMG', 'BPS', 'SBPS', 'XAP', 'SBCH',
            'IZA', 'SDZY', 'IPN', 'SBIP', 'JJD', 'SSVV', 'MOC', 'SBMK', 'CXJ', 'SBCX',
            'CAC', 'SBCA', 'PVH', 'SBPV', 'BVB', 'SBBV', 'RBR', 'SBRB', 'CZS', 'SBCZ',
            'FEN', 'SBFN', 'CFB', 'SBCB', 'DOU', 'SSDO', 'URG', 'SBUG', 'PET', 'SBPK',
            'BAU', 'SBBU', 'MII', 'SBML', 'AQA', 'SBAQ', 'ARU', 'SBAU', 'PPB', 'SBDN'
        }

    def _extrair_dados_aeronauta(self):
        """Extrai dados do aeronauta a partir do nome do arquivo CSV."""
        try:
            arquivo = os.path.basename(self.arquivo_csv)
            nome_sem_ext = os.path.splitext(arquivo)[0]
            
            # Tenta extrair o período do nome do arquivo (ex: 01022026_01032026)
            m_per = re.search(r"(\d{8})_(\d{8})", nome_sem_ext)
            if m_per:
                p_inicio = m_per.group(1)
                p_fim = m_per.group(2)
                self.periodo = f"{p_inicio[:2]}/{p_inicio[2:4]}/{p_inicio[4:]} a {p_fim[:2]}/{p_fim[2:4]}/{p_fim[4:]}"
            
            # Tenta extrair de forma robusta via regex
            m_dados = re.search(r"^escala_[pe]_(.+?)_([A-Z]{3,4})__+(\d+)?", nome_sem_ext, re.IGNORECASE)
            if m_dados:
                self.nome_aeronauta = m_dados.group(1).replace('_', ' ').strip().upper()
                self.base = m_dados.group(2).upper()
                self.re = m_dados.group(3) or ""
                return

            # Fallback (caso a regex nao dê match)
            if nome_sem_ext.startswith('escala_p_') or nome_sem_ext.startswith('escala_e_'):
                nome_sem_pref = nome_sem_ext[9:]
                partes = nome_sem_pref.split('_')
                if len(partes) >= 3:
                    # Encontra o índice da base operacional (geralmente uma sigla em maiusculas)
                    idx_base = -1
                    for idx, parte in enumerate(partes):
                        if parte.isupper() and len(parte) in (3, 4):
                            idx_base = idx
                            break
                    
                    if idx_base != -1:
                        partes_nome = partes[:idx_base]
                        self.nome_aeronauta = " ".join(partes_nome).replace('_', ' ').strip().upper()
                        self.base = partes[idx_base].upper()
                        
                        # Tenta achar o RE depois da base
                        self.re = ""
                        for i in range(idx_base + 1, len(partes)):
                            if partes[i] and partes[i].isdigit():
                                self.re = partes[i]
                                break
                    else:
                        # Fallback mais simples caso nao ache a base
                        self.nome_aeronauta = f"{partes[0]} {partes[1]}".upper()
        except Exception as e:
            print(f"Aviso ao extrair dados do aeronauta: {e}")

    def _carregar_e_filtrar_dados(self):
        """Lê o arquivo CSV da quarta versão e filtra linhas inválidas."""
        try:
            self.df = pd.read_csv(self.arquivo_csv)
            
            # Normalizar nomes de colunas para Title Case se vierem com capitalização diferente (como checkin, checkout, etc.)
            mapa_colunas = {
                'checkin': 'Checkin',
                'check-in': 'Checkin',
                'checkout': 'Checkout',
                'check-out': 'Checkout',
                'start': 'Start',
                'end': 'End',
                'activity': 'Activity',
                'atividade': 'Activity',
                'dep': 'Dep',
                'arr': 'Arr'
            }
            novos_nomes = {}
            for col in self.df.columns:
                col_normalizada = str(col).strip().lower()
                if col_normalizada in mapa_colunas:
                    novos_nomes[col] = mapa_colunas[col_normalizada]
            if novos_nomes:
                self.df = self.df.rename(columns=novos_nomes)
            
            # Extrai período do primeiro registro se houver e self.periodo estiver vazio
            if not self.periodo and 'periodo' in self.df.columns and len(self.df) > 0:
                self.periodo = str(self.df.iloc[0]['periodo']).strip()
            
            # Filtra atividades válidas (onde pelo menos um tempo está preenchido)
            cols_validar = ['Tempo Apresentacao', 'Tempo Corte', 'Tempo Solo', 'Tempo Jornada', 'Tempo Repouso']
            cols_existentes = [c for c in cols_validar if c in self.df.columns]
            
            if cols_existentes:
                # Substitui traços por NaN temporariamente para a verificação
                df_temp = self.df[cols_existentes].replace(['-', ''], pd.NA)
                mascara_valida = df_temp.notna().any(axis=1)
                self.df = self.df[mascara_valida].reset_index(drop=True)
            
            print(f"✅ Carregados {len(self.df)} registros válidos de escala para cálculo de diárias.")
        except Exception as e:
            print(f"❌ Erro ao ler e filtrar o CSV: {e}")
            self.df = pd.DataFrame()

    def _is_sobreaviso_ou_plantao(self, codigo) -> bool:
        if pd.isna(codigo):
            return False
        c = str(codigo).strip().upper()
        if self.is_latam:
            return c in self.atividades_sobreaviso_latam
        else:
            return c in self.tipos_plantao_azul

    def _obter_tipo_atividade(self, codigo):
        if pd.isna(codigo):
            return 'OUTRO'
        c = str(codigo).strip().upper()
        
        # 1. Repouso (sempre tem precedência)
        if any(k in c for k in ['REPOUSO', 'REP', 'HOTEL', 'DESCANSO']):
            return 'REPOUSO'
            
        # 1b. Sobreaviso/Plantão (excluído de diárias por decisão do TST de 27/10/2021)
        if self._is_sobreaviso_ou_plantao(c) or any(k in c for k in ['SOBREAVISO', 'SBA', 'HSB']):
            return 'SOBREAVISO'
            
        # 2. Folgas e Licenças baseadas nas consultas de configuração
        if self.is_latam:
            # Se for LATAM e o código NÃO estiver no conjunto de atividades pagas
            # (e não for um código óbvio de voo regular como LA...), é folga
            is_voo_regular = c.startswith('LA') and len(c) > 2 and c[2:].isdigit()
            if not is_voo_regular and c not in self.atividades_pagas_latam:
                return 'FOLGA'
        else:
            # Se for AZUL, folgas/licenças são tratadas apenas pela consulta do json folgas_regulamentares
            if c in self.folgas_azul:
                return 'FOLGA'

        # 3. Reservas
        if (not self.is_latam and c in self.tipos_reserva_azul) or any(k in c for k in ['RESERVA', 'RSV', 'RES']):
            return 'RESERVA'
            
        # 4. Plantão
        if (not self.is_latam and c in self.tipos_plantao_azul) or any(k in c for k in ['PLANTAO', 'ASB', 'HSB', 'PLA', 'PLN']):
            return 'PLANTAO'
            
        # 5. Treinamento
        # Consultamos a lista de treinamentos oficial da Azul com fallbacks para simulador e treinamentos conhecidos
        if (not self.is_latam and c in self.tipos_treinamento_azul) or any(k in c for k in ['TREINAMENTO', 'TREIN', 'GS', 'SIMULADOR', 'SIM', 'EAD', 'CURSO', 'INICIAL', 'GROUND SCHOOL', 'PC3', 'SFX', 'DGR', 'GCI']):
            return 'TREINAMENTO'
            
        # 6. Extras
        if any(k in c for k in ['XAP', 'EXTRA', 'EXT']):
            return 'EXTRA'
            
        return 'VOO'

    def _is_empty(self, val):
        if pd.isna(val):
            return True
        s = str(val).strip().upper()
        return s in ['', '-', 'NAT', 'NAN', '<NA>']

    def _classificar_aeroporto(self, iata_icao):
        """Retorna 'Nacional' ou a região internacional correspondente."""
        if pd.isna(iata_icao):
            return 'Nacional'
        code = str(iata_icao).strip().upper()
        if code in self.aeroportos_br:
            return 'Nacional'
            
        # Busca nas regiões internacionais
        REGIOES = {
            "europa": {
                'LIS', 'OPO', 'CDG', 'ORY', 'MAD', 'FRA', 'FCO', 'MXP', 'AMS', 'ZRH',
                'LPPR', 'LFPG', 'LFPO', 'LEMD', 'EDDF', 'LIRF', 'LIMC', 'EHAM', 'LSZH'
            },
            "inglaterra": {
                'LHR', 'LGW', 'MAN', 'EDI', 'GLA', 'STN', 'LTN',
                'EGLL', 'EGKK', 'EGCC', 'EGPH', 'EGPF', 'EGSS', 'EGGW'
            },
            "america_sul_caribe": {
                'MVD', 'PDP', 'EZE', 'AEP', 'COR', 'ASU', 'VVI', 'LPB', 'SCL', 'LIM',
                'BOG', 'PTY', 'CUR', 'PUJ', 'CUN', 'SXM',
                'SUMU', 'SULS', 'SAEZ', 'SABE', 'SACO', 'SGAS', 'SLVR', 'SLLP', 'SCEL',
                'SPJC', 'SKBO', 'MPTO', 'TNCC', 'MDPC', 'MMUN', 'TNCM'
            },
            "america_norte_mexico": {
                'MCO', 'FLL', 'MIA', 'JFK', 'EWR', 'LAX', 'ORD', 'BOS', 'IAD', 'ATL',
                'KMCO', 'KFLL', 'KMIA', 'KJFK', 'KEWR', 'KLAX', 'KORD', 'KBOS', 'KIAD', 'KATL'
            }
        }
        
        for regiao, codigos in REGIOES.items():
            if code in codigos:
                return regiao
        return 'demais_paises'

    def _obter_valores_diaria(self, regiao, tipo_refeicao):
        """Retorna (valor, moeda) para a refeição e região dada."""
        if regiao == 'Nacional':
            valor = self.config["nacional"]["cafe_manha" if tipo_refeicao == "cafe" else "refeicao_principal"]
            return valor, "R$"
        else:
            reg = self.config["internacional"].get(regiao, self.config["internacional"]["demais_paises"])
            moeda = reg["moeda"]
            valor = reg["cafe_manha" if tipo_refeicao == "cafe" else "refeicao_principal"]
            
            # Símbolos de moedas
            simbolos = {"USD": "US$", "EUR": "€", "GBP": "£"}
            return valor, simbolos.get(moeda, moeda)

    def calcular_diarias(self):
        """Processa a escala calculando todas as diárias devidas."""
        if self.df is None or self.df.empty:
            return []

        # Validação defensiva de colunas obrigatórias
        colunas_obrigatorias = ['Checkin', 'Checkout', 'Start', 'End']
        colunas_faltantes = [c for c in colunas_obrigatorias if c not in self.df.columns]
        if colunas_faltantes:
            print(f"❌ Erro: Colunas obrigatórias ausentes no arquivo CSV: {colunas_faltantes}")
            return []

        diarias_calculadas = []
        
        # Converte datas de Checkin, Checkout, Start e End para datetime
        for col in ['Checkin', 'Checkout', 'Start', 'End']:
            if col in self.df.columns:
                self.df[col] = pd.to_datetime(self.df[col], errors='coerce')

        # Remove linhas onde Checkin ou Checkout sejam nulos
        df_jornadas = self.df.dropna(subset=['Checkin', 'Checkout']).copy()
        if df_jornadas.empty:
            return []

        # Agrupa por jornada única (Checkin idêntico)
        grupos = df_jornadas.groupby('Checkin')

        for checkin, grupo_df in grupos:
            # O checkout da jornada é o máximo dos checkouts do grupo
            checkout = grupo_df['Checkout'].max()
            # Ordena as etapas cronologicamente
            etapas = grupo_df.sort_values(by='Start')

            # Verifica se a jornada inteira deve ser descartada (apenas Folga ou Repouso na Base)
            todas_descartadas = True
            for _, etapa in etapas.iterrows():
                atividade = etapa['Activity']
                tipo_ativ = self._obter_tipo_atividade(atividade)
                
                dep = etapa['Dep'] if 'Dep' in grupo_df.columns and pd.notna(etapa['Dep']) else ''
                localidade = dep if dep else self.base
                regiao = self._classificar_aeroporto(localidade)



                # Se houver serviço ativo ou repouso fora da base, não descartamos a jornada
                if not (tipo_ativ == 'FOLGA' or tipo_ativ == 'SOBREAVISO' or (tipo_ativ == 'REPOUSO' and regiao == 'Nacional' and str(localidade).upper() == self.base)):
                    todas_descartadas = False
                    break

            if todas_descartadas:
                continue

            # Varre os dias cobertos pela jornada [Checkin, Checkout]
            dia_inicio = checkin.date()
            dia_fim = checkout.date()
            
            dias_cobertos = []
            curr = dia_inicio
            while curr <= dia_fim:
                dias_cobertos.append(curr)
                curr += timedelta(days=1)
                
            for dia in dias_cobertos:
                # Intervalos de refeições para este dia (em Horário de Brasília)
                ref_intervals = [
                    ("cafe", "Café da Manhã", datetime.combine(dia, datetime.min.time()) + timedelta(hours=5), datetime.combine(dia, datetime.min.time()) + timedelta(hours=8)),
                    ("almoco", "Almoço", datetime.combine(dia, datetime.min.time()) + timedelta(hours=11), datetime.combine(dia, datetime.min.time()) + timedelta(hours=13)),
                    ("jantar", "Jantar", datetime.combine(dia, datetime.min.time()) + timedelta(hours=19), datetime.combine(dia, datetime.min.time()) + timedelta(hours=20)),
                    ("ceia", "Ceia", datetime.combine(dia, datetime.min.time()) + timedelta(hours=0), datetime.combine(dia, datetime.min.time()) + timedelta(hours=1))
                ]
                
                for ref_key, ref_nome, r_ini, r_fim in ref_intervals:
                    # Verifica sobreposição da refeição com a jornada: max(r_ini, checkin) <= min(r_fim, checkout)
                    t_ini = max(r_ini, checkin)
                    t_fim = min(r_fim, checkout)
                    
                    if t_ini <= t_fim:
                        # Encontra a etapa da jornada que melhor representa este período
                        etapa_ref = None
                        
                        # 1. Tenta encontrar etapa que se sobrepõe diretamente com a refeição
                        sobrepostas = []
                        for _, etapa in etapas.iterrows():
                            # Se a etapa possui início/fim válidos
                            if pd.notna(etapa['Start']) and pd.notna(etapa['End']):
                                e_ini = max(r_ini, etapa['Start'])
                                e_fim = min(r_fim, etapa['End'])
                                if e_ini <= e_fim:
                                    duracao_sobreposicao = e_fim - e_ini
                                    sobrepostas.append((duracao_sobreposicao, etapa))
                        
                        if sobrepostas:
                            # Pega a etapa com maior sobreposição
                            sobrepostas = sorted(sobrepostas, key=lambda x: x[0], reverse=True)
                            etapa_ref = sobrepostas[0][1]
                        
                        # 2. Se não houver sobreposição direta, busca a etapa mais próxima/anterior
                        if etapa_ref is None:
                            # Busca a última etapa que terminou antes do início da refeição
                            etapas_anteriores = etapas[etapas['End'] <= r_ini]
                            if not etapas_anteriores.empty:
                                etapa_ref = etapas_anteriores.iloc[-1]
                            else:
                                # Caso seja antes da primeira etapa, pega a primeira
                                etapa_ref = etapas.iloc[0]
                        
                        # Extrai dados da etapa representativa
                        atividade = etapa_ref['Activity']
                        tipo_ativ = self._obter_tipo_atividade(atividade)
                        
                        # Adiciona o asterisco "*" no nome da atividade se for sobreaviso/plantao
                        atividade_display = atividade
                        if tipo_ativ == 'SOBREAVISO':
                            atividade_display = f"{atividade}*"



                        dep = etapa_ref['Dep'] if 'Dep' in grupo_df.columns and pd.notna(etapa_ref['Dep']) else ''
                        arr = etapa_ref['Arr'] if 'Arr' in grupo_df.columns and pd.notna(etapa_ref['Arr']) else ''
                        
                        # Determina localidade (se em solo após um voo, usa o destino da etapa anterior)
                        if pd.notna(etapa_ref['End']) and etapa_ref['End'] <= r_ini:
                            localidade = arr if arr else dep
                        else:
                            localidade = dep if dep else self.base
                            
                        if not localidade:
                            localidade = self.base
                            
                        regiao = self._classificar_aeroporto(localidade)
                        
                        # Valores e moeda iniciais
                        valor, moeda = self._obter_valores_diaria(regiao, ref_key)
                        obs = "Devido em serviço"
                        
                        # Regras especiais de elegibilidade
                        if tipo_ativ == 'SOBREAVISO':
                            valor = 0.0
                            obs = "Não devido em sobreaviso (Decisão TST de 27/10/2021)"
                        
                        # Regra específica do Café da Manhã (servido no hotel no repouso)
                        elif ref_key == 'cafe':
                            if tipo_ativ == 'REPOUSO':
                                valor = 0.0
                                obs = "Incluso no hotel (não devido)"
                                _, moeda = self._obter_valores_diaria(regiao, ref_key)
                            else:
                                obs = "Devido em serviço/treinamento"
                        
                        # Regra específica da Ceia (paga em voo ou simulador)
                        elif ref_key == 'ceia':
                            is_simulador = (tipo_ativ == 'TREINAMENTO' and any(k in atividade.upper() for k in ['PC3', 'SFX', 'SIM']))
                            if tipo_ativ == 'VOO' or is_simulador:
                                obs = "Elegível (Voo/Simulador)"
                            else:
                                valor = 0.0
                                obs = f"Não elegível em {tipo_ativ}"
                        
                        diarias_calculadas.append({
                            'Data': dia.strftime('%d/%m/%Y'),
                            'Refeicao': ref_nome,
                            'Atividade': atividade_display,
                            'Localidade': localidade,
                            'Regiao': 'Nacional' if regiao == 'Nacional' else regiao.replace('_', ' ').title(),
                            'Valor': valor,
                            'Moeda': moeda,
                            'Observacao': obs
                        })
                        
        # Evita duplicidade de diárias (mesmo dia e mesma refeição)
        # Prioriza manter o registro que possui o maior valor a receber (Valor > 0)
        diarias_unicas = {}
        for d in diarias_calculadas:
            chave = (d['Data'], d['Refeicao'])
            if chave not in diarias_unicas:
                diarias_unicas[chave] = d
            else:
                if d['Valor'] > diarias_unicas[chave]['Valor']:
                    diarias_unicas[chave] = d

        # Converte de volta para uma lista ordenada cronologicamente por data e tipo de refeição
        ordem_refeicao = {"Café da Manhã": 0, "Almoço": 1, "Jantar": 2, "Ceia": 3}
        diarias_finais = list(diarias_unicas.values())
        diarias_finais.sort(key=lambda x: (datetime.strptime(x['Data'], '%d/%m/%Y'), ordem_refeicao.get(x['Refeicao'], 4)))

        return diarias_finais

    def gerar_relatorio_txt(self, output_path):
        """Gera o relatório descritivo das diárias em formato de texto."""
        diarias = self.calcular_diarias()
        
        # Totais
        totais = defaultdict(float)
        detalhado_linhas = []
        
        for d in diarias:
            if d['Valor'] > 0:
                totais[d['Moeda']] += d['Valor']
            detalhado_linhas.append(
                f"{d['Data']} | {d['Refeicao']:<15} | {d['Atividade']:<10} | {d['Localidade']:<6} | "
                f"{d['Regiao']:<20} | {d['Moeda']} {d['Valor']:>6.2f} | {d['Observacao']}"
            )
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("======================================================================\n")
            f.write("                   RELATÓRIO DE DIÁRIAS A RECEBER                     \n")
            f.write("======================================================================\n\n")
            f.write(f"AERONAUTA: {self.nome_aeronauta}\n")
            f.write(f"REGISTRO (RE): {self.re}\n")
            f.write(f"BASE OPERACIONAL: {self.base}\n")
            f.write(f"PERÍODO DA ESCALA: {self.periodo}\n\n")
            
            f.write("----------------------------------------------------------------------\n")
            f.write("                           RESUMO DE VALORES                          \n")
            f.write("----------------------------------------------------------------------\n")
            for moeda, valor in sorted(totais.items()):
                f.write(f"Total a receber em {moeda}: {moeda} {valor:,.2f}\n")
            if not totais:
                f.write("Nenhuma diária a receber no período analisado.\n")
            f.write("----------------------------------------------------------------------\n\n")
            
            f.write("DETALHAMENTO DIA A DIA:\n")
            f.write("Data       | Refeição        | Atividade  | Local  | Região               | Valor        | Observação\n")
            f.write("-" * 110 + "\n")
            for linha in detalhado_linhas:
                f.write(linha + "\n")
                
            f.write("\n" + "=" * 110 + "\n")
            f.write("                                             BASE LEGAL\n")
            f.write("=" * 110 + "\n\n")
            f.write("1. Convenção Coletiva de Trabalho (Diárias de Alimentação - Cláusula 2.3):\n")
            f.write("As diárias de alimentação, quando pagas diretamente ao aeronauta, no território nacional, serão\n")
            f.write("fixadas, a partir de 01 de dezembro de 2025, em R$ 109,95 por refeição principal (almoço, jantar ou ceia).\n\n")
            f.write("Parágrafo Primeiro: A diária de alimentação relativa ao café da manhã será igual a 25% (vinte e cinco por cento)\n")
            f.write("do valor estabelecido para as refeições principais, não sendo devido seu pagamento quando estiver incluído\n")
            f.write("na conta do hotel.\n\n")
            f.write("Parágrafo Segundo: As diárias de alimentação serão pagas sempre que o aeronauta estiver prestando serviço ou\n")
            f.write("à disposição da empresa, no todo ou em parte, nos seguintes períodos:\n")
            f.write("  I.   Café da manhã, das 05:00 às 08:00 horas inclusive;\n")
            f.write("  II.  Almoço, das 11:00 às 13:00 horas inclusive;\n")
            f.write("  III. Jantar, das 19:00 às 20:00 horas inclusive;\n")
            f.write("  IV.  Ceia, entre 00:00 e 01:00 hora inclusive;\n\n")
            f.write("2. Exceção de Pagamento - Decisão TST (Sobreaviso):\n")
            f.write("Por decisão unânime da Seção Especializada em Dissídios Coletivos (SDC) do TST, publicada em 27 de outubro de 2021,\n")
            f.write("foi pacificado que não devem ser pagas diárias aos aeronautas em sobreaviso. No relatório acima, as atividades\n")
            f.write("identificadas como sobreaviso ou plantão equivalente estão assinaladas com um asterisco '*' no nome da atividade\n")
            f.write("e possuem valor zerado.\n\n")
            f.write("NOTA:\n")
            f.write("Quando encontrar '*' na atividade, você deve considerar se o pagamento da referida diária é devida ou não de acordo com os textos colocados aqui.\n")
                
        print(f"✅ Relatório TXT gerado com sucesso: {output_path}")
        return diarias

    def gerar_relatorio_pdf(self, output_path):
        """Gera o relatório descritivo das diárias em PDF elegante usando reportlab."""
        diarias = self.calcular_diarias()
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=20,
            rightMargin=20,
            topMargin=30,
            bottomMargin=30
        )
        
        styles = getSampleStyleSheet()
        
        # Estilos customizados
        style_title = ParagraphStyle(
            name='TitleStyle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=colors.HexColor('#0f2a4a'),
            alignment=TA_CENTER,
            spaceAfter=15
        )
        
        style_subtitle = ParagraphStyle(
            name='SubTitleStyle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=colors.HexColor('#333333'),
            spaceAfter=6
        )
        
        style_header_table = ParagraphStyle(
            name='HeaderTable',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=colors.white,
            alignment=TA_CENTER
        )
        
        style_cell_center = ParagraphStyle(
            name='CellCenter',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            alignment=TA_CENTER
        )
        
        style_cell_left = ParagraphStyle(
            name='CellLeft',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            alignment=TA_LEFT
        )
        
        style_cell_right = ParagraphStyle(
            name='CellRight',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            alignment=TA_RIGHT
        )
        
        story = []
        
        # Cabeçalho Principal do PDF
        story.append(Paragraph("RELATÓRIO DE DIÁRIAS A RECEBER", style_title))
        story.append(Spacer(1, 10))
        
        # Dados do Aeronauta
        story.append(Paragraph(f"<b>AERONAUTA:</b> {self.nome_aeronauta}", style_subtitle))
        story.append(Paragraph(f"<b>REGISTRO (RE):</b> {self.re}", style_subtitle))
        story.append(Paragraph(f"<b>BASE OPERACIONAL:</b> {self.base}", style_subtitle))
        story.append(Paragraph(f"<b>PERÍODO DA ESCALA:</b> {self.periodo}", style_subtitle))
        story.append(Spacer(1, 15))
        
        # Resumo de Valores
        totais = defaultdict(float)
        for d in diarias:
            if d['Valor'] > 0:
                totais[d['Moeda']] += d['Valor']
                
        resumo_dados = [["Moeda", "Total a Receber"]]
        for moeda, valor in sorted(totais.items()):
            resumo_dados.append([moeda, f"{moeda} {valor:,.2f}"])
            
        if len(resumo_dados) == 1:
            resumo_dados.append(["-", "Nenhuma diária a receber no período"])
            
        t_resumo = Table(resumo_dados, colWidths=[150, 200])
        t_resumo.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f2a4a')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f4f6f8')]),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BOTTOMPADDING', (0,1), (-1,-1), 5),
            ('TOPPADDING', (0,1), (-1,-1), 5),
        ]))
        
        story.append(Paragraph("<b>RESUMO DE VALORES:</b>", style_subtitle))
        story.append(t_resumo)
        story.append(Spacer(1, 25))
        
        # Tabela Detalhada Dia a Dia
        story.append(Paragraph("<b>DETALHAMENTO DIA A DIA:</b>", style_subtitle))
        
        tabela_dados = [[
            Paragraph("Data", style_header_table),
            Paragraph("Refeição", style_header_table),
            Paragraph("Ativ.", style_header_table),
            Paragraph("Local", style_header_table),
            Paragraph("Região", style_header_table),
            Paragraph("Valor", style_header_table),
            Paragraph("Observação", style_header_table)
        ]]
        
        for d in diarias:
            tabela_dados.append([
                Paragraph(d['Data'], style_cell_center),
                Paragraph(d['Refeicao'], style_cell_left),
                Paragraph(str(d['Atividade']), style_cell_center),
                Paragraph(str(d['Localidade']), style_cell_center),
                Paragraph(d['Regiao'], style_cell_left),
                Paragraph(f"{d['Moeda']} {d['Valor']:,.2f}", style_cell_right),
                Paragraph(d['Observacao'], style_cell_left)
            ])
            
        # Largura das colunas (total A4 útil = 555)
        t_detalhe = Table(tabela_dados, colWidths=[55, 75, 45, 35, 105, 75, 170])
        t_detalhe.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f2a4a')),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9f9f9')]),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,1), (-1,-1), 4),
            ('TOPPADDING', (0,1), (-1,-1), 4),
        ]))
        
        story.append(t_detalhe)
        
        # Seção Base Legal no PDF
        story.append(Spacer(1, 20))
        
        style_base_legal_title = ParagraphStyle(
            name='BaseLegalTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=colors.HexColor('#0f2a4a'),
            spaceAfter=8
        )
        
        style_base_legal_text = ParagraphStyle(
            name='BaseLegalText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            textColor=colors.HexColor('#444444'),
            leading=11,
            spaceAfter=6
        )

        base_legal_story = []
        base_legal_story.append(Paragraph("<b>BASE LEGAL E REGULAMENTAR:</b>", style_base_legal_title))
        
        cct_text = (
            "<b>Convenção Coletiva de Trabalho (Cláusula 2.3 - Diárias):</b><br/>"
            "As diárias de alimentação, quando pagas diretamente ao aeronauta, no território nacional, serão "
            "fixadas, a partir de 01 de dezembro de 2025, em R$ 109,95 por refeição principal (almoço, jantar ou ceia).<br/>"
            "• <i>Parágrafo Primeiro:</i> A diária de alimentação relativa ao café da manhã será igual a 25% (vinte e cinco por cento) "
            "do valor estabelecido para as refeições principais, não sendo devido seu pagamento quando estiver incluído na conta do hotel.<br/>"
            "• <i>Parágrafo Segundo:</i> As diárias de alimentação serão pagas sempre que o aeronauta estiver prestando serviço ou "
            "à disposição da empresa, nos seguintes períodos: I. Café da manhã, das 05:00 às 08:00 horas inclusive; II. Almoço, das 11:00 "
            "às 13:00 horas inclusive; III. Jantar, das 19:00 às 20:00 horas inclusive; IV. Ceia, entre 00:00 e 01:00 hora inclusive."
        )
        base_legal_story.append(Paragraph(cct_text, style_base_legal_text))
        
        tst_text = (
            "<b>Exceção de Pagamento - Decisão TST (Sobreaviso):</b><br/>"
            "Por decisão unânime da Seção Especializada em Dissídios Coletivos (SDC) do TST, publicada em 27 de outubro de 2021, "
            "foi pacificado que não devem ser pagas diárias aos aeronautas em sobreaviso (identificados com asterisco '*' no relatório)."
        )
        base_legal_story.append(Paragraph(tst_text, style_base_legal_text))
        
        nota_text = (
            "<b>NOTA:</b><br/>"
            "Quando encontrar '*' na atividade, você deve considerar se o pagamento da referida diária é devida ou não de acordo com os textos colocados aqui."
        )
        base_legal_story.append(Paragraph(nota_text, style_base_legal_text))
        
        story.append(KeepTogether(base_legal_story))
        
        try:
            doc.build(story)
            print(f"✅ Relatório PDF gerado com sucesso: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Erro ao gerar relatório PDF: {e}")
            return False

    def gerar_relatorio_csv(self, output_path):
        """Gera o relatório descritivo das diárias em formato CSV."""
        diarias = self.calcular_diarias()
        if not diarias:
            print("⚠️ Nenhuma diária calculada para salvar no CSV.")
            return False
        
        try:
            df_diarias = pd.DataFrame(diarias)
            # Salva o arquivo CSV
            df_diarias.to_csv(output_path, index=False, encoding="utf-8-sig")
            print(f"✅ Relatório CSV gerado com sucesso: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Erro ao gerar relatório CSV: {e}")
            return False


def main():
    print("="*60)
    print("🎯 PROCESSADOR DE DIÁRIAS CCT - AERONAUTAS")
    print("="*60)
    
    arquivo_csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    if arquivo_csv_env and os.path.isfile(arquivo_csv_env):
        arquivo_csv = arquivo_csv_env
        print(f"\n📂 Arquivo CSV (ENV): {os.path.basename(arquivo_csv)}")
    else:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        print("\n📂 Selecione o arquivo CSV da Quarta Versão da escala...")
        arquivo_csv = filedialog.askopenfilename(
            title="Selecione o arquivo CSV da Quarta Versão",
            filetypes=[
                ("Arquivos CSV", "*.csv"),
                ("Todos os arquivos", "*.*")
            ]
        )
    
    if not arquivo_csv:
        print("\n❌ Nenhum arquivo selecionado. Operação cancelada.")
        return
        
    if not os.path.exists(arquivo_csv):
        print(f"❌ Arquivo não encontrado: {arquivo_csv}")
        return

    gerador = RelatorioDiarias(arquivo_csv)
    
    # Define nomes dos arquivos de saída
    diretorio = os.path.dirname(arquivo_csv)
    nome_base = os.path.splitext(os.path.basename(arquivo_csv))[0]
    
    # Remove sufixos como "_QUARTA_VERSAO_..." para gerar o nome limpo do relatório
    nome_limpo = re.sub(r'_(PRIMEIRA|SEGUNDA|TERCEIRA|QUARTA)_VERSAO.*$', '', nome_base, flags=re.IGNORECASE)
    
    output_txt = os.path.join(diretorio, f"{nome_limpo}_RELATORIO_DIARIAS.txt")
    output_pdf = os.path.join(diretorio, f"{nome_limpo}_SUMARIO_DIARIAS.pdf")
    output_csv = os.path.join(diretorio, f"{nome_limpo}_RELATORIO_DIARIAS.csv")
    
    # Processa e gera os relatórios
    gerador.gerar_relatorio_txt(output_txt)
    gerador.gerar_relatorio_pdf(output_pdf)
    gerador.gerar_relatorio_csv(output_csv)
    
    print(f"\n{'='*60}")
    print("✅ PROCESSAMENTO DE DIÁRIAS CONCLUÍDO!")
    print(f"{'='*60}")
    print(f"📄 PDF: {os.path.basename(output_pdf)}")
    print(f"📄 TXT: {os.path.basename(output_txt)}")
    print(f"{'='*60}\n")
    
    if not MODO_AUTOMATICO:
        messagebox.showinfo("Sucesso", f"Relatórios de diárias gerados com sucesso!")

if __name__ == "__main__":
    main()
