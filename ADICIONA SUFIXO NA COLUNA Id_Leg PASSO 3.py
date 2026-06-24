# -*- coding: utf-8 -*-
"""
ADICIONA SUFIXO NAS PERNAS DE VOO (DEG + timestamp)
---------------------------------------------------
- Seleciona um CSV de entrada via diálogo.
- Adiciona/zera coluna 'Id_Leg' e preenche por grupos de 'Checkin':
    * tamanho 1 -> '-IF'
    * primeira  -> '-I'
    * meio      -> '-M'
    * última    -> '-F'
- Salva no MESMO diretório do arquivo de entrada, com nome:
    <stem_sem__SEGUNDA_VERSAO[_data]>_TERCEIRA_VERSAO_<DDMMAAAA_HHMMSS>.csv

Requisitos: pandas, tkinter
"""

from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
import re

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"

import pandas as pd

# =========================
# Seleção de arquivo (DEG)
# =========================
def selecionar_arquivo_csv(inicial: Path | None = None) -> Path | None:
    csv_env = os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
    if csv_env and Path(csv_env).is_file():
        print(f"📄 Arquivo selecionado (ENV): {csv_env}")
        return Path(csv_env).resolve()

    import tkinter as tk
    from tkinter import filedialog, messagebox
    if MODO_AUTOMATICO:
        try:
            messagebox.showinfo = lambda *args, **kwargs: None
            messagebox.showwarning = lambda *args, **kwargs: None
            messagebox.showerror = lambda *args, **kwargs: None
        except Exception:
            pass
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        messagebox.showinfo("Seleção de Arquivo", "Selecione o arquivo CSV (_SEGUNDA_VERSAO).")
    except Exception:
        pass
    filetypes = [("CSV", "*.csv"), ("Todos os arquivos", "*.*")]
    caminho = filedialog.askopenfilename(
        title="Selecione o CSV de entrada",
        initialdir=str(inicial or Path.cwd()),
        filetypes=filetypes
    )
    try:
        root.destroy()
    except Exception:
        pass
    return Path(caminho).resolve() if caminho else None

def caminho_saida_com_timestamp(entrada: Path) -> Path:
    """
    Gera:
      <stem_sem__SEGUNDA_VERSAO[_data]>_TERCEIRA_VERSAO_<DDMMAAAA_HHMMSS>.csv
    no MESMO diretório do arquivo de entrada.
    """
    import re as _re
    stem = entrada.stem
    stem = _re.sub(r"_SEGUNDA_VERSAO(_\d{8}_\d{6})?$", "", stem)
    ts = datetime.now().strftime("%d%m%Y_%H%M%S")
    out_name = f"{stem}_TERCEIRA_VERSAO_{ts}.csv"
    return entrada.with_name(out_name)

# =========================
# Leitura robusta (CSV)
# =========================
def ler_csv_robusto(path: Path) -> pd.DataFrame:
    # tenta encodings comuns; separador fixo vírgula
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
    ultimo_erro = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except Exception as e:
            ultimo_erro = e
    raise RuntimeError(f"Falha ao ler CSV ({path.name}). Último erro: {repr(ultimo_erro)}")

# =========================
# Lógica de Id_Leg por grupo
# =========================
MESES_MAP = {
    'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 'MAI': '05', 'JUN': '06',
    'JUL': '07', 'AGO': '08', 'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
}

def formatar_data_pt(val):
    if pd.isna(val):
        return pd.NA
    
    val_str = str(val).strip().upper()
    val_str = val_str.rstrip('-').strip()
    
    if not val_str or val_str in ['NAN', 'NONE', '-', '—']:
        return pd.NA
        
    # Match ddMMMaa hh:mm ou ddMMMaaaa hh:mm (ex: 02AGO21 08:10)
    match = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2,4})\s+(\d{2}):(\d{2})", val_str)
    if match:
        dia = match.group(1).zfill(2)
        mes_sigla = match.group(2)
        ano_str = match.group(3)
        hora = match.group(4)
        minuto = match.group(5)
        
        mes = MESES_MAP.get(mes_sigla)
        if not mes:
            return val_str
            
        if len(ano_str) == 2:
            ano = "20" + ano_str
        else:
            ano = ano_str
            
        return f"{dia}/{mes}/{ano} {hora}:{minuto}"
        
    return val_str

def converter_para_datetime(series: pd.Series) -> pd.Series:
    """Limpa e converte uma série de strings de data/hora brasileira para datetime."""
    limpo = series.apply(formatar_data_pt)
    return pd.to_datetime(limpo, dayfirst=True, errors="coerce")

