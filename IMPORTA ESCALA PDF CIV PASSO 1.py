# -*- coding: utf-8 -*-
"""
IMPORTA PDF/XLSX/XLS/CSV (FORMATO ALTERNATIVO) -> CSV

Objetivo:
- Gerar CSV com o MESMO layout final do script "IMPORTA ESCALA PDF SIMPLIFICADA ... PASSO 1"
- Nome de saída: <nome_do_arquivo>_PRIMEIRA_VERSAO.csv
- Pasta de saída: substitui "Escalas_Executadas" por "Auditoria_Calculos"

Mapeamento solicitado:
- NumberFlight  -> Activity
- StartDate     -> Checkin e Start
- Origem        -> Dep
- Destino       -> Arr
- EndDate       -> End e Checkout
- Equipment     -> AcVer
- Funcao        -> CAT
- DD e Crew     -> em branco
"""

import os
import re
import sys
import csv
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import tkinter as tk
from tkinter import messagebox, filedialog

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_PDF")) or os.environ.get("AERO_NO_POPUP") == "1"
if MODO_AUTOMATICO:
    try:
        messagebox.showinfo = lambda *args, **kwargs: None
        messagebox.showwarning = lambda *args, **kwargs: None
        messagebox.showerror = lambda *args, **kwargs: None
    except Exception:
        pass


# =============================================================================
# Seleção de arquivo e nome de saída
# =============================================================================

def selecionar_arquivo_entrada() -> Optional[str]:
    # Modo automatizado via rotina inicial do BAT
    entrada_env = os.environ.get("AERO_ESCALA_PDF", "").strip().strip('"')
    if entrada_env and os.path.isfile(entrada_env):
        print(f"Arquivo de entrada selecionado (ENV): {entrada_env}")
        return entrada_env

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showinfo("Seleção de Arquivo", "Selecione o arquivo XLSX/XLS/CSV da escala (formato alternativo).")
        caminho = filedialog.askopenfilename(
            title="Selecione o arquivo de entrada",
            filetypes=[
                ("PDF, Planilhas e CSV", "*.pdf;*.xlsx;*.xls;*.csv"),
                ("PDF", "*.pdf"),
                ("Arquivos Excel", "*.xlsx;*.xls"),
                ("CSV", "*.csv"),
                ("Todos os arquivos", "*.*"),
            ]
        )
        return caminho or None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def nome_csv_saida_para(caminho_entrada: str) -> str:
    from datetime import datetime as _dt
    data_proc = _dt.now().strftime("%d%m%Y_%H%M%S")
    dir_in = os.path.dirname(caminho_entrada)
    base_in = os.path.splitext(os.path.basename(caminho_entrada))[0]
    dir_env = os.environ.get("AERO_OUTPUT_DIR", "").strip().strip('"')
    if dir_env:
        os.makedirs(dir_env, exist_ok=True)
        return os.path.join(dir_env, f"{base_in}_PRIMEIRA_VERSAO_{data_proc}.csv")
    dir_out = dir_in.replace("Escalas_Executadas", "Auditoria_Calculos")
    os.makedirs(dir_out, exist_ok=True)
    return os.path.join(dir_out, f"{base_in}_PRIMEIRA_VERSAO_{data_proc}.csv")


def salvar_csv_seguro(df: pd.DataFrame, caminho_saida: str) -> str:
    """
    Salva CSV no caminho desejado.
    Se houver PermissionError (arquivo aberto/bloqueado), salva com timestamp.
    Retorna o caminho efetivamente salvo.
    """
    try:
        df.to_csv(caminho_saida, index=False, encoding="utf-8-sig", sep=",")
        return caminho_saida
    except PermissionError:
        pasta = os.path.dirname(caminho_saida)
        nome = os.path.basename(caminho_saida)
        stem, ext = os.path.splitext(nome)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        alternativo = os.path.join(pasta, f"{stem}_{ts}{ext}")
        df.to_csv(alternativo, index=False, encoding="utf-8-sig", sep=",")
        print(f"⚠️ Arquivo de saída estava bloqueado. Salvo com novo nome: {alternativo}")
        return alternativo


