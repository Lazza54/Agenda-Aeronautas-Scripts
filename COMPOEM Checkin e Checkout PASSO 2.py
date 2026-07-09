# -*- coding: utf-8 -*-
"""
PREENCHE CAMPOS EM BRANCO - FINAL (integração DEG)
--------------------------------------------------
- Seleciona um arquivo de ENTRADA (CSV ou Excel) via diálogo.
- Lê CSV (autodetect delimitador) e Excel (.xlsx/.xls).
- Limpa espaços e marcadores de vazio.
- Preenche:
    * Todas as colunas, EXCETO 'Checkout': ffill + bfill.
    * 'Checkout': bfill e depois ffill (garante zero NaN).
- Padroniza datas/horas nas colunas: Checkin, Start, End, Checkout.
- Salva no MESMO DIRETÓRIO do arquivo de entrada com nome:
    <nome_entrada>_SEGUNDA_VERSAO_DDMMAAAA_HHMMSS.<mesma_extensão>

Requisitos: pandas, numpy, (openpyxl para .xlsx).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional

MODO_AUTOMATICO = bool(os.environ.get("AERO_ESCALA_CSV")) or os.environ.get("AERO_NO_POPUP") == "1"

# ===== Caminho do script e CWD fixado na pasta do script =====
SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent
os.chdir(ROOT)

# ===== Dependências =====
import pandas as pd
import numpy as np

# =========================
# Impressão segura
# =========================
def safe_print(*args) -> None:
    text = " ".join(str(a) for a in args)
    try:
        print(text)
    except UnicodeEncodeError:
        enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
        try:
            sys.stdout.buffer.write((text + "\n").encode(enc, errors="replace"))
        except Exception:
            sys.stdout.write(text.encode(errors="replace").decode() + "\n")

# =========================
# BLOCO DEG — Seleção e nome de saída
# =========================
def selecionar_diretorio_arquivo() -> Optional[Path]:
    """Retorna o Path do arquivo CSV de entrada.
    Modo automático: variável de ambiente AERO_ESCALA_CSV.
    Modo interativo: abre diálogo de seleção."""
    import os as _os
    csv_env = _os.environ.get("AERO_ESCALA_CSV", "").strip().strip('"')
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

    tipos = (
        ("CSV", "*.csv"),
        ("Excel", "*.xlsx;*.xls"),
        ("Todos", "*.*"),
    )
    caminho = filedialog.askopenfilename(
        title="Selecione o arquivo de entrada (CSV ou Excel)",
        initialdir=str(ROOT),
        filetypes=tipos,
    )
    if not caminho:
        try: messagebox.showwarning("Aviso", "Nenhum arquivo selecionado. Operação cancelada.")
        except Exception: pass
        return None

    caminho = Path(caminho).resolve()
    try: messagebox.showinfo("Arquivo selecionado", f"Você selecionou:\n{caminho}")
    except Exception: pass
    return caminho

def caminho_saida_mesmo_dir(entrada: Path) -> Path:
    """
    Gera o caminho de saída no MESMO diretório do arquivo de entrada:
            <stem_sem__PRIMEIRA_VERSAO[_data]>_SEGUNDA_VERSAO_DDMMAAAA_HHMMSS.<mesma_extensão>
    """
    import re as _re
    stem = entrada.stem
    # Remove sufixo _PRIMEIRA_VERSAO com ou sem data de processamento (_DDMMAAAA_HHMMSS)
    stem = _re.sub(r"_PRIMEIRA_VERSAO(_\d{8}_\d{6})?$", "", stem)
    data_proc = datetime.now().strftime("%d%m%Y_%H%M%S")
    out_name = f"{stem}_SEGUNDA_VERSAO_{data_proc}{entrada.suffix.lower() if entrada.suffix else '.csv'}"
    return entrada.with_name(out_name)

# =====================
# Leitura de dados
# =====================
def _ler_csv_robusto(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
    separadores = [",", ";", "\t", "|", None]
    ultimo_erro = None
    melhor_df = None
    melhor_score = (-1, -1)

    for enc in encodings:
        for sep in separadores:
            try:
                df = pd.read_csv(
                    path,
                    engine="python",
                    sep=sep,
                    encoding=enc,
                    dtype=str,
                    keep_default_na=False,
                    na_values=[],
                    on_bad_lines="skip",
                )
                score = (len(df.columns), len(df))
                if score > melhor_score:
                    melhor_df = df
                    melhor_score = score
            except Exception as e:
                ultimo_erro = e

    if melhor_df is not None:
        return melhor_df

    raise RuntimeError(f"Falha ao ler CSV com encodings {encodings}. Ultimo erro: {repr(ultimo_erro)}")

def _ler_excel_robusto(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path, dtype=str)
    except Exception as e:
        raise RuntimeError(f"Falha ao ler Excel: {repr(e)}")

def ler_tabela(path: Path) -> Tuple[pd.DataFrame, str]:
    ext = path.suffix.lower()
    if ext == ".csv":
        return _ler_csv_robusto(path), "csv"
    if ext in (".xlsx", ".xls"):
        return _ler_excel_robusto(path), "excel"
    # tentativas flexíveis
    try:
        return _ler_csv_robusto(path), "csv"
    except Exception:
        pass
    try:
        return _ler_excel_robusto(path), "excel"
    except Exception:
        pass
    raise ValueError(f"Extensão não suportada: {ext}. Forneça CSV ou Excel.")

# =====================
# Limpeza e preenchimento
# =====================
VALORES_VAZIOS = {
    "", " ", "-", "—", "–", "--", "---",
    "na", "n/a", "nao informado", "não informado", "null", "none",
    "sem dado", "indefinido",
}
VALORES_VAZIOS = VALORES_VAZIOS | {v.upper() for v in VALORES_VAZIOS}

def limpar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    def _strip_cell(x):
        if pd.isna(x): return np.nan
        return str(x).replace("\ufeff", "").strip()

    # Compatível com pandas >= 3.x: applymap pode não existir, então usamos apply se necessário
    if hasattr(df, 'applymap'):
        df = df.applymap(_strip_cell)
        df = df.applymap(lambda x: np.nan if (isinstance(x, str) and x.strip() in VALORES_VAZIOS) else x)
    else:
        # Fallback: aplica célula a célula
        df = df.apply(lambda col: col.apply(_strip_cell))
        df = df.apply(lambda col: col.apply(lambda x: np.nan if (isinstance(x, str) and x.strip() in VALORES_VAZIOS) else x))
    return df

def preencher_checkout_bfill_then_ffill(series: pd.Series) -> tuple[pd.Series, int]:
    s = series.copy()
    nan_antes = int(s.isna().sum())
    s = s.bfill()
    s = s.ffill()
    nan_depois = int(s.isna().sum())
    return s, max(nan_antes - nan_depois, 0)

# =====================
# Datas/Horas
# =====================
COLUNAS_DATAHORA = ["Checkin", "Start", "End", "Checkout"]

def _tentar_parse_datetime(serie: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(serie, errors="coerce", dayfirst=True)
    out = []
    for orig, dt in zip(serie, parsed):
        out.append(dt.strftime("%d/%m/%Y %H:%M") if pd.notna(dt) else orig)
    return pd.Series(out, index=serie.index)

def padronizar_colunas_datahora(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in COLUNAS_DATAHORA:
        if col in df.columns:
            df[col] = _tentar_parse_datetime(df[col].astype(str))
    return df

# =====================
# Escrita (mesmo diretório)
# =====================
def escrever_saida(df: pd.DataFrame, entrada: Path, tipo: str) -> Path:
    out = caminho_saida_mesmo_dir(entrada)
    if tipo == "csv":
        df.to_csv(out, index=False, encoding="utf-8-sig", sep=",")
    else:
        # força .xlsx na saída excel
        out = out.with_suffix(".xlsx")
        df.to_excel(out, index=False)
    return out


def checkin_checkout_sem_vazios(df: pd.DataFrame) -> bool:
    """Retorna True se as colunas Checkin e Checkout existirem e não tiverem valores vazios."""
    colunas_necessarias = ["Checkin", "Checkout"]
    if any(col not in df.columns for col in colunas_necessarias):
        return False
    return bool(df["Checkin"].notna().all() and df["Checkout"].notna().all())


def _arquivo_eh_latam(path: Path) -> bool:
    """Detecta se o arquivo de entrada é da LATAM pelo nome."""
    stem_up = path.stem.upper().strip()
    name_up = path.name.upper().strip()
    return (
        stem_up.endswith("LATAM")
        or stem_up.endswith("_LATAM")
        or "LATAM" in stem_up
        or "LATAM" in name_up
    )


def aplicar_regra_latam_checkin_start(df: pd.DataFrame, arquivo_entrada: Path) -> pd.DataFrame:
    """Para arquivo LATAM: se Activity não iniciar com LA, Checkin = Start."""
    if not _arquivo_eh_latam(arquivo_entrada):
        return df
    if not {"Activity", "Checkin", "Start"}.issubset(df.columns):
        return df

    out = df.copy()
    act = out["Activity"].fillna("").astype(str).str.strip().str.upper()
    mask_nao_la = ~act.str.startswith("LA")
    mask_start_ok = out["Start"].notna() & (out["Start"].astype(str).str.strip() != "")
    mask = mask_nao_la & mask_start_ok
    out.loc[mask, "Checkin"] = out.loc[mask, "Start"]
    return out

# =====================
# Pipeline principal
# =====================
def processar_arquivo(arquivo_entrada: Path) -> Path:
    df, tipo = ler_tabela(arquivo_entrada)
    df = limpar_dataframe(df)

    if tipo == "csv" and checkin_checkout_sem_vazios(df):
        saida = caminho_saida_mesmo_dir(arquivo_entrada)
        shutil.copy2(arquivo_entrada, saida)
        safe_print("Checkin e Checkout já estão completos. CSV copiado sem alterações.")
        return saida

    antes = int(df.isna().sum().sum())

    df_filled = df.copy()
    cols_except_checkout = [c for c in df_filled.columns if c != "Checkout"]
    if cols_except_checkout:
        df_filled[cols_except_checkout] = df_filled[cols_except_checkout].ffill().bfill()

    if "Checkout" in df_filled.columns:
        nova_checkout, _ = preencher_checkout_bfill_then_ffill(df_filled["Checkout"])
        df_filled["Checkout"] = nova_checkout

    # Restaurar linhas que originalmente tinham Activity em branco (ex: folgas)
    if "Activity" in df.columns:
        mask_vazia = df["Activity"].isna()
        df_filled.loc[mask_vazia, :] = df.loc[mask_vazia, :]

    # Regra específica LATAM:
    # quando Activity não iniciar com LA, Checkin deve ser igual a Start.
    df_filled = aplicar_regra_latam_checkin_start(df_filled, arquivo_entrada)

    df_filled = padronizar_colunas_datahora(df_filled)

    depois = int(df_filled.isna().sum().sum())
    total_preenchidas = antes - depois

    saida = escrever_saida(df_filled, arquivo_entrada, tipo)
    safe_print(f"Linhas: {len(df_filled)} | Colunas: {len(df_filled.columns)} | Células preenchidas: {total_preenchidas}")
    return saida

def main():
    entrada = selecionar_diretorio_arquivo()
    if not entrada:
        return
    try:
        out = processar_arquivo(entrada)
        if MODO_AUTOMATICO:
            safe_print("[OK]", out)
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
                messagebox.showinfo("Concluído", f"Processamento finalizado!\n\nArquivo de saída:\n{out}")
                r.destroy()
            except Exception:
                safe_print("[OK]", out)
    except Exception as e:
        if MODO_AUTOMATICO:
            safe_print("[ERRO]", repr(e))
        else:
            try:
                import tkinter as tk
                from tkinter import messagebox
                r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
                messagebox.showerror("Erro", f"Ocorreu um erro durante o processamento:\n{repr(e)}")
                r.destroy()
            except Exception:
                safe_print("[ERRO]", repr(e))

if __name__ == "__main__":
    main()