def preencher_id_leg_por_checkin(df: pd.DataFrame) -> pd.DataFrame:
    if "Checkin" not in df.columns:
        raise KeyError("Coluna 'Checkin' não encontrada no CSV.")

    out = df.copy()

    # Garante a coluna Id_Leg na posição 1 (após a primeira coluna)
    if "Id_Leg" not in out.columns:
        out.insert(1, "Id_Leg", "")
    else:
        out["Id_Leg"] = ""

    # Convertemos temporariamente para datetime para realizar a ordenação e cálculos de intervalo
    temp = df.copy()
    temp["_orig_idx"] = temp.index
    
    # Tratamento de colunas datetime com conversão robusta e limpeza de traços
    temp["Checkin_dt"] = converter_para_datetime(temp["Checkin"])
    temp["Checkout_dt"] = converter_para_datetime(temp["Checkout"])
    
    # Caso a coluna Start não exista, usamos o Checkin_dt como fallback para ordenação
    if "Start" in temp.columns:
        temp["Start_dt"] = converter_para_datetime(temp["Start"])
    else:
        temp["Start_dt"] = temp["Checkin_dt"]

    # Filtramos apenas linhas que contêm Checkin e Checkout válidos para o agrupamento
    valid_mask = temp["Checkin_dt"].notna() & temp["Checkout_dt"].notna()
    df_valid = temp[valid_mask].copy()

    if df_valid.empty:
        return out

    # Ordenamos cronologicamente pela data de início para garantir cálculo correto do descanso
    df_valid = df_valid.sort_values(by="Start_dt").reset_index(drop=True)

    # Identificamos os grupos de jornada baseado no descanso >= 12 horas
    grupos = []
    grupo_id = 0
    
    for idx, row in df_valid.iterrows():
        if idx == 0:
            grupos.append(grupo_id)
            continue
            
        row_anterior = df_valid.iloc[idx - 1]
        
        # Duração da atividade anterior e atual em minutos (Checkout - Checkin)
        duracao_anterior = (row_anterior["Checkout_dt"] - row_anterior["Checkin_dt"]).total_seconds() / 60.0
        duracao_atual = (row["Checkout_dt"] - row["Checkin_dt"]).total_seconds() / 60.0
        
        # Verificação de Dep = Arr para a atividade anterior e atual (ignora maiúsculas/minúsculas e espaços)
        dep_arr_anterior = str(row_anterior.get("Dep", "")).strip().upper() == str(row_anterior.get("Arr", "")).strip().upper() if pd.notna(row_anterior.get("Dep")) and pd.notna(row_anterior.get("Arr")) else False
        dep_arr_atual = str(row.get("Dep", "")).strip().upper() == str(row.get("Arr", "")).strip().upper() if pd.notna(row.get("Dep")) and pd.notna(row.get("Arr")) else False
        
        # Intervalo de descanso em horas entre o Checkout anterior e o Checkin atual
        diff = row["Checkin_dt"] - row_anterior["Checkout_dt"]
        diff_hours = diff.total_seconds() / 3600.0
        
        # Novo grupo inicia se:
        # 1. Descanso >= 12 horas
        # 2. Atividade anterior durou >= 23h55 (1435 min) E tem Dep = Arr
        # 3. Atividade atual dura >= 23h55 (1435 min) E tem Dep = Arr
        check_anterior = duracao_anterior >= 1435.0 and dep_arr_anterior
        check_atual = duracao_atual >= 1435.0 and dep_arr_atual
        
        if diff_hours >= 12.0 or check_anterior or check_atual:
            grupo_id += 1
            
        grupos.append(grupo_id)
        
    df_valid["_grupo_jornada"] = grupos

    # Preenchemos a coluna Id_Leg no DataFrame original com base nos grupos identificados
    for gid, grupo_df in df_valid.groupby("_grupo_jornada"):
        orig_indices = grupo_df["_orig_idx"].tolist()
        n = len(orig_indices)
        
        if n == 1:
            out.loc[orig_indices[0], "Id_Leg"] = "-IF"
        else:
            out.loc[orig_indices[0], "Id_Leg"] = "-I"
            if n > 2:
                out.loc[orig_indices[1:-1], "Id_Leg"] = "-M"
            out.loc[orig_indices[-1], "Id_Leg"] = "-F"

    return out

# =========================
# Pipeline principal
# =========================
def main():
    entrada = selecionar_arquivo_csv()
    if not entrada:
        print("Nenhum arquivo selecionado. Operação cancelada.")
        return
    if entrada.suffix.lower() != ".csv":
        print(f"O arquivo selecionado não é CSV: {entrada.name}")
        return

    print(f"📄 Arquivo de entrada: {entrada}")

    df = ler_csv_robusto(entrada)
    print("Colunas do arquivo lido:", list(df.columns))

    df_final = preencher_id_leg_por_checkin(df)

    saida = caminho_saida_com_timestamp(entrada)
    df_final.to_csv(saida, index=False, encoding="utf-8-sig")
    print(f"✅ Arquivo gravado: {saida}")

    # Mensagem visual (opcional)
    if not MODO_AUTOMATICO:
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
            messagebox.showinfo("Concluído", f"Processamento finalizado!\n\nArquivo de saída:\n{saida}")
            r.destroy()
        except Exception:
            pass

if __name__ == "__main__":
    main()