def extrair_vbase(caminho_entrada: str) -> str:
    """Extrai a base do aeronauta: 4ª posição do nome do arquivo separada por '_' (ignorando vazios)."""
    nome = os.path.splitext(os.path.basename(caminho_entrada))[0]
    partes = [p.strip() for p in nome.split("_") if p and p.strip()]
    if len(partes) >= 4:
        return partes[3]
    return ""


# =============================================================================
# Utilitários
# =============================================================================

CSV_COLUNAS = ["Activity", "Checkin", "Start", "Dep", "Arr", "End", "Checkout", "AcVer", "DD", "CAT", "Crew"]
COLUNAS_OBRIGATORIAS = ["NumberFlight", "StartDate", "Origem", "Destino", "EndDate", "Equipment", "Funcao"]
COLUNAS_OBRIGATORIAS_ESSENCIAIS = ["NumberFlight", "StartDate", "Origem", "Destino", "EndDate", "Equipment"]

ALIASES_COLUNAS = {
    "NumberFlight": [
        "numberflight", "number flight", "flight", "flightnumber", "flight number",
        "numerovoo", "numero voo", "voo", "activity"
    ],
    "StartDate": [
        "startdate", "start date", "start", "inicio", "datahora inicio", "data hora inicio",
        "deptime", "dep time", "std", "checkin"
    ],
    "Origem": [
        "origem", "dep", "departure", "from", "saida"
    ],
    "Destino": [
        "destino", "arr", "arrival", "to", "chegada"
    ],
    "EndDate": [
        "enddate", "end date", "end", "fim", "datahora fim", "data hora fim",
        "arrtime", "arr time", "sta", "checkout"
    ],
    "Equipment": [
        "equipment", "equipamento", "acver", "aircraft", "aeronave", "ac", "fleet"
    ],
    "Funcao": [
        "funcao", "função", "func", "cat", "categoria", "role", "cargo"
    ],
    "RemarksEndorsements": [
        "remarksandendorsements", "remarks and endorsements", "remarks", "endorsements"
    ],
    "TypeOfPilotingTime": [
        "typeofpilotingtime", "type of piloting time", "piloting time", "type of piloting"
    ],
    "SecondInCommand": [
        "secondincommand", "second in command", "sic", "fo", "first officer"
    ],
    "PilotInCommand": [
        "pilotincommand", "pilot in command", "pic"
    ],
    "TimeDualReceived": [
        "timedualreceived", "time dual received", "dual received"
    ],
    "FlightInstructor": [
        "flightinstructor", "flight instructor", "instructor"
    ],
}


def _info(msg: str):
    print(msg)
    try:
        messagebox.showinfo("Informação", msg)
    except tk.TclError:
        pass


def _erro(msg: str):
    print(f"ERRO: {msg}", file=sys.stderr)
    try:
        messagebox.showerror("Erro", msg)
    except tk.TclError:
        pass


def _normalizar_texto(v):
    if pd.isna(v):
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\r", " ")).strip()


def _normalizar_nome_coluna(nome: str) -> str:
    texto = _normalizar_texto(nome).lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^a-z0-9]+", "", texto)
    return texto


def _resolver_coluna(df: pd.DataFrame, coluna_logica: str) -> Optional[str]:
    """
    Resolve o nome real da coluna no dataframe para uma coluna lógica esperada.
    Prioridade: match exato -> alias exato normalizado -> alias contido no nome.
    """
    colunas = list(df.columns)

    # 1) Match exato
    if coluna_logica in colunas:
        return coluna_logica

    # 2) Match normalizado
    mapa_norm = {_normalizar_nome_coluna(c): c for c in colunas}
    logica_norm = _normalizar_nome_coluna(coluna_logica)
    if logica_norm in mapa_norm:
        return mapa_norm[logica_norm]

    # 3) Match por aliases
    aliases = ALIASES_COLUNAS.get(coluna_logica, [])
    aliases_norm = [_normalizar_nome_coluna(a) for a in aliases if a]

    for alias_norm in aliases_norm:
        if alias_norm in mapa_norm:
            return mapa_norm[alias_norm]

    # 4) Match parcial (alias contido no nome da coluna)
    for c in colunas:
        c_norm = _normalizar_nome_coluna(c)
        for alias_norm in aliases_norm:
            if alias_norm and (alias_norm in c_norm or c_norm in alias_norm):
                return c

    return None


