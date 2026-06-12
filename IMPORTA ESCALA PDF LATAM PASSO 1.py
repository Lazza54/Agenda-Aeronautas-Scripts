# -*- coding: utf-8 -*-
"""
IMPORTA PDF DE ESCALA LATAM -> CSV (layout padrão do pipeline)
Utilizando pdfplumber como extrator (sem dependência de Java/tabula)
Fusão da lógica de extração flexível baseada em Regex com correções cronológicas avançadas.

Saída:
  <nome_do_pdf>_PRIMEIRA_VERSAO_<data>.csv

Pasta de saída:
  - Se AERO_OUTPUT_DIR estiver definido, usa essa pasta
  - Caso contrário, troca "Escalas_Executadas" por "Auditoria_Calculos"
"""

import os
import re
import warnings
from datetime import datetime, timedelta

import pandas as pd
import pdfplumber
from tqdm import tqdm

import tkinter as tk
from tkinter import messagebox, filedialog

warnings.filterwarnings("ignore")

CSV_COLUMNS = ["Activity", "Checkin", "Start", "Dep", "Arr", "End", "Checkout", "AcVer", "DD", "CAT", "Crew"]

# Mapeamento de meses abreviados para números
MONTHS_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
    'DEZ': 12, 'OUT': 10, 'SET': 9, 'AGO': 8, 'MAI': 5, 'ABR': 4, 'FEV': 2
}

diretorio_entrada = ""
arquivo_entrada = ""