def _to_series(valor, index: pd.Index) -> pd.Series:
    if isinstance(valor, pd.Series):
        return valor.reindex(index).fillna("")
    return pd.Series([valor] * len(index), index=index, dtype="object")


def _texto_linha(row: pd.Series) -> str:
    partes = []
    for v in row.values:
        t = _normalizar_texto(v)
        if t:
            partes.append(t.upper())
    return " ".join(partes)


def _vazio_logico(v) -> bool:
    t = _normalizar_texto(v).upper()
    return t in {"", "-", "--", "N/A", "NA", "NONE", "NULL"}


def _eh_linha_lixo_pdf_layout(row: pd.Series) -> bool:
    """Detecta linhas indevidas (rodapé/cabeçalho quebrado) já no layout final."""
    texto = _texto_linha(row)
    padroes = [
        r"REMARKS\s+AND\s+ENDORSEMENTS",
        r"TYPE\s+OF\s+PILOTING\s+TIME",
        r"SECOND\s+IN\s+COMMAND",
        r"TOTAL\s+IN\s+TYPE\s+OF",
        r"IN\s+TYPE\s+OF.*OUT,\s*TYPE\s+OF",
        r"COMMANDLOT\s+IN\s+TYPE\s+OFNDOUT,\s*TYPE\s+OF",
        r"CANAC\s*:\s*\d+",
        r"NOME\s*:\s*",
        r"DATA\s+DA\s+SOLICITACAO\s*:",
    ]
    return any(re.search(p, texto) for p in padroes)


def _remover_linhas_rodape_pdf(df: pd.DataFrame) -> pd.DataFrame:
    """Remove linhas de rodapé/cabeçalho repetido que surgem na extração do PDF."""
    if df.empty:
        return df

    padroes_rodape = [
        r"REMARKS\s+AND\s+ENDORSEMENTS",
        r"TYPE\s+OF\s+PILOTING\s+TIME",
        r"SECOND\s+IN\s+COMMAND",
        r"TOTAL\s+IN\s+TYPE\s+OF",
        r"IN\s+TYPE\s+OF.*OUT,\s*TYPE\s+OF",
        r"PAGE\s+\d+\s+OF\s+\d+",
        r"COMMANDLOT\s+IN\s+TYPE\s+OFNDOUT,\s*TYPE\s+OF",
        r"CANAC\s*:\s*\d+",
        r"NOME\s*:\s*",
        r"DATA\s+DA\s+SOLICITACAO\s*:",
        r"^[-_=|.\s]{6,}$",
    ]

    remover = []
    for _, row in df.iterrows():
        texto = _texto_linha(row)

        # Cabeçalho repetido entre páginas (separador de página com novos títulos)
        eh_cabecalho_repetido = (
            ("NUMBERFLIGHT" in texto and "STARTDATE" in texto and "ENDDATE" in texto)
            or ("ORIGEM" in texto and "DESTINO" in texto and "EQUIPMENT" in texto)
            or ("ACTIVITY" in texto and "CHECKIN" in texto and "CHECKOUT" in texto)
        )

        # Linha separadora visual (apenas traços/sinais)
        tokens = [re.sub(r"\s+", "", _normalizar_texto(v)) for v in row.values]
        tokens = [t for t in tokens if t]
        eh_linha_separadora = bool(tokens) and all(re.fullmatch(r"[-_=|.]{3,}", t) for t in tokens)

        eh_rodape = any(re.search(p, texto) for p in padroes_rodape) or eh_cabecalho_repetido or eh_linha_separadora
        remover.append(eh_rodape)

    if any(remover):
        df = df.loc[[not x for x in remover]].copy()

    return df


def _normalizar_data_hora(coluna: pd.Series) -> pd.Series:
    data = pd.to_datetime(coluna, errors="coerce", dayfirst=True)
    saida = coluna.astype("object").copy()

    mask_ok = data.notna()
    if mask_ok.any():
        saida.loc[mask_ok] = data.loc[mask_ok].dt.strftime("%d/%m/%Y %H:%M")

    mask_bad = ~mask_ok
    if mask_bad.any():
        saida.loc[mask_bad] = saida.loc[mask_bad].apply(_normalizar_texto)

    return saida


def _formatar_activity(v) -> str:
    if pd.isna(v):
        return ""

    texto = _normalizar_texto(v)
    if not texto:
        return ""

    # Remove espaços e padroniza maiúsculo
    texto = re.sub(r"\s+", "", texto).upper()

    # Trata valores numéricos de planilha que podem vir como 1234.0
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto.split(".", 1)[0]

    # Evita duplicar prefixo
    if texto.startswith("AD"):
        texto = texto[2:]

    return f"AD{texto}" if texto else ""


def _detectar_tipo_arquivo(caminho: str) -> str:
    """Retorna: pdf | xlsx | xls | csv | desconhecido"""
    ext = os.path.splitext(caminho)[1].lower()

    try:
        with open(caminho, "rb") as f:
            cabecalho = f.read(8)
    except Exception:
        cabecalho = b""

    # XLSX (zip)
    if cabecalho.startswith(b"PK"):
        return "xlsx"

    # XLS antigo (OLE)
    if cabecalho.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return "xls"

    # fallback por extensão
    if ext == ".pdf":
        return "pdf"
    if ext == ".xlsx":
        return "xlsx"
    if ext == ".xls":
        return "xls"
    if ext == ".csv":
        return "csv"

    # tentativa simples de texto CSV
    try:
        with open(caminho, "r", encoding="utf-8-sig", errors="ignore") as f:
            amostra = f.read(4096)
        if "," in amostra or ";" in amostra or "\t" in amostra:
            return "csv"
    except Exception:
        pass

    return "desconhecido"


def _carregar_pdf_com_tabula(caminho_pdf: str) -> pd.DataFrame:
    """Lê PDF tabular e retorna DataFrame concatenado das tabelas encontradas."""
    try:
        import tabula
    except Exception:
        raise RuntimeError(
            "Para ler PDF neste passo, instale 'tabula-py' e tenha Java disponível."
        )

    tentativas = [
        {"lattice": True, "stream": False},
        {"lattice": False, "stream": True},
    ]

    ultimo_erro = None
    for t in tentativas:
        try:
            tabelas = tabula.read_pdf(
                caminho_pdf,
                pages="all",
                encoding="utf-8",
                multiple_tables=True,
                lattice=t["lattice"],
                stream=t["stream"],
            )
            tabelas_validas = [df for df in (tabelas or []) if isinstance(df, pd.DataFrame) and not df.empty]
            if tabelas_validas:
                df = pd.concat(tabelas_validas, ignore_index=True)
                df.columns = [str(c).strip() for c in df.columns]
                return df
        except Exception as e:
            ultimo_erro = e

    raise RuntimeError(
        f"Falha ao extrair tabelas do PDF. Verifique se é PDF tabular. Erro: {ultimo_erro}"
    )