def selecionar_diretorio_arquivo():
    """Abre diálogo para escolher um PDF; retorna (diretório, arquivo)."""
    global diretorio_entrada, arquivo_entrada

    pdf_env = os.environ.get("AERO_ESCALA_PDF", "").strip().strip('"')
    if pdf_env and os.path.isfile(pdf_env) and pdf_env.lower().endswith(".pdf"):
        diretorio_entrada = os.path.dirname(pdf_env)
        arquivo_entrada = os.path.basename(pdf_env)
        print(f"[ENV] Diretorio selecionado: {diretorio_entrada}")
        print(f"[ENV] Arquivo selecionado: {arquivo_entrada}")
        return diretorio_entrada, arquivo_entrada

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showinfo("Seleção de Arquivo", "Selecione o PDF da Escala LATAM.")
        caminho_completo = filedialog.askopenfilename(
            title="Selecione o PDF",
            filetypes=[("Arquivos PDF", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if not caminho_completo:
            print("Nenhum arquivo foi selecionado.")
            return None, None
        diretorio_entrada = os.path.dirname(caminho_completo)
        arquivo_entrada = os.path.basename(caminho_completo)
        print(f"Diretorio selecionado: {diretorio_entrada}")
        print(f"Arquivo selecionado: {arquivo_entrada}")
        return diretorio_entrada, arquivo_entrada
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def nome_csv_saida_para(pdf_path: str) -> str:
    data_proc = datetime.now().strftime("%d%m%Y_%H%M%S")
    dir_pdf = os.path.dirname(pdf_path)
    base_pdf = os.path.splitext(os.path.basename(pdf_path))[0]

    dir_env = os.environ.get("AERO_OUTPUT_DIR", "").strip().strip('"')
    if dir_env:
        os.makedirs(dir_env, exist_ok=True)
        return os.path.join(dir_env, f"{base_pdf}_PRIMEIRA_VERSAO_{data_proc}.csv")

    dir_out = dir_pdf.replace("Escalas_Executadas", "Auditoria_Calculos")
    os.makedirs(dir_out, exist_ok=True)
    return os.path.join(dir_out, f"{base_pdf}_PRIMEIRA_VERSAO_{data_proc}.csv")


def _erro(msg: str):
    print("ERRO:", msg)
    try:
        messagebox.showerror("Erro", msg)
    except tk.TclError:
        pass


def clean_time(val):
    """Remove (+1), (+2), etc e extrai apenas HH:MM"""
    if not val:
        return ""
    val = re.sub(r'\(\+\d\)', '', str(val)).strip()
    match = re.search(r'\d{2}:\d{2}', val)
    return match.group(0) if match else ""


def extract_date_from_col0(val):
    """Extrai uma data física (dd-Mmm-yyyy) da Coluna 0."""
    if not val:
        return None
    val_str = str(val).strip()
    match = re.search(r'(\d{2})-([A-Za-z]{3})-(\d{4})', val_str)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).upper()
        year = int(match.group(3))
        month = MONTHS_MAP.get(month_name, 1)
        return datetime(year, month, day)
    return None


def has_valid_time(val):
    """Verifica se os primeiros 5 caracteres da string representam um horário HH:MM válido."""
    if not val:
        return False
    val_str = str(val).strip()
    return bool(re.match(r'^\d{2}:\d{2}', val_str[:5]))


def find_marco_zero(df_raw):
    """
    Regra 1: Marco Zero (Regra de Retrocesso)
    - Encontra a primeira data física na Coluna 0 (ex: 02-Jun-2026).
    - Calcula a distância para o dia 01 (Dia Encontrado - 1).
    - Sobe a partir da linha anterior contando quantas linhas têm horário válido como primeiro valor.
    - A linha que completa essa contagem é o Marco Zero.
    """
    date_pattern = re.compile(r'(\d{2})-([A-Za-z]{3})-(\d{4})')
    
    first_date_idx = -1
    first_date_val = None
    
    for idx, row in df_raw.iterrows():
        col0_val = str(row[0]).strip() if row[0] is not None else ""
        if date_pattern.search(col0_val):
            first_date_idx = idx
            first_date_val = col0_val
            break
            
    if first_date_idx == -1:
        print("[ERRO] Nenhuma data física encontrada na Coluna 0 para referenciar.")
        return -1, None
        
    dt_encontrada = extract_date_from_col0(first_date_val)
    if not dt_encontrada:
        print("[ERRO] Falha ao analisar a primeira data física encontrada.")
        return -1, None
        
    dia_encontrado = dt_encontrada.day
    distancia = dia_encontrado - 1
    
    print(f"Primeira data física identificada: {first_date_val} (Linha {first_date_idx})")
    print(f"Dia Encontrado: {dia_encontrado}. Distância até o dia 1: {distancia} linha(s)")
    
    data_inicio_marco_zero = datetime(dt_encontrada.year, dt_encontrada.month, 1)
    
    if distancia <= 0:
        print(f"Marco Zero fixado na própria linha da primeira data física (Linha {first_date_idx})")
        return first_date_idx, data_inicio_marco_zero
        
    retro_idx = first_date_idx - 1
    valid_lines_count = 0
    
    while retro_idx >= 0:
        row_vals = df_raw.iloc[retro_idx]
        cells = [str(c).strip() for c in row_vals if c is not None and str(c).strip() != "" and str(c).strip() != "None"]
        if cells:
            if has_valid_time(cells[0]):
                valid_lines_count += 1
                if valid_lines_count == distancia:
                    print(f"Marco Zero fixado na Linha {retro_idx} (contendo '{cells[0]}' como horário de checkin).")
                    return retro_idx, data_inicio_marco_zero
        retro_idx -= 1
        
    print(f"[AVISO] Não foi possível retroceder {distancia} linhas com horário válido. Fixando no início (Linha 0).")
    return 0, data_inicio_marco_zero


def _normalizar_datas_serie(series: pd.Series) -> pd.Series:
    def _fix(v):
        if pd.isna(v):
            return ""
        s = str(v).strip()
        if s in {"-", ""}:
            return s

        # Corrige casos invertidos como: '04:20 17/05/2026'
        m_inv = re.match(r"^(\d{1,2}:\d{2})\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})$", s)
        if m_inv:
            s = f"{m_inv.group(2)} {m_inv.group(1)}"

        s_up = s.upper()
        repl = {
            "DEZ": "DEC", "FEV": "FEB", "ABR": "APR", "MAI": "MAY",
            "AGO": "AUG", "SET": "SEP", "OUT": "OCT",
        }
        for k, x in repl.items():
            s_up = s_up.replace(k, x)
        return s_up

    corrected = series.apply(_fix)

    fmts = [
        "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%y %H:%M", "%d-%m-%y %H:%M",
        "%d%b%Y %H:%M", "%d%b%y %H:%M",
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
    ]

    converted = pd.Series(pd.NaT, index=corrected.index, dtype="datetime64[ns]")
    parse_mask = corrected.notna() & (corrected != "-") & (corrected != "")

    for fmt in fmts:
        mask = parse_mask & converted.isna()
        if mask.any():
            conv = pd.to_datetime(corrected[mask], format=fmt, errors="coerce")
            converted.loc[mask & conv.notna()] = conv[conv.notna()]

    mask = parse_mask & converted.isna()
    if mask.any():
        conv = pd.to_datetime(corrected[mask], errors="coerce", dayfirst=True)
        converted.loc[mask & conv.notna()] = conv[conv.notna()]

    out = corrected.astype("object")
    ok = converted.notna()
    if ok.any():
        out.loc[ok] = converted.loc[ok].dt.strftime("%d/%m/%Y %H:%M")

    return out


def _ajustar_datas_do_dr(df: pd.DataFrame) -> pd.DataFrame:
    """Corrige DO/DR quando Checkin/Start ficam após End/Checkout."""
    if df.empty or "Activity" not in df.columns:
        return df

    out = df.copy()
    atividade = out["Activity"].fillna("").astype(str).str.strip().str.upper()
    mask_do_dr = atividade.isin(["DO", "DR"])
    if not mask_do_dr.any():
        return out

    def _parse_col(col_name: str) -> pd.Series:
        if col_name not in out.columns:
            return pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
        return pd.to_datetime(out[col_name], errors="coerce", dayfirst=True)

    dt_checkin = _parse_col("Checkin")
    dt_start = _parse_col("Start")
    dt_end = _parse_col("End")
    dt_checkout = _parse_col("Checkout")

    ref_final = dt_end.copy()
    usar_checkout = ref_final.isna() | (dt_checkout.notna() & (dt_checkout < ref_final))
    ref_final.loc[usar_checkout] = dt_checkout.loc[usar_checkout]

    for col_name, dt_col in [("Checkin", dt_checkin), ("Start", dt_start)]:
        valores = dt_col.copy()
        mask = mask_do_dr & valores.notna() & ref_final.notna() & (valores > ref_final)
        if not mask.any():
            continue

        while mask.any():
            valores.loc[mask] = valores.loc[mask] - pd.Timedelta(days=1)
            mask = mask_do_dr & valores.notna() & ref_final.notna() & (valores > ref_final)

        out.loc[valores.notna(), col_name] = valores.loc[valores.notna()].dt.strftime("%d/%m/%Y %H:%M")

    return out


def _corrigir_continuidade_jornadas(df: pd.DataFrame) -> pd.DataFrame:
    """Garante coerência temporal em linhas de continuação de jornada (sem checkin)."""
    if df.empty:
        return df

    out = df.copy()

    def _to_dt(v: str):
        return pd.to_datetime(v, errors="coerce", dayfirst=True)

    prev_end = pd.NaT
    for idx in out.index:
        act = str(out.at[idx, "Activity"]).strip().upper() if "Activity" in out.columns else ""
        ch = str(out.at[idx, "Checkin"]).strip() if "Checkin" in out.columns else ""

        # Ignora folgas nas regras de continuidade de jornada de trabalho
        if act in ["DO", "DR", "OFF", "DOF"]:
            continue

        ch_dt = _to_dt(ch) if ch else pd.NaT
        st = _to_dt(out.at[idx, "Start"]) if "Start" in out.columns else pd.NaT
        en = _to_dt(out.at[idx, "End"]) if "End" in out.columns else pd.NaT
        co = _to_dt(out.at[idx, "Checkout"]) if "Checkout" in out.columns else pd.NaT

        if pd.notna(ch_dt) and pd.notna(prev_end):
            delta_days = 0
            while ch_dt < prev_end:
                ch_dt += pd.Timedelta(days=1)
                delta_days += 1
            if delta_days > 0:
                if pd.notna(st): st += pd.Timedelta(days=delta_days)
                if pd.notna(en): en += pd.Timedelta(days=delta_days)
                if pd.notna(co): co += pd.Timedelta(days=delta_days)

        if pd.notna(ch_dt) and pd.notna(st):
            delta_days = 0
            while st < ch_dt:
                st += pd.Timedelta(days=1)
                delta_days += 1
            if delta_days > 0:
                if pd.notna(en): en += pd.Timedelta(days=delta_days)
                if pd.notna(co): co += pd.Timedelta(days=delta_days)

        # Continuação de jornada pura (sem checkin)
        if ch == "" and pd.notna(prev_end) and pd.notna(st):
            delta_days = 0
            while st <= prev_end:
                st += pd.Timedelta(days=1)
                delta_days += 1
            if delta_days > 0:
                if pd.notna(en): en += pd.Timedelta(days=delta_days)
                if pd.notna(co): co += pd.Timedelta(days=delta_days)

        if pd.notna(st) and pd.notna(en):
            while en < st:
                en += pd.Timedelta(days=1)

        if pd.notna(en) and pd.notna(co):
            while co < en:
                co += pd.Timedelta(days=1)

        if pd.notna(st) and "Start" in out.columns:
            out.at[idx, "Start"] = st.strftime("%d/%m/%Y %H:%M")
        if pd.notna(ch_dt) and "Checkin" in out.columns:
            out.at[idx, "Checkin"] = ch_dt.strftime("%d/%m/%Y %H:%M")
        if pd.notna(en) and "End" in out.columns:
            out.at[idx, "End"] = en.strftime("%d/%m/%Y %H:%M")
        if pd.notna(co) and "Checkout" in out.columns:
            out.at[idx, "Checkout"] = co.strftime("%d/%m/%Y %H:%M")

        if pd.notna(en):
            prev_end = en

    return out


def _limpar_e_ajustar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.replace("\r", " ", regex=True, inplace=True)
    df.replace("- nan", "-", regex=True, inplace=True)
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    if "Activity" in df.columns:
        a = df["Activity"].astype(str).str.upper().str.strip()
        df = df[~a.isin(["TOTAL:", "TOTAL", "OCULTO", "NAN", "NONE", ""])].copy()

    for col in ["Checkin", "Start", "End", "Checkout"]:
        if col in df.columns:
            df[col] = _normalizar_datas_serie(df[col])

    # 1. Ajuste de Checkin e Checkout vazios para voos/atividades de solo (que não sejam folgas)
    if {"Activity", "Checkin", "Start"}.issubset(df.columns):
        activity_upper = df["Activity"].astype(str).str.upper()
        mask = (df["Checkin"].astype(str).str.strip().isin(["", "-", "nan"])) & \
               (~activity_upper.str.startswith(("AD", "LA"), na=False)) & \
               (~activity_upper.isin(["DO", "DR", "OFF", "DOF"]))
        df.loc[mask, "Checkin"] = df.loc[mask, "Start"]

    if {"Checkout", "End"}.issubset(df.columns):
        m2 = df["Checkout"].astype(str).str.strip().isin(["", "-", "nan"])
        df.loc[m2, "Checkout"] = df.loc[m2, "End"]

    df = _ajustar_datas_do_dr(df)
    df = _corrigir_continuidade_jornadas(df)

    # Garante colunas finais
    for c in CSV_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    return df[CSV_COLUMNS].reset_index(drop=True)


def _eh_linha_numeracao_colunas(row_values) -> bool:
    """Detecta linha artificial como: 0;1;2;3;..."""
    vals = [str(v).strip() for v in row_values]
    vals = [v for v in vals if v != ""]
    if len(vals) < 3:
        return False

    if all(v.isdigit() for v in vals):
        nums = [int(v) for v in vals]
        diffs = [b - a for a, b in zip(nums, nums[1:])]
        if nums == list(range(nums[0], nums[0] + len(nums))) and all(d == 1 for d in diffs):
            return True

    return False


def _eh_linha_cabecalho_rodape_latam(row_values) -> bool:
    txt = " ".join(str(v).strip() for v in row_values if str(v).strip())
    if not txt:
        return False
    up = txt.upper()

    return any([
        "ROSTER REPORT" in up,
        "PRINTED" in up,
        "PAGE" in up and "OF" in up,
        "UNNAMED:" in up,
        "MATRÍCULA" in up,
        "MATRICULA" in up,
        "CAUDURO" in up,
        "JAEGER" in up,
        bool(re.search(r"^\s*\d{1,2}-[A-Z]{3}-\d{4}\s*$", up)),
    ])


def _limpar_tabela_bruta_latam(df: pd.DataFrame) -> pd.DataFrame:
    """Limpa ruídos de extração e mantém a estrutura por posição de coluna."""
    if df is None or df.empty:
        return pd.DataFrame()

    x = df.copy()
    x = x.fillna("").astype(str)
    x = x.map(lambda v: v.replace("\r", " ").replace("\n", " ").strip())

    if x.shape[1] == 0:
        return pd.DataFrame()

    # Reindexa colunas para posição fixa 0..N
    x.columns = list(range(len(x.columns)))

    # Remove linhas totalmente vazias
    mask_not_empty = x.apply(lambda r: any(str(v).strip() for v in r), axis=1)
    x = x[mask_not_empty].copy()
    if x.empty:
        return x

    # Remove linhas artificiais de numeração de colunas e cabeçalho/rodapé de página
    mask_keep = []
    for _, row in x.iterrows():
        vals = row.tolist()
        if _eh_linha_numeracao_colunas(vals):
            mask_keep.append(False)
            continue
        if _eh_linha_cabecalho_rodape_latam(vals):
            mask_keep.append(False)
            continue
        mask_keep.append(True)

    x = x[pd.Series(mask_keep, index=x.index)].copy()
    x.reset_index(drop=True, inplace=True)
    return x


def parse_field_datetime(base_date: datetime, val: str) -> str:
    """
    Extrai o offset (+X) e o horário HH:MM da string e calcula a data correta.
    """
    if not val or val.strip() in ["", "-", "None", "nan"]:
        return ""
    val_str = val.strip()
    
    # Extrai o offset de dias se houver, ex: (+1)
    offset_days = 0
    match_offset = re.search(r'\d{2}:\d{2}\(\+(\d+)\)', val_str)
    if not match_offset:
        # Tenta também o formato simples de (+X) sem horário imediatamente colado
        match_offset = re.search(r'\(\+(\d+)\)', val_str)
    if match_offset:
        offset_days = int(match_offset.group(1))
        val_str = re.sub(r'\(\+\d+\)', '', val_str).strip()
    
    # Extrai apenas o horário HH:MM da string
    match_time = re.search(r'\d{2}:\d{2}', val_str)
    if not match_time:
        return ""
    time_str = match_time.group(0)
    
    # Calcula a data alvo
    target_date = base_date + timedelta(days=offset_days)
    return f"{target_date.strftime('%d/%m/%Y')} {time_str}"


def parse_airport(val: str) -> str:
    """
    Extrai a sigla de 3 letras do aeroporto (ex: GRU da string GRU 08:10).
    """
    if not val or val.strip() in ["", "-", "None", "nan"]:
        return ""
    val_str = val.strip()
    match = re.search(r'\b([A-Z]{3})\b', val_str)
    return match.group(1) if match else ""


def main():
    dir_in, arq_in = selecionar_diretorio_arquivo()
    if not (dir_in and arq_in):
        _erro("Nenhum PDF selecionado.")
        return

    arquivo_path = os.path.join(dir_in, arq_in)
    if not arquivo_path.lower().endswith(".pdf"):
        _erro("O arquivo selecionado não é um PDF.")
        return

    print("\nLendo PDF LATAM e extraindo tabelas por coordenadas de bboxes...")
    raw_rows = []
    with pdfplumber.open(arquivo_path) as pdf:
        total_pages = len(pdf.pages)
        with tqdm(total=100, desc="Processando PDF", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            for page in pdf.pages:
                tables = page.find_tables()
                if not tables:
                    pbar.update(100 / total_pages)
                    continue
                # Assume a primeira tabela encontrada na página
                t = tables[0]
                texts = t.extract()
                for r_idx, row in enumerate(t.rows):
                    # Matriz virtual uniforme de 16 colunas
                    virtual_row = [""] * 16
                    for c_idx, cell_bbox in enumerate(row.cells):
                        if cell_bbox is not None:
                            txt = texts[r_idx][c_idx]
                            if txt is not None:
                                txt = txt.strip().replace('\n', ' ')
                                x0 = cell_bbox[0]
                                # Projeta a célula na coluna virtual de largura 80pt a partir de x0 = 20.0
                                col_idx = int(round((x0 - 20.0) / 80.0))
                                if 0 <= col_idx < 16:
                                    virtual_row[col_idx] = txt
                    raw_rows.append(virtual_row)
                pbar.update(100 / total_pages)

    if not raw_rows:
        _erro("Nenhuma tabela foi encontrada no PDF.")
        return

    df_raw = pd.DataFrame(raw_rows)
    df_raw.columns = range(df_raw.shape[1])

    # 1. Limpar cabeçalhos e rodapés ANTES de achar o Marco Zero
    df_clean = _limpar_tabela_bruta_latam(df_raw)
    if df_clean.empty:
        _erro("Nenhum dado sobrou após a limpeza inicial do PDF.")
        return

    # 2. Encontrar Marco Zero
    start_idx, data_inicio_marco_zero = find_marco_zero(df_clean)
    if start_idx == -1:
        _erro("Falha ao processar o Marco Zero.")
        return

    # Descartar cabeçalho
    df_filtered = df_clean.iloc[start_idx:].reset_index(drop=True)

    processed_data = []
    current_date = data_inicio_marco_zero

    # Ajuste inicial da current_date base se a primeira linha do bloco inicial possuir offset (+X)
    if not df_filtered.empty:
        first_row = df_filtered.iloc[0]
        first_checkin = str(first_row[3]).strip()
        first_start = str(first_row[7]).strip()
        
        match_offset = re.search(r'\(\+(\d+)\)', first_checkin)
        if not match_offset:
            match_offset = re.search(r'\(\+(\d+)\)', first_start)
            
        if match_offset:
            offset_days = int(match_offset.group(1))
            current_date = data_inicio_marco_zero - timedelta(days=offset_days)
            print(f"[AJUSTE BASE] Primeira linha do Marco Zero possui offset (+{offset_days}). Ajustando data base inicial para: {current_date.strftime('%d/%m/%Y')}")

    for _, row in df_filtered.iterrows():
        col0 = str(row[0]).strip()

        # Gatilho de Parada (Rodapé)
        if any(k in col0.upper() for k in ['LEGEND', 'DH :', 'AERONAUTIC', 'ROSTER REPORT']):
            break

        # Lógica de atualização da data base
        physical_date = extract_date_from_col0(col0)
        if physical_date is not None:
            current_date = physical_date

        # Determina a atividade
        col4_val = str(row[4]).strip()
        col2_val = str(row[2]).strip()

        # Activity: se col 4 (Activity principal) estiver vazia, usa col 2 (Activity fallback)
        activity = col4_val if col4_val else col2_val

        if not activity or activity in ["None", ""] or activity.upper() in ["TOTAL:", "TOTAL", "OCULTO", "NAN"]:
            continue

        # Filtra atividades indesejadas de rodapé ou legenda
        if any(token in activity.upper() for token in ["AIRPORT STAND BY", "AERONAUTIC MEDICAL", "HOME STAND BY", "ANNUAL FIXED", "DAY OFF", "REQUESTED DAY"]):
            continue

        # Extrai CAT, AcVer e DD
        cat = str(row[6]).strip() if str(row[6]).strip() not in ["None", "-"] else ""
        ac_ver = str(row[13]).strip() if str(row[13]).strip() not in ["None", "-"] else ""
        dd = str(row[10]).strip() if str(row[10]).strip() not in ["None", "-"] else ""

        # Extrai Dep e Arr
        dep = parse_airport(str(row[7]).strip())
        arr = parse_airport(str(row[8]).strip())

        # Extrai Checkin
        checkin_raw = str(row[3]).strip()
        checkin = parse_field_datetime(current_date, checkin_raw)

        # Extrai Start e End
        start_raw = str(row[7]).strip()
        start = parse_field_datetime(current_date, start_raw)
        
        end_raw = str(row[8]).strip()
        end = parse_field_datetime(current_date, end_raw)

        # Extrai Checkout
        checkout_raw = str(row[9]).strip()
        if not checkout_raw or checkout_raw in ["", "-", "None"]:
            checkout_raw = end_raw
        checkout = parse_field_datetime(current_date, checkout_raw)

        # Ajuste de Checkin vazio para atividades de solo (que não sejam voo e nem folgas)
        activity_upper = activity.upper()
        if not checkin and start:
            if not (activity_upper.startswith("LA") or activity_upper.startswith("AD")) and \
               not (activity_upper in ["DO", "DR", "OFF", "DOF"]):
                checkin = start

        processed_data.append({
            'Activity': activity,
            'Checkin': checkin,
            'Start': start,
            'Dep': dep,
            'Arr': arr,
            'End': end,
            'Checkout': checkout,
            'AcVer': ac_ver,
            'DD': dd,
            'CAT': cat,
            'Crew': ""
        })

    if not processed_data:
        _erro("Nenhum dado válido foi extraído da escala.")
        return

    df_std = pd.DataFrame(processed_data)
    df_std = df_std[CSV_COLUMNS]

    # Limpar e ajustar temporalmente os dados
    print("Limpando e ajustando dados...")
    try:
        df_final = _limpar_e_ajustar(df_std)
    except Exception as e:
        _erro(f"Erro ao ajustar/normalizar datas e jornadas: {e}")
        return

    csv_out = nome_csv_saida_para(arquivo_path)
    try:
        df_final.to_csv(
            csv_out,
            index=False,
            encoding="latin1",
            sep=";",
            lineterminator="\n"
        )
        print(f"\n[SUCESSO] CSV PRIMEIRA_VERSAO gerado: {csv_out}")
    except Exception as e:
        _erro(f"Erro ao salvar CSV: {e}")
        return

    print("\nProcessamento concluído.")


if __name__ == "__main__":
    main()