def _carregar_dataframe_entrada(caminho: str) -> pd.DataFrame:
    tipo = _detectar_tipo_arquivo(caminho)

    if tipo == "pdf":
        return _carregar_pdf_com_tabula(caminho)

    if tipo in {"xlsx", "xls"}:
        try:
            return pd.read_excel(caminho)
        except ImportError:
            raise RuntimeError("Dependência ausente para Excel. Instale openpyxl no ambiente Python em uso.")

    if tipo == "csv":
        # lê CSV tentando encodings, separadores e modos de quoting comuns
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
        separadores = [None, ";", ",", "\t", "|"]
        ultimo_erro = None

        # 1) Tentativas padrão
        for enc in encodings:
            for sep in separadores:
                try:
                    if sep is None:
                        return pd.read_csv(
                            caminho,
                            sep=None,
                            engine="python",
                            encoding=enc,
                            dtype=str,
                            on_bad_lines="skip",
                        )
                    return pd.read_csv(
                        caminho,
                        sep=sep,
                        engine="python",
                        encoding=enc,
                        dtype=str,
                        on_bad_lines="skip",
                    )
                except Exception as e:
                    ultimo_erro = e

        # 2) Fallback para CSV com aspas quebradas (desabilita quote parsing)
        for enc in encodings:
            for sep in [";", ",", "\t", "|"]:
                try:
                    return pd.read_csv(
                        caminho,
                        sep=sep,
                        engine="python",
                        encoding=enc,
                        dtype=str,
                        on_bad_lines="skip",
                        quoting=csv.QUOTE_NONE,
                    )
                except Exception as e:
                    ultimo_erro = e

        raise RuntimeError(
            f"Falha ao ler CSV com encodings {encodings}. Último erro: {ultimo_erro}"
        )

    raise RuntimeError("Tipo de arquivo não reconhecido. Use XLSX, XLS ou CSV.")


# =============================================================================
# Parser adaptado (entrada XLSX)
# =============================================================================

def arquivo_para_dataframe_alternativo(caminho_entrada: str) -> pd.DataFrame:
    df_in = _carregar_dataframe_entrada(caminho_entrada)
    df_in.columns = [str(c).strip() for c in df_in.columns]
    df_in = _remover_linhas_rodape_pdf(df_in)

    mapa_colunas = {col: _resolver_coluna(df_in, col) for col in COLUNAS_OBRIGATORIAS}
    faltantes = [col for col in COLUNAS_OBRIGATORIAS_ESSENCIAIS if mapa_colunas.get(col) is None]
    if faltantes:
        colunas_disponiveis = ", ".join(df_in.columns)
        raise RuntimeError(
            "Colunas obrigatórias ausentes no arquivo de entrada: "
            f"{', '.join(faltantes)}\n"
            f"Colunas encontradas: {colunas_disponiveis}"
        )

    col_voo = mapa_colunas["NumberFlight"]
    col_start = mapa_colunas["StartDate"]
    col_origem = mapa_colunas["Origem"]
    col_destino = mapa_colunas["Destino"]
    col_end = mapa_colunas["EndDate"]
    col_equipment = mapa_colunas["Equipment"]
    col_funcao = mapa_colunas.get("Funcao")
    col_remarks = _resolver_coluna(df_in, "RemarksEndorsements")
    col_pilot_in_command = _resolver_coluna(df_in, "PilotInCommand")
    col_type_piloting = _resolver_coluna(df_in, "TypeOfPilotingTime")
    col_second_in_command = _resolver_coluna(df_in, "SecondInCommand")
    col_dual_received = _resolver_coluna(df_in, "TimeDualReceived")
    col_flight_instructor = _resolver_coluna(df_in, "FlightInstructor")

    # Regra de negócio: Activity deve ser AD + REMARKS AND ENDORSEMENTS (quando existir)
    col_activity_fonte = col_remarks if col_remarks else col_voo

    cat_serie = _to_series(df_in[col_funcao] if col_funcao else "", df_in.index)

    # Regra solicitada: CAT fica vazio quando as colunas de "TYPE OF PILOTING TIME" estiverem vazias
    # (PILOT IN COMMAND, SECOND IN COMMAND, TIME DUAL RECEIVED, FLIGHT INSTRUCTOR).
    serie_pic = _to_series(df_in[col_pilot_in_command], df_in.index) if col_pilot_in_command else _to_series("", df_in.index)
    serie_type = _to_series(df_in[col_type_piloting], df_in.index) if col_type_piloting else _to_series("", df_in.index)
    serie_second = _to_series(df_in[col_second_in_command], df_in.index) if col_second_in_command else _to_series("", df_in.index)
    serie_dual = _to_series(df_in[col_dual_received], df_in.index) if col_dual_received else _to_series("", df_in.index)
    serie_instr = _to_series(df_in[col_flight_instructor], df_in.index) if col_flight_instructor else _to_series("", df_in.index)

    mask_cat_vazio = (
        serie_pic.apply(_vazio_logico)
        & serie_type.apply(_vazio_logico)
        & serie_second.apply(_vazio_logico)
        & serie_dual.apply(_vazio_logico)
        & serie_instr.apply(_vazio_logico)
    )
    cat_serie.loc[mask_cat_vazio] = ""

    df_out = pd.DataFrame({
        "Activity": df_in[col_activity_fonte],
        "Checkin": df_in[col_start],
        "Start": df_in[col_start],
        "Dep": df_in[col_origem],
        "Arr": df_in[col_destino],
        "End": df_in[col_end],
        "Checkout": df_in[col_end],
        "AcVer": df_in[col_equipment],
        "DD": "",
        "CAT": cat_serie,
        "Crew": "",
    })

    for col in ["Checkin", "Start", "End", "Checkout"]:
        df_out[col] = _normalizar_data_hora(df_out[col])

    # Corrige END DATE quando for menor que START DATE (voo que cruza meia-noite)
    # Regra: se End < Start, adiciona 1 dia ao End; idem para Checkout
    def _corrigir_end_menor_start(row):
        fmt = "%d/%m/%Y %H:%M"
        for col_s, col_e in [("Start", "End"), ("Checkin", "Checkout")]:
            try:
                s = datetime.strptime(str(row[col_s]).strip(), fmt)
                e = datetime.strptime(str(row[col_e]).strip(), fmt)
                if e < s:
                    row[col_e] = (e + timedelta(days=1)).strftime(fmt)
            except Exception:
                pass
        return row

    df_out = df_out.apply(_corrigir_end_menor_start, axis=1)

    for col in ["Activity", "Dep", "Arr", "AcVer", "CAT", "DD", "Crew"]:
        df_out[col] = df_out[col].apply(_normalizar_texto)

    # Regra de negócio: Activity = AD + campo de origem (preferencialmente REMARKS AND ENDORSEMENTS)
    df_out["Activity"] = df_in[col_activity_fonte].apply(_formatar_activity)

    # Remove linhas de lixo herdadas da extração PDF (ex.: separador de páginas/rodapé)
    mask_lixo_layout = df_out.apply(_eh_linha_lixo_pdf_layout, axis=1)
    if mask_lixo_layout.any():
        df_out = df_out.loc[~mask_lixo_layout].copy()

    # Remove linhas sem dados de operação válidos (evita sobras de rodapé no CSV final)
    mask_op_valida = (
        df_out["Start"].apply(_normalizar_texto).ne("") |
        df_out["End"].apply(_normalizar_texto).ne("") |
        df_out["Dep"].apply(_normalizar_texto).ne("") |
        df_out["Arr"].apply(_normalizar_texto).ne("")
    )
    df_out = df_out.loc[mask_op_valida].copy()

    # Remove linhas totalmente vazias no layout final
    df_out.replace("", pd.NA, inplace=True)
    df_out.dropna(how="all", inplace=True)
    df_out.fillna("", inplace=True)
    df_out.reset_index(drop=True, inplace=True)

    return df_out[CSV_COLUNAS]


def ajustar_checkin_primeira_linha(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula Checkin da 1ª linha usando a regra padrão de início de jornada:
    - AcVer contém 'AT'          => Start - 30 min
    - 3º dígito Activity > 5     => Start - 60 min
    - Padrão                     => Start - 50 min
    """
    if df.empty:
        return df

    start_str    = str(df.at[0, "Start"]).strip()
    acver_str    = str(df.at[0, "AcVer"]).strip()
    activity_str = str(df.at[0, "Activity"]).strip()
    checkin_ant  = str(df.at[0, "Checkin"]).strip()

    novo_checkin = _calcular_checkin_por_regra(start_str, acver_str, activity_str)
    df.at[0, "Checkin"] = novo_checkin
    print(f"⏱️  Checkin da 1ª linha ajustado: {checkin_ant} → {novo_checkin}")
    return df


def _terceiro_digito_activity_maior_que_5(activity: str) -> bool:
    """Retorna True se o 3º dígito numérico da Activity for > 5."""
    texto = _normalizar_texto(activity).upper()
    if texto.startswith("AD"):
        texto = texto[2:]
    digitos = re.findall(r"\d", texto)
    if len(digitos) < 3:
        return False
    return int(digitos[2]) > 5


def _calcular_checkin_por_regra(start_str: str, acver: str, activity: str) -> str:
    """
    Calcula Checkin a partir de Start para a linha que inicia uma jornada:
    - Se AcVer contém 'AT'            => Start - 30 min.
    - Se 3º dígito de Activity > 5    => Start - 60 min.
    - Padrão                          => Start - 50 min.
    Prioridade: 60 min > 50 min > 30 min.
    """
    FMT = "%d/%m/%Y %H:%M"
    start_txt = str(start_str).strip()
    acver_txt = _normalizar_texto(acver).upper()
    activity_txt = _normalizar_texto(activity).upper()

    # padrão
    minutos = 50

    if "AT" in acver_txt:
        minutos = 30

    if _terceiro_digito_activity_maior_que_5(activity_txt):
        minutos = 60

    try:
        start_dt = datetime.strptime(start_txt, FMT)
    except ValueError:
        return start_txt

    return (start_dt - timedelta(minutes=minutos)).strftime(FMT)


def ajustar_checkout_pernoite(df: pd.DataFrame) -> pd.DataFrame:
    """
    Regras de pernoite e jornada:
    - Compara Checkin[i+1] com Checkin[i].
    - Se a diferença for superior a 12 horas → houve pernoite.
    - Nesse caso: Checkout[i] = End[i] + 30 minutos (linha ANTERIOR ao pernoite).
    - Um contador acompanha quantas linhas pertencem à mesma jornada (inicia em 1).
    - Ao detectar pernoite, retrocede até a primeira linha da jornada e iguala:
      * Checkout de todas as linhas da jornada com o Checkout ajustado da última linha.
      * Checkin de todas as linhas da jornada com o Checkin da primeira linha.
    """
    FMT = "%d/%m/%Y %H:%M"
    ajustes = 0
    jornadas_equalizadas = 0

    if df.empty:
        return df

    contador_jornada = 1
    inicio_jornada = 0

    for i in range(len(df) - 1):
        checkin_atual_str  = str(df.at[i,     "Checkin"]).strip()
        checkin_prox_str   = str(df.at[i + 1, "Checkin"]).strip()
        end_atual_str      = str(df.at[i,     "End"]).strip()

        try:
            checkin_atual_dt = datetime.strptime(checkin_atual_str, FMT)
            checkin_prox_dt  = datetime.strptime(checkin_prox_str,  FMT)
        except ValueError:
            contador_jornada = 1
            inicio_jornada = i + 1
            continue

        diferenca = checkin_prox_dt - checkin_atual_dt
        if diferenca > timedelta(hours=12):
            # pernoite detectado
            try:
                end_atual_dt  = datetime.strptime(end_atual_str, FMT)
                novo_checkout = end_atual_dt + timedelta(minutes=30)
                checkout_anterior = str(df.at[i, "Checkout"]).strip()
                df.at[i, "Checkout"] = novo_checkout.strftime(FMT)
                ajustes += 1

                # Equaliza toda a jornada atual (da linha inicial até a linha i)
                checkout_referencia = str(df.at[i, "Checkout"]).strip()
                start_referencia = str(df.at[inicio_jornada, "Start"]).strip()
                acver_referencia = str(df.at[inicio_jornada, "AcVer"]).strip()
                activity_referencia = str(df.at[inicio_jornada, "Activity"]).strip()
                checkin_referencia = _calcular_checkin_por_regra(
                    start_referencia,
                    acver_referencia,
                    activity_referencia,
                )

                for j in range(inicio_jornada, i + 1):
                    df.at[j, "Checkout"] = checkout_referencia
                    df.at[j, "Checkin"] = checkin_referencia

                # Também aplica a regra de Checkin na linha seguinte ao pernoite (i+1)
                # usando Start/AcVer/Activity da própria linha seguinte.
                start_prox = str(df.at[i + 1, "Start"]).strip()
                acver_prox = str(df.at[i + 1, "AcVer"]).strip()
                activity_prox = str(df.at[i + 1, "Activity"]).strip()
                checkin_prox_anterior = str(df.at[i + 1, "Checkin"]).strip()
                checkin_prox_ajustado = _calcular_checkin_por_regra(
                    start_prox,
                    acver_prox,
                    activity_prox,
                )
                df.at[i + 1, "Checkin"] = checkin_prox_ajustado

                jornadas_equalizadas += 1

                print(f"🌙 Pernoite entre linhas {i + 1} e {i + 2} "
                      f"(diff={diferenca}): Checkout[{i + 1}] "
                      f"{checkout_anterior} → {df.at[i, 'Checkout']} | "
                      f"Jornada equalizada: linhas {inicio_jornada + 1}..{i + 1} "
                      f"(contador={contador_jornada}) | "
                      f"Checkin linha {i + 2}: {checkin_prox_anterior} → {df.at[i + 1, 'Checkin']}")
            except ValueError:
                print(f"⚠️  Linha {i + 1}: não foi possível ajustar Checkout "
                      f"(End inválido: '{end_atual_str}').")

            # Reinicia para a próxima jornada, começando em i+1
            contador_jornada = 1
            inicio_jornada = i + 1
        else:
            # Ainda na mesma jornada
            contador_jornada += 1

    if ajustes > 0:
        print(f"   Total de pernoites ajustados: {ajustes}")
        print(f"   Total de jornadas equalizadas: {jornadas_equalizadas}")
    else:
        print("   Nenhum pernoite detectado.")

    return df


# =============================================================================
# Execução
# =============================================================================

def main():
    arquivo_entrada = selecionar_arquivo_entrada()
    if not arquivo_entrada:
        _erro("Nenhum arquivo selecionado.")
        return

    vBase = extrair_vbase(arquivo_entrada)
    if vBase:
        print(f"🛫 vBase identificada: {vBase}")
    else:
        print("⚠️ vBase não identificada no nome do arquivo (4ª posição por '_').")

    try:
        tipo = _detectar_tipo_arquivo(arquivo_entrada)
        print(f"\n📖 Lendo arquivo de entrada ({tipo})...")
        df = arquivo_para_dataframe_alternativo(arquivo_entrada)

        # Ajusta Checkin da 1ª linha (regra de início de jornada)
        df = ajustar_checkin_primeira_linha(df)

        # Ajusta Checkout nos pernoites (Checkin próxima > Checkout atual)
        print("\n🔍 Verificando pernoites...")
        # Ajusta pernoite por diferença >12h entre Checkins e equaliza a jornada
        df = ajustar_checkout_pernoite(df)

        csv_out = nome_csv_saida_para(arquivo_entrada)
        csv_out = salvar_csv_seguro(df, csv_out)

        print("\n" + "=" * 70)
        print("✅ TAREFA CONCLUÍDA COM SUCESSO!")
        print("=" * 70)
        print(f"📊 Linhas processadas: {len(df)}")
        print(f"🛫 Base (vBase): {vBase if vBase else 'NÃO IDENTIFICADA'}")
        print(f"📦 CSV gerado: {csv_out}")
        print("=" * 70 + "\n")

        _info(f"CSV gerado com sucesso em:\n{csv_out}")

    except Exception as e:
        _erro(f"Falha ao processar arquivo alternativo: {e}")


if __name__ == "__main__":
    main()
