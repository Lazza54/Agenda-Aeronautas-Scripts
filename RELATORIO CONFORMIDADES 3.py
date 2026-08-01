import csv
import calendar
import datetime
import os
import pathlib
import sys
import json
import re
import unicodedata
import tkinter as tk
from tkinter import filedialog
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type, Set, Tuple
import pandas as pd
from pytz import timezone, UnknownTimeZoneError
import textwrap

import sys
from contextlib import contextmanager

@contextmanager
def smart_open(filename=None, mode='w'):
    if filename:
        f = open(filename, mode)
        try:
            yield f
        finally:
            f.close()
    else:
        yield sys.stdout

# --- Caminho base dos JSONs de regras ---
REGRAS_JSON_PATH = pathlib.Path(BASE_OFFICIAL_DOCS_PATH / "regras_json")
METADATA_EOS_PATH = pathlib.Path(BASE_LEGISLACAO_PATH / "metadata_eos.json")
LIMITS_MATRIX_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "limits_matrix_cells_from_rows.json")
LIMITS_MATRIX_B3_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "limits_matrix_b3_comissarios.json")
LIMITS_E2_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "limits_e2_tripulacao_simples.json")
LIMITS_A3_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "limits_a3_mensal_anual.json")
TABELA_B2_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "Tabela B.2.json")
TABELA_B3_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "Tabela B.3.json")
TABELA_A4_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "Tabela A.4.json")
TABELA_A5_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "Tabela A.5.json")
LOCAL_TEXT_LIMITS_PATH = pathlib.Path(__file__).with_name("cct_text_limits_local.json")
ATIVIDADES_ESCALA_LATAM_PATH = pathlib.Path(BASE_COMMON_FILES_PATH / "AtividadesEscalaLATAM.json")


def _parse_hhmm_to_minutes(s: str) -> int:
    """Converte string 'HH:MM' em total de minutos."""
    try:
        h, m = s.split(':')
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _extract_first_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    m = re.search(r"(\d+)", str(value))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _normalize_text(value: str) -> str:
    """Normaliza texto para comparação: remove acentos, converte para maiúsculas e remove espaços extras."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ASCII", "ignore").decode("ASCII")
    return " ".join(text.upper().strip().split())


def _looks_like_flight_code(value: str) -> bool:
    """Heurística para identificar número de voo real (ex.: LA1234)."""
    v = _normalize_text(value)
    if not v:
        return False
    return re.fullmatch(r"[A-Z]{1,3}\d{2,5}[A-Z]?", v) is not None


def _entry_matches_latam_catalog(entry: "ScheduleEntry", latam_activities_set: Set[str]) -> bool:
    """Retorna True quando a entrada encontra correspondência no catálogo LATAM."""
    if not latam_activities_set:
        return True
    candidates = {
        _normalize_text(entry.tipo_atividade or ""),
        _normalize_text(entry.voo_numero or ""),
        _normalize_text(entry.descricao or ""),
    }
    candidates.discard("")
    return any(candidate in latam_activities_set for candidate in candidates)


def _is_voo_activity(entry: "ScheduleEntry", folgas_set: Set[str], latam_activities_set: Optional[Set[str]] = None) -> bool:
    """Classifica atividade de voo usando folgas + heurística + catálogo LATAM."""
    if entry.is_folga(folgas_set):
        return False

    if _looks_like_flight_code(entry.voo_numero or ""):
        return True
    if _looks_like_flight_code(entry.tipo_atividade or ""):
        return True

    atividade = str(entry.tipo_atividade or "").upper().strip()
    if atividade.startswith("AD"):
        if latam_activities_set:
            return _entry_matches_latam_catalog(entry, latam_activities_set)
        return True

    return False


MINUTES_PER_CIVIL_DAY = 24 * 60
DAYS_PER_CIVIL_WEEK = 7


def _civil_week_bounds(ref_date: datetime.date) -> Tuple[datetime.date, datetime.date]:
    """Retorna a semana civil domingo-sábado que contém a data informada."""
    start = ref_date - datetime.timedelta(days=(ref_date.weekday() + 1) % 7)
    end = start + datetime.timedelta(days=DAYS_PER_CIVIL_WEEK - 1)
    return start, end


class LimitsLoader:
    """
    Carrega e interpreta os limites operacionais dos arquivos JSON de regras.
    Fontes:
      - legal_overrides.json  → b1_overrides.cells_by_bucket (FDP máx por horário/pousos)
      - legal_overrides.json  → rest.ranges (repouso mínimo por FDP realizado)
      - rbac117_rulepack.json → fallback (b1.cells_by_bucket FRMS_ON e rest.ranges)
    """

    def __init__(self, json_dir: pathlib.Path = REGRAS_JSON_PATH):
        self._b1_cells: Dict[str, Dict] = {}   # "FRMS_OFF>SIMPLES>ACLIMATADO>06:00-07:59>1-2" → {fdp_max, voo_max, ...}
        self._b3_cells: Dict[str, Dict] = {}   # "FRMS_OFF>AUMENTADA>ACLIMATADO>07:00-13:59>3-4" → {fdp_max, voo_max, ...}
        self._e2_simple: Dict[str, Dict[str, Optional[str]]] = {}  # "PADRAO" → {fdp_max, voo_max}
        self._a3_limits: Dict[str, Dict[str, int]] = {}  # "AVIÕES A JATO" → {limite_horas_voo_mensais, ...}
        self._text_limits: Dict[str, Any] = {}  # regras textuais: folgas, sexto período, madrugadas
        self._rest_ranges: List[Dict] = []      # [{fdp_min, fdp_max, descanso_min, crew_type, aclim, frms}, ...]
        self._special_duty_limits_min: Dict[str, Dict[str, int]] = {"reserva": {}, "sobreaviso": {}}
        self._standby_rules: Dict[str, Dict[str, Any]] = {}
        self._load(json_dir)

    def _load(self, json_dir: pathlib.Path):
        matrix_path = LIMITS_MATRIX_PATH
        b3_matrix_path = LIMITS_MATRIX_B3_PATH
        e2_path = LIMITS_E2_PATH
        a3_path = LIMITS_A3_PATH
        a4_path = TABELA_A4_PATH
        a5_path = TABELA_A5_PATH
        overrides_path = json_dir / "legal_overrides.json"
        rulepack_path  = json_dir / "rbac117_rulepack.json"

        def _crew_alias(crew_label: str) -> str:
            n = _normalize_text(crew_label)
            if any(x in n for x in ["MINIMA", "SIMPLES"]):
                return "SIMPLES"
            if any(x in n for x in ["COMPOSTA", "AUMENTADA"]):
                return "AUMENTADA"
            if "REVEZAMENTO" in n or "COMPLEMENTADA" in n:
                return "COMPLEMENTADA"
            return "SIMPLES"

        # --- Tabela A.4 (reserva) ---
        if a4_path.exists():
            try:
                with open(a4_path, encoding='utf-8') as f:
                    a4_data = json.load(f)
                if isinstance(a4_data, list):
                    for row in a4_data:
                        if not isinstance(row, dict):
                            continue
                        crew = _crew_alias(row.get("0", ""))
                        hours = _extract_first_int(row.get("1"))
                        if hours is not None:
                            self._special_duty_limits_min.setdefault("reserva", {})[crew] = hours * 60
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{a4_path.name}': {e}")

                pass
        # --- Tabela A.5 (sobreaviso) ---
        if a5_path.exists():
            try:
                with open(a5_path, encoding='utf-8') as f:
                    a5_data = json.load(f)
                if isinstance(a5_data, list):
                    for row in a5_data:
                        if not isinstance(row, dict):
                            continue
                        crew = _crew_alias(row.get("0", ""))
                        hours = _extract_first_int(row.get("1"))
                        if hours is not None:
                            self._special_duty_limits_min.setdefault("sobreaviso", {})[crew] = hours * 60
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{a5_path.name}': {e}")

                pass
        # --- limits_matrix_cells_from_rows.json (fonte granular preferencial para FDP/VOO) ---
        if matrix_path.exists():
            try:
                with open(matrix_path, encoding='utf-8') as f:
                    matrix_data = json.load(f)
                loaded = 0
                for frms_key, frms_block in matrix_data.items():
                    cells = frms_block.get("cells", {}) if isinstance(frms_block, dict) else {}
                    for bucket_key, cell in cells.items():
                        # full_key: FRMS_OFF>SIMPLES>ACLIMATADO>13:00-14:59>3-4
                        self._b1_cells[f"{frms_key}>{bucket_key}"] = cell
                        loaded += 1
                # print(f"[LimitsLoader] {loaded} células FDP/VOO granulares carregadas de '{matrix_path.name}'.")
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{matrix_path.name}': {e}")

                pass
        # --- limits_matrix_b3_comissarios.json (cabine/comissários) ---
        if b3_matrix_path.exists():
            try:
                with open(b3_matrix_path, encoding='utf-8') as f:
                    b3_data = json.load(f)
                loaded_b3 = 0
                for frms_key, frms_block in b3_data.items():
                    cells = frms_block.get("cells", {}) if isinstance(frms_block, dict) else {}
                    for bucket_key, cell in cells.items():
                        self._b3_cells[f"{frms_key}>{bucket_key}"] = cell
                        loaded_b3 += 1
                # print(f"[LimitsLoader] {loaded_b3} células FDP/VOO para cabine carregadas de '{b3_matrix_path.name}'.")
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{b3_matrix_path.name}': {e}")

                pass
        # --- limits_e2_tripulacao_simples.json (tripulação simples) ---
        if e2_path.exists():
            try:
                with open(e2_path, encoding='utf-8') as f:
                    e2_data = json.load(f)
                for scenario, cell in (e2_data.items() if isinstance(e2_data, dict) else []):
                    scenario_key = _normalize_text(scenario)
                    if not scenario_key:
                        continue
                    self._e2_simple[scenario_key] = {
                        "fdp_max": cell.get("fdp_max") if isinstance(cell, dict) else None,
                        "voo_max": cell.get("voo_max") if isinstance(cell, dict) else None,
                    }
                if self._e2_simple:
                    # print(f"[LimitsLoader] {len(self._e2_simple)} cenários E.2 carregados de '{e2_path.name}'.")
                    pass
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{e2_path.name}': {e}")

                pass
        # --- limits_a3_mensal_anual.json (limites mensais/anuais) ---
        if a3_path.exists():
            try:
                with open(a3_path, encoding='utf-8') as f:
                    a3_data = json.load(f)
                for aircraft_type, cfg in (a3_data.items() if isinstance(a3_data, dict) else []):
                    key = _normalize_text(aircraft_type)
                    if not key or not isinstance(cfg, dict):
                        continue
                    mensais = cfg.get("limite_horas_voo_mensais")
                    anuais = cfg.get("limite_horas_voo_anuais")
                    if mensais is None or anuais is None:
                        continue
                    self._a3_limits[key] = {
                        "limite_horas_voo_mensais": int(mensais),
                        "limite_horas_voo_anuais": int(anuais),
                    }
                if self._a3_limits:
                    # print(f"[LimitsLoader] {len(self._a3_limits)} limites A.3 carregados de '{a3_path.name}'.")
                    pass
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{a3_path.name}': {e}")

                pass
        # --- legal_overrides.json (fonte primária) ---
        if overrides_path.exists():
            try:
                with open(overrides_path, encoding='utf-8') as f:
                    data = json.load(f)
                # FDP cells (b1_overrides)
                for frms_key, cells in data.get("b1_overrides", {}).get("cells_by_bucket", {}).items():
                    for bucket_key, cell in cells.items():
                        self._b1_cells[f"{frms_key}>{bucket_key}"] = cell
                # Repouso mínimo (rest.ranges)
                for frms_key, ranges in data.get("rest", {}).get("ranges", {}).items():
                    if isinstance(ranges, list):
                        for r in ranges:
                            self._rest_ranges.append({**r, "_frms": frms_key})
                # Regras textuais consolidadas
                if isinstance(data.get("text_limits"), dict):
                    self._text_limits = data.get("text_limits", {})
                # Regras de sobreaviso/reserva (standby)
                standby = data.get("standby", {}) if isinstance(data, dict) else {}
                if isinstance(standby, dict):
                    for rule in standby.get("rules", []) if isinstance(standby.get("rules", []), list) else []:
                        if not isinstance(rule, dict):
                            continue
                        st_type = _normalize_text(rule.get("type", ""))
                        if not st_type:
                            continue
                        self._standby_rules[st_type] = rule
                # print(f"[LimitsLoader] {len(self._b1_cells)} células FDP e {len(self._rest_ranges)} regras de repouso carregadas de '{overrides_path.name}'.")
                self._print_rest_summary()
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{overrides_path.name}': {e}")

                pass
        # --- cct_text_limits_local.json (overlay local no workspace) ---
        if LOCAL_TEXT_LIMITS_PATH.exists():
            try:
                with open(LOCAL_TEXT_LIMITS_PATH, encoding='utf-8') as f:
                    local_data = json.load(f)
                local_tl = local_data.get("text_limits", {}) if isinstance(local_data, dict) else {}
                if isinstance(local_tl, dict):
                    base = self._text_limits if isinstance(self._text_limits, dict) else {}
                    base.update(local_tl)
                    self._text_limits = base
                    # print(f"[LimitsLoader] text_limits local carregado de '{LOCAL_TEXT_LIMITS_PATH.name}'.")
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{LOCAL_TEXT_LIMITS_PATH.name}': {e}")

                pass
        # --- rbac117_rulepack.json (fallback) ---
        if rulepack_path.exists():
            try:
                with open(rulepack_path, encoding='utf-8') as f:
                    data = json.load(f)
                # b1 cells (complementa o que não veio do overrides)
                for frms_key, cells in data.get("b1", {}).get("cells_by_bucket", {}).items():
                    for bucket_key, cell in cells.items():
                        key = f"{frms_key}>{bucket_key}"
                        if key not in self._b1_cells:
                            self._b1_cells[key] = cell
                # Repouso (fallback se overrides não carregou)
                if not self._rest_ranges:
                    for frms_key, ranges in data.get("rest", {}).get("ranges", {}).items():
                        if isinstance(ranges, list):
                            for r in ranges:
                                self._rest_ranges.append({**r, "_frms": frms_key})
            except Exception as e:
                # print(f"[LimitsLoader] Aviso: falha ao ler '{rulepack_path.name}': {e}")

                pass
    def _cells_for_funcao(self, funcao: str) -> Dict[str, Dict]:
        """Seleciona o repositório de células conforme função (piloto x comissário)."""
        f = _normalize_text(funcao)
        if ("COMISS" in f or "CABINE" in f) and self._b3_cells:
            return self._b3_cells
        return self._b1_cells

    def _get_e2_scenario_cell(self, is_wocl: bool = False, is_longa: bool = False) -> Optional[Dict[str, Optional[str]]]:
        """Retorna cenário E.2 para tripulação simples quando aplicável."""
        if not self._e2_simple:
            return None
        preferred = []
        if is_longa and is_wocl:
            preferred.append("LONGA NA WOCL")
        if is_longa:
            preferred.append("LONGA")
        if is_wocl:
            preferred.append("NA WOCL")
        preferred.append("PADRAO")
        preferred.append("PADRÃO")
        for key in preferred:
            k = _normalize_text(key)
            if k in self._e2_simple:
                return self._e2_simple[k]
        return None

    def _infer_a3_key_from_aircraft(self, tipo_aeronave_principal: str) -> Optional[str]:
        t = _normalize_text(tipo_aeronave_principal)
        if not t:
            return None
        if "JATO" in t:
            return _normalize_text("AVIÕES A JATO")
        if "TURBO" in t:
            return _normalize_text("AVIÕES TURBOÉLICE")
        if "CONVENC" in t:
            return _normalize_text("AVIÕES CONVENCIONAIS")
        if "HELIC" in t:
            return _normalize_text("HELICÓPTEROS")
        return None

    def get_monthly_annual_voo_limits(self, tipo_aeronave_principal: str) -> Optional[Dict[str, int]]:
        """Retorna limites A.3 (mensal/anual) para o tipo de aeronave do perfil."""
        key = self._infer_a3_key_from_aircraft(tipo_aeronave_principal)
        if key and key in self._a3_limits:
            return self._a3_limits[key]
        return None

    def get_text_limits(self) -> Dict[str, Any]:
        return self._text_limits if isinstance(self._text_limits, dict) else {}

    def get_folgas_limits(self) -> Dict[str, Any]:
        tl = self.get_text_limits()
        folgas = tl.get("folgas", {}) if isinstance(tl, dict) else {}
        return folgas if isinstance(folgas, dict) else {}

    def get_madrugadas_limits(self) -> Dict[str, Any]:
        tl = self.get_text_limits()
        madrugadas = tl.get("madrugadas", {}) if isinstance(tl, dict) else {}
        return madrugadas if isinstance(madrugadas, dict) else {}

    def get_sexto_periodo_limit(self) -> Optional[int]:
        tl = self.get_text_limits()
        sp = tl.get("sexto_periodo", {}) if isinstance(tl, dict) else {}
        if not isinstance(sp, dict):
            return None
        dias = sp.get("dias_trabalho_entre_folgas", {})
        if not isinstance(dias, dict):
            return None
        v = dias.get("max_periodos_24h_consecutivos")
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    def get_jornada_semanal_limits(self) -> Dict[str, Any]:
        tl = self.get_text_limits()
        jsm = tl.get("jornada_semanal_mensal", {}) if isinstance(tl, dict) else {}
        return jsm if isinstance(jsm, dict) else {}

    def get_special_duty_limit_minutes(self, special_type: str, crew_type: str = "SIMPLES") -> Optional[int]:
        """Retorna limite em minutos para tipos especiais (reserva/sobreaviso)."""
        st = _normalize_text(special_type)
        crew = _normalize_text(crew_type)

        # Prioridade 1: standby.rules em legal_overrides.json
        standby_rule = self._standby_rules.get(st)
        if isinstance(standby_rule, dict):
            max_duration = standby_rule.get("max_duration")
            if isinstance(max_duration, str) and ":" in max_duration:
                return _parse_hhmm_to_minutes(max_duration)

        # Prioridade 2: Tabela A.4/A.5 mapeada por tipo de tripulação
        crew_map = self._special_duty_limits_min.get(st, {})
        if not isinstance(crew_map, dict) or not crew_map:
            return None

        if "SIMPLES" in crew:
            key = "SIMPLES"
        elif "AUMENTADA" in crew:
            key = "AUMENTADA"
        elif "COMPLEMENTADA" in crew:
            key = "COMPLEMENTADA"
        else:
            key = "SIMPLES"

        return crew_map.get(key)

    def find_applicable_cell(
        self,
        hora_local: datetime.time,
        pousos: int = 1,
        crew_type: str = "SIMPLES",
        aclim: str = "ACLIMATADO",
        frms: str = "OFF",
        funcao: str = "PILOTO"
    ) -> Optional[Tuple[Dict[str, Any], str, str]]:
        """Retorna célula aplicada + bucket horário + bucket pousos para as condições dadas."""
        hora_min = hora_local.hour * 60 + hora_local.minute
        pousos_bkt = self._pousos_bucket(pousos)
        frms_key = f"FRMS_{frms}"

        selected_cells = self._cells_for_funcao(funcao)
        chosen_cell: Optional[Dict[str, Any]] = None
        chosen_hora_bucket: Optional[str] = None
        best_fdp_min: Optional[int] = None
        best_span: Optional[int] = None

        for full_key, cell in selected_cells.items():
            partes = full_key.split('>')
            if len(partes) != 5:
                continue
            k_frms, k_crew, k_aclim, k_hora, k_pousos = partes
            if k_frms != frms_key:
                continue
            if k_crew != crew_type:
                continue
            if k_aclim != aclim:
                continue
            if k_pousos != pousos_bkt:
                continue
            if not self._hora_matches_bucket(hora_min, k_hora):
                continue
            fdp_str = cell.get("fdp_max")
            if not fdp_str:
                continue

            fdp_min = _parse_hhmm_to_minutes(fdp_str)
            span = self._bucket_span_minutes(k_hora)
            if best_span is None or span < best_span:
                best_span = span
                best_fdp_min = fdp_min
                chosen_cell = cell
                chosen_hora_bucket = k_hora
            elif span == best_span and (best_fdp_min is None or fdp_min < best_fdp_min):
                best_fdp_min = fdp_min
                chosen_cell = cell
                chosen_hora_bucket = k_hora

        if chosen_cell is None or chosen_hora_bucket is None:
            return None
        return chosen_cell, chosen_hora_bucket, pousos_bkt

    def _print_rest_summary(self):
        """Exibe no terminal as faixas de repouso únicas carregadas do JSON (deduplificadas por fdp_min/fdp_max)."""
        seen = {}
        for r in self._rest_ranges:
            key = (r.get("fdp_min", "?"), r.get("fdp_max") or "sem limite", r.get("descanso_min", "?"))
            seen[key] = key
        # print("[LimitsLoader] Faixas de repouso mínimo carregadas (por FDP realizado):")
        # print(f"  {'FDP de':>12} | {'FDP até':>12} | {'Repouso mínimo':>14}")
        # print(f"  {'-'*12}-+-{'-'*12}-+-{'-'*14}")
        for fdp_min, fdp_max, descanso in sorted(seen.keys()):
            # print(f"  {fdp_min:>12} | {fdp_max:>12} | {descanso:>14}")

            pass
    # ------------------------------------------------------------------
    def _hora_matches_bucket(self, hora_minutos: int, bucket: str) -> bool:
        """Verifica se um horário (minutos desde 00:00) pertence ao bucket ex: '06:00-07:59'."""
        partes = bucket.split('-')
        if len(partes) != 2:
            return False
        start_min = _parse_hhmm_to_minutes(partes[0])
        end_min   = _parse_hhmm_to_minutes(partes[1])
        if start_min <= end_min:
            return start_min <= hora_minutos <= end_min
        else:  # bucket que cruza meia-noite, ex: "18:00-05:59"
            return hora_minutos >= start_min or hora_minutos <= end_min

    def _pousos_bucket(self, pousos: int) -> str:
        if pousos <= 2: return "1-2"
        elif pousos <= 4: return "3-4"
        elif pousos == 5: return "5"
        elif pousos == 6: return "6"
        else: return "7+"

    def _bucket_span_minutes(self, bucket: str) -> int:
        """Retorna duração da faixa horária em minutos para priorizar o bucket mais específico."""
        partes = bucket.split('-')
        if len(partes) != 2:
            return 24 * 60
        start_min = _parse_hhmm_to_minutes(partes[0])
        end_min = _parse_hhmm_to_minutes(partes[1])
        if start_min <= end_min:
            return (end_min - start_min) + 1
        return ((24 * 60 - start_min) + end_min) + 1

    def get_fdp_max_minutes(
        self,
        hora_local: datetime.time,
        pousos: int = 1,
        crew_type: str = "SIMPLES",
        aclim: str = "ACLIMATADO",
        frms: str = "OFF",
        funcao: str = "PILOTO",
        is_wocl: bool = False,
        is_longa: bool = False
    ) -> Optional[int]:
        """
        Retorna o FDP máximo (em minutos) para as condições dadas.
        Quando múltiplos buckets cobrem o mesmo horário, retorna o mais restritivo (menor).
        """
        found = self.find_applicable_cell(
            hora_local,
            pousos=pousos,
            crew_type=crew_type,
            aclim=aclim,
            frms=frms,
            funcao=funcao,
        )
        if found is not None:
            cell, _, _ = found
            fdp_str = cell.get("fdp_max")
            if fdp_str:
                return _parse_hhmm_to_minutes(fdp_str)

        # Fallback E.2 (tripulação simples)
        if crew_type == "SIMPLES":
            e2_cell = self._get_e2_scenario_cell(is_wocl=is_wocl, is_longa=is_longa)
            if e2_cell and e2_cell.get("fdp_max"):
                return _parse_hhmm_to_minutes(e2_cell["fdp_max"])
        return None

    def get_voo_max_minutes(
        self,
        hora_local: datetime.time,
        pousos: int = 1,
        crew_type: str = "SIMPLES",
        aclim: str = "ACLIMATADO",
        frms: str = "OFF",
        funcao: str = "PILOTO",
        is_wocl: bool = False,
        is_longa: bool = False
    ) -> Optional[int]:
        """Retorna o tempo máximo de voo (em minutos) para as condições dadas."""
        found = self.find_applicable_cell(
            hora_local,
            pousos=pousos,
            crew_type=crew_type,
            aclim=aclim,
            frms=frms,
            funcao=funcao,
        )
        if found is not None:
            cell, _, _ = found
            voo_str = cell.get("voo_max")
            if voo_str:
                return _parse_hhmm_to_minutes(voo_str)

        # Fallback E.2 (tripulação simples)
        if crew_type == "SIMPLES":
            e2_cell = self._get_e2_scenario_cell(is_wocl=is_wocl, is_longa=is_longa)
            if e2_cell and e2_cell.get("voo_max"):
                return _parse_hhmm_to_minutes(e2_cell["voo_max"])
        return None

    def get_pousos_max(
        self,
        hora_local: datetime.time,
        pousos: int = 1,
        crew_type: str = "SIMPLES",
        aclim: str = "ACLIMATADO",
        frms: str = "OFF",
    ) -> Optional[int]:
        """Retorna pousos_max da célula aplicável, ou None se não definido."""
        found = self.find_applicable_cell(
            hora_local,
            pousos=pousos,
            crew_type=crew_type,
            aclim=aclim,
            frms=frms,
            funcao="PILOTO",
        )
        if found is not None:
            cell, _, _ = found
            return cell.get("pousos_max")  # int ou None
        return None

    def get_rest_min_minutes(
        self,
        fdp_minutes: int,
        crew_type: str = "SIMPLES",
        aclim: str = "ACLIMATADO",
        frms: str = "OFF"
    ) -> Optional[int]:
        """
        Retorna o repouso mínimo (em minutos) exigido após um FDP de 'fdp_minutes'.
        Quando múltiplas faixas se aplicam, retorna o mais restritivo (maior).
        """
        frms_key = f"FRMS_{frms}"
        aclim_norm = _normalize_text(aclim)

        def _calc_best(must_match_crew: bool) -> Optional[int]:
            best_val: Optional[int] = None
            for r in self._rest_ranges:
                if r.get("_frms") != frms_key:
                    continue
                if _normalize_text(r.get("aclim", "")) != aclim_norm:
                    continue
                if must_match_crew and _normalize_text(r.get("crew_type", "")) != _normalize_text(crew_type):
                    continue
                fdp_min_r = _parse_hhmm_to_minutes(r.get("fdp_min", "00:00"))
                fdp_max_str = r.get("fdp_max")
                fdp_max_r = _parse_hhmm_to_minutes(fdp_max_str) if fdp_max_str else 9999 * 60
                if fdp_min_r <= fdp_minutes <= fdp_max_r:
                    desc_str = r.get("descanso_min", "12:00")
                    val = _parse_hhmm_to_minutes(desc_str)
                    if best_val is None or val > best_val:
                        best_val = val
            return best_val

        # 1) tenta com crew_type específico
        best = _calc_best(must_match_crew=True)
        if best is not None:
            return best

        # 2) fallback sem distinção de tipo de tripulação
        return _calc_best(must_match_crew=False)

    def get_rest_ranges_snapshot(
        self,
        aclim: str = "ACLIMATADO",
        frms: str = "OFF",
    ) -> List[Dict[str, Optional[int]]]:
        """Retorna faixas de repouso deduplicadas para snapshot de relatório, sem distinção de função."""
        frms_key = f"FRMS_{frms}"
        aclim_norm = _normalize_text(aclim)
        seen = {}
        for r in self._rest_ranges:
            if r.get("_frms") != frms_key:
                continue
            if _normalize_text(r.get("aclim", "")) != aclim_norm:
                continue
            fdp_min = _parse_hhmm_to_minutes(r.get("fdp_min", "00:00"))
            fdp_max = _parse_hhmm_to_minutes(r.get("fdp_max")) if r.get("fdp_max") else None
            descanso = _parse_hhmm_to_minutes(r.get("descanso_min", "12:00"))
            key = (fdp_min, fdp_max)
            if key not in seen or descanso > seen[key]["descanso_min"]:
                seen[key] = {
                    "fdp_min": fdp_min,
                    "fdp_max": fdp_max,
                    "descanso_min": descanso,
                }
        return sorted(seen.values(), key=lambda x: (x["fdp_min"], x["fdp_max"] if x["fdp_max"] is not None else 9999 * 60))


# Singleton global do loader
_limits_loader_instance: Optional["LimitsLoader"] = None

def get_limits_loader() -> Optional["LimitsLoader"]:
    global _limits_loader_instance
    if _limits_loader_instance is None:
        try:
            _limits_loader_instance = LimitsLoader(REGRAS_JSON_PATH)
        except Exception as e:
            # print(f"[AVISO] Não foi possível inicializar LimitsLoader: {e}. Regras usarão valores hardcoded.")
            pass
    return _limits_loader_instance


# --- Funções de Suporte Globais ---
def load_folgas_config(file_path: pathlib.Path) -> Set[str]:
    """
    Carrega as atividades consideradas 'folga' de um arquivo JSON.
    O JSON DEVE ter a estrutura: {"lista_folgas": ["FOLGA", "RDO", ...]}
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de configuração de folgas não encontrado: {file_path}")
    try:
        raw = file_path.read_text(encoding='utf-8')
        try:
            config = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback para arquivo malformado: extrai tokens entre aspas,
            # descartando nomes de chaves conhecidas.
            quoted = re.findall(r'"([^"\\\n\r]+)"', raw)
            ignored_keys = {"LISTA_FOLGAS", "LISTA_FOLGAS_REGULAMENTARES"}
            folgas_fallback = [q for q in quoted if _normalize_text(q) not in ignored_keys]
            folgas_set = set(_normalize_text(x) for x in folgas_fallback if str(x).strip())
            if folgas_set:
                # print(f"[AVISO] JSON de folgas malformado em '{file_path.name}'. Usando parser de fallback.")
                return folgas_set
            raise

        if not isinstance(config, dict):
            return set()

        candidates = []
        for key in ("lista_folgas", "lista_folgas_regulamentares"):
            v = config.get(key, [])
            if isinstance(v, list):
                candidates.extend(v)

        return set(_normalize_text(activity) for activity in candidates if str(activity).strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Erro ao decodificar o arquivo JSON de folgas: {e}")
    except Exception as e:
        raise Exception(f"Erro ao carregar configuração de folgas: {e}")


def load_latam_activities_config(file_path: pathlib.Path) -> Set[str]:
    """Carrega AtividadesEscalaLATAM e retorna tokens normalizados de referência."""
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de atividades LATAM não encontrado: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, dict):
        activities = data.get("atividades", [])
    elif isinstance(data, list):
        activities = data
    else:
        activities = []

    tokens: Set[str] = set()
    for item in activities:
        if not isinstance(item, dict):
            continue
        for key in (
            "descricao_textual",
            "Descrição (descrição textual)",
            "codigo_ams",
            "Código AMS",
            "codigo_iflight_neo",
            "codigo_ifligth_neo",
            "Código iFligth Neo",
            "Código iFlight Neo",
            "descricao_resumida",
            "Descrição",
        ):
            token = _normalize_text(item.get(key, ""))
            if token:
                tokens.add(token)

    return tokens


def load_latam_activity_groups(file_path: pathlib.Path) -> Dict[str, Set[str]]:
    """Carrega grupos de atividade LATAM para classificação especial de jornada.

    Retorna sets normalizados para detecção de RESERVA e SOBREAVISO.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de atividades LATAM não encontrado: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    activities = data.get("atividades", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

    groups: Dict[str, Set[str]] = {
        "reserva": set(),
        "sobreaviso": set(),
    }

    for item in activities:
        if not isinstance(item, dict):
            continue
        ams = item.get("codigo_ams", "")
        neo = item.get("codigo_iflight_neo", "")
        resumo = item.get("descricao_resumida", "")

        ams_n = _normalize_text(ams)
        neo_n = _normalize_text(neo)
        resumo_n = _normalize_text(resumo)

        is_reserva = ("RESERVA" in ams_n) or resumo_n.startswith("ASB")
        is_sobreaviso = (
            ("SOBRE AVISO" in ams_n)
            or ("SOBREAVISO" in ams_n)
            or resumo_n == "HSB"
        )

        if is_reserva:
            for token in (ams_n, neo_n, resumo_n):
                if token:
                    groups["reserva"].add(token)

        if is_sobreaviso:
            for token in (ams_n, neo_n, resumo_n):
                if token:
                    groups["sobreaviso"].add(token)

    return groups


def _infer_entry_special_duty_type(entry: "ScheduleEntry", profile: "AeronautaProfile") -> Optional[str]:
    """Classifica entrada LATAM em tipo especial de jornada (reserva/sobreaviso)."""
    candidates = {
        _normalize_text(entry.tipo_atividade or ""),
        _normalize_text(entry.voo_numero or ""),
        _normalize_text(entry.descricao or ""),
    }
    candidates.discard("")

    if any(c in profile.latam_sobreaviso_codes_set for c in candidates):
        return "sobreaviso"
    if any(c in profile.latam_reserva_codes_set for c in candidates):
        return "reserva"

    # Fallback heurístico (útil em testes manuais sem os grupos carregados no perfil).
    raw_code = _normalize_text(entry.tipo_atividade or "")
    if raw_code in {"HSB", "SA", "SAM", "SAT", "SAMB", "SATB", "SAMR", "SATR"}:
        return "sobreaviso"
    if raw_code.startswith("ASB") or raw_code.startswith("RES") or raw_code in {"RGRU", "RCGH", "RSDU"}:
        return "reserva"
    return None


def load_company_metadata(metadata_path: pathlib.Path) -> Dict[str, Dict[str, Any]]:
    """Carrega o metadata_eos.json e cria índices por nome abreviado, nome completo e COA."""
    if not metadata_path.exists():
        return {"records": [], "by_abbrev": {}, "by_name": {}, "by_coa": {}}

    with open(metadata_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    records = data.get("empresas_rbac_121", [])
    by_abbrev: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    by_coa: Dict[str, Dict[str, Any]] = {}

    for item in records:
        nome_abreviado = _normalize_text(item.get("nome_abreviado", ""))
        nome_completo = _normalize_text(item.get("nome_completo", ""))
        coa_id = _normalize_text(item.get("coa_id", ""))
        if nome_abreviado:
            by_abbrev[nome_abreviado] = item
        if nome_completo:
            by_name[nome_completo] = item
        if coa_id:
            by_coa[coa_id] = item

    return {"records": records, "by_abbrev": by_abbrev, "by_name": by_name, "by_coa": by_coa}


def parse_aeronauta_context_from_filename(file_path: pathlib.Path, company_metadata: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """Extrai nome, matrícula, base, função e empresa a partir do nome do CSV."""

    stem = file_path.stem
    tokens = [t for t in stem.split('_') if t]
    # Remove prefixos conhecidos
    while tokens and tokens[0].lower() in {'escala', 'e', 'p'}:
        tokens.pop(0)

    # Remove datas, versao, execucao e outros sufixos conhecidos do final
    while tokens and (re.fullmatch(r'\d{8}', tokens[-1]) or 'VERSAO' in tokens[-1].upper() or re.fullmatch(r'\d{6}', tokens[-1])):
        tokens.pop()

    # Identifica base (primeiro token de 3 letras)
    base_idx = next((i for i, t in enumerate(tokens) if re.fullmatch(r'[A-Z]{3}', t.upper())), None)
    base = tokens[base_idx] if base_idx is not None else ''

    # Matrícula: próximo token numérico após base
    matricula = ''
    empresa_token = ''
    funcao_tokens = []
    nome_tokens = []
    tipos_aeronave = {"JATO", "TURBO-HELICE", "CONVENCIONAL", "HELICOPTERO", "HELICÓPTERO", "PLANADOR", "ANFIBIO", "ANFÍBIO"}
    plataformas = {"SIMPL", "SIMPLES", "COMPL", "COMPLEMENTADA", "AUMENTADA", "INSTRUTOR", "EXTRA", "RESERVA", "SOBREAVISO", "PLANTAO", "PLANTÃO"}
    if base_idx is not None:
        nome_tokens = tokens[:base_idx]
        after_base = tokens[base_idx+1:]
        # Matrícula
        if after_base and re.fullmatch(r'\d+', after_base[0]):
            matricula = after_base[0]
            after_base = after_base[1:]
        # Empresa
        if after_base:
            empresa_token = after_base[0]
            after_base = after_base[1:]
        # Função: todos os tokens até encontrar um token que seja data, versão ou tipo de aeronave
        for t in after_base:
            t_norm = t.upper().replace('-', '').replace('Í', 'I').replace('Ó', 'O')
            if re.fullmatch(r'\d{8}', t) or 'VERSAO' in t_norm or re.fullmatch(r'\d{6}', t):
                break
            if t_norm in {x.replace('-', '').replace('Í', 'I').replace('Ó', 'O') for x in tipos_aeronave}:
                break
            if t_norm in {x.replace('-', '').replace('Í', 'I').replace('Ó', 'O') for x in plataformas}:
                break
            funcao_tokens.append(t)
    nome = ' '.join(nome_tokens).replace('__', ' ').replace('_', ' ').replace('  ', ' ').strip().title()
    funcao = ' '.join(funcao_tokens).replace('_', ' ').strip().upper()

    # Busca empresa no metadata (opcional)
    abbrev_lookup = company_metadata.get('by_abbrev', {})
    company_data = abbrev_lookup.get(_normalize_text(empresa_token), {})

    empresa_nome_completo = company_data.get('nome_completo', empresa_token)
    empresa_nome_abreviado = company_data.get('nome_abreviado', empresa_token)
    empresa_nome_fantasia = company_data.get('nome_fantasia', empresa_token)
    empresa_cnpj = company_data.get('cnpj', '')
    empresa_rbac_tipo = company_data.get('rbac_tipo', '')
    empresa_tipo_operacao = company_data.get('tipo_operacao', '')
    empresa_gestao_fadiga = company_data.get('gestao_fadiga', '')

    return {
        'nome': nome.strip(),
        'matricula': matricula,
        'base': base,
        'funcao': funcao,
        'empresa_nome_completo': empresa_nome_completo,
        'empresa_nome_abreviado': empresa_nome_abreviado,
        'empresa_nome_fantasia': empresa_nome_fantasia,
        'empresa_cnpj': empresa_cnpj,
        'empresa_rbac_tipo': empresa_rbac_tipo,
        'empresa_tipo_operacao': empresa_tipo_operacao,
        'empresa_gestao_fadiga': empresa_gestao_fadiga,
    }


def infer_audit_month_from_filename(file_path: pathlib.Path) -> Optional[Tuple[int, int]]:
    """Infere ano/mês de auditoria a partir de datas DDMMYYYY no nome do arquivo."""
    stem = file_path.stem
    date_tokens = re.findall(r"(?<!\d)(\d{8})(?!\d)", stem)

    # Ignora datas que fazem parte de sufixo de timestamp de processamento:
    # padrão "..._DDMMYYYY_HHMMSS" no final do nome do arquivo.
    timestamp_date_tokens = set(re.findall(r"(?<!\d)(\d{8})_\d{6}(?!\d)", stem))
    if timestamp_date_tokens:
        date_tokens = [tok for tok in date_tokens if tok not in timestamp_date_tokens]

    parsed_dates: List[datetime.date] = []

    for tok in date_tokens:
        try:
            parsed_dates.append(datetime.datetime.strptime(tok, "%d%m%Y").date())
        except Exception:
            continue

    if not parsed_dates:
        return None

    parsed_dates.sort()
    first = parsed_dates[0]
    return (first.year, first.month)


# --- 1. Definições de Modelos de Dados (Classes) ---

class AeronautaProfile:
    """Representa o perfil de um aeronauta com dados relevantes para a auditoria."""
    def __init__(self,
                 nome: str,
                 matricula: str,
                 base_domiciliar: str,           # Ex: "GRU", "GIG"
                 fuso_base: str,                 # Ex: "America/Sao_Paulo"
                 tipo_aeronave_principal: str,   # Ex: "JATO", "TURBO-HELICE", "CONVENCIONAL"
                 funcao: str,                    # Ex: "PILOTO", "COMISSARIO"
                 cct_aplicavel: str = "PADRAO",  # Nome da CCT ou ACT
                 crew_type: str = "SIMPLES",     # "SIMPLES", "AUMENTADA", "COMPLEMENTADA"
                 frms: str = "OFF",              # "OFF" ou "ON"
                 aclimatado: str = "ACLIMATADO", # "ACLIMATADO" ou "NAO_ACLIMATADO"
                 empresa_nome_completo: str = "",
                 empresa_nome_abreviado: str = "",
                 empresa_nome_fantasia: str = "",
                 empresa_cnpj: str = "",
                 empresa_rbac_tipo: str = "",
                 empresa_tipo_operacao: str = "",
                 empresa_gestao_fadiga: str = ""
                 ):
        self.nome = nome
        self.matricula = matricula
        self.base_domiciliar = base_domiciliar
        try:
            self.fuso_base = timezone(fuso_base)
        except UnknownTimeZoneError:
            raise ValueError(f"Fuso horário '{fuso_base}' inválido. Verifique a lista de fusos horários IANA.")
        self.tipo_aeronave_principal = tipo_aeronave_principal
        self.funcao = funcao
        self.cct_aplicavel = cct_aplicavel
        self.crew_type = crew_type
        self.frms = frms
        self.aclimatado = aclimatado
        self.empresa_nome_completo = empresa_nome_completo
        self.empresa_nome_abreviado = empresa_nome_abreviado
        self.empresa_nome_fantasia = empresa_nome_fantasia
        self.empresa_cnpj = empresa_cnpj
        self.empresa_rbac_tipo = empresa_rbac_tipo
        self.empresa_tipo_operacao = empresa_tipo_operacao
        self.empresa_gestao_fadiga = empresa_gestao_fadiga
        self.folgas_set: Set[str] = set() # Inicializa vazio, será preenchido no main
        self.latam_activities_set: Set[str] = set() # Catálogo AtividadesEscalaLATAM (quando aplicável)
        self.latam_reserva_codes_set: Set[str] = set()
        self.latam_sobreaviso_codes_set: Set[str] = set()

    def get_local_datetime(self, dt_utc: datetime.datetime) -> datetime.datetime:
        """Converte um datetime UTC para o datetime local da base do aeronauta."""
        return dt_utc.astimezone(self.fuso_base)

    def get_utc_datetime(self, dt_local: datetime.datetime) -> datetime.datetime:
        """Converte um datetime local da base do aeronauta para UTC."""
        # Certifica-se de que o datetime local está "aware" do fuso horário antes de converter para UTC
        if dt_local.tzinfo is None or dt_local.tzinfo.utcoffset(dt_local) is None:
            dt_local = self.fuso_base.localize(dt_local)
        return dt_local.astimezone(timezone('UTC'))

    def __repr__(self):
        return (f"AeronautaProfile(Nome='{self.nome}', Matrícula='{self.matricula}', "
                f"Base='{self.base_domiciliar}', Função='{self.funcao}', "
                f"Empresa='{self.empresa_nome_abreviado or self.empresa_nome_completo}')")

class ScheduleEntry:
    """Representa uma única entrada na escala (voo, repouso, reserva, etc.)."""
    def __init__(self,
                 data: datetime.date,
                 tipo_atividade: str, # "VOO", "REP", "SBV", "RES", "ADM", "FOLGA", "TREINAMENTO"
                 hora_inicio: datetime.time,
                 hora_fim: datetime.time,
                 local_inicio: str = "",
                 local_fim: str = "",
                 descricao: str = "",
                 voo_numero: Optional[str] = None,
                 # Novos campos para o relatório detalhado
                 id_leg: str = "",
                 checkin: Optional[datetime.datetime] = None,
                 dep: Optional[datetime.datetime] = None,
                 arr: Optional[datetime.datetime] = None,
                 checkout: Optional[datetime.datetime] = None,
                 start_raw: str = "",
                 end_raw: str = "",
                 dep_raw: str = "",
                 arr_raw: str = "",
                 tempo_repouso_raw: str = "",
                 tempo_corte_raw: str = ""
                 ):
        self.data = data
        self.tipo_atividade = tipo_atividade
        self.hora_inicio = hora_inicio
        self.hora_fim = hora_fim
        self.local_inicio = local_inicio
        self.local_fim = local_fim
        self.descricao = descricao
        self.voo_numero = voo_numero
        
        # Atribuições dos novos campos
        self.id_leg = id_leg
        self.checkin = checkin
        self.dep = dep
        self.arr = arr
        self.checkout = checkout
        self.start_raw = start_raw
        self.end_raw = end_raw
        self.dep_raw = dep_raw
        self.arr_raw = arr_raw
        self.tempo_repouso_raw = tempo_repouso_raw
        self.tempo_corte_raw = tempo_corte_raw

    def get_start_datetime(self, profile: AeronautaProfile) -> datetime.datetime:
        """Retorna o datetime UTC de início da atividade."""
        return profile.get_utc_datetime(datetime.datetime.combine(self.data, self.hora_inicio))

    def get_end_datetime(self, profile: AeronautaProfile) -> datetime.datetime:
        """Retorna o datetime UTC de fim da atividade. Lida com atividades que viram o dia."""
        # Se a hora de fim for menor ou igual à hora de início, assume que a atividade virou o dia
        start_dt_local = datetime.datetime.combine(self.data, self.hora_inicio)
        end_dt_local = datetime.datetime.combine(self.data, self.hora_fim)
        if self.hora_fim <= self.hora_inicio: # Atividade vira o dia
            end_dt_local += datetime.timedelta(days=1)
        return profile.get_utc_datetime(end_dt_local)

    def duration_minutes(self, profile: AeronautaProfile) -> int:
        """Calcula a duração da atividade em minutos, considerando a virada do dia."""
        start_dt_utc = self.get_start_datetime(profile)
        end_dt_utc = self.get_end_datetime(profile)
        return int((end_dt_utc - start_dt_utc).total_seconds() / 60)

    def get_local_interval(self, profile: AeronautaProfile) -> Tuple[datetime.datetime, datetime.datetime]:
        """Retorna início e fim da atividade em horário local da base."""
        start_local = profile.get_local_datetime(self.get_start_datetime(profile))
        end_local = profile.get_local_datetime(self.get_end_datetime(profile))
        return start_local, end_local

    def civil_day_count(self, profile: AeronautaProfile) -> int:
        """Quantidade de dias civis completos cobertos pela atividade.

        Regra de ouro: um dia só existe quando a cobertura é de 00:00 a 00:00,
        com duração mínima de 24:00.
        """
        start_local, end_local = self.get_local_interval(profile)
        if end_local <= start_local:
            return 0
        if start_local.time() != datetime.time(0, 0):
            return 0
        if end_local.time() != datetime.time(0, 0):
            return 0
        total_minutes = int((end_local - start_local).total_seconds() / 60)
        if total_minutes < MINUTES_PER_CIVIL_DAY:
            return 0
        return (end_local.date() - start_local.date()).days

    def is_full_civil_day(self, profile: AeronautaProfile) -> bool:
        return self.civil_day_count(profile) >= 1

    def is_folga(self, folgas_set: Set[str]) -> bool:
        """Verifica se a Activity representa folga com base no conjunto configurado.

        Regras:
        - correspondência exata (após normalização);
        - correspondência contida com fronteira de token (ex.: "DR*", "FOLGA 24H").
        """
        atividade = str(self.tipo_atividade or "").upper().strip()
        if not atividade:
            return False

        folgas_norm = {str(f).upper().strip() for f in folgas_set if str(f).strip()}
        # Fallback mínimo regulatório para evitar que folgas fiquem sem classificação
        # quando o arquivo de folgas vier incompleto/malformado.
        folgas_norm.update({"DO", "DR", "RO", "RP", "RDO", "FOLGA"})
        if atividade in folgas_norm:
            return True

        for folga in folgas_norm:
            # Garante fronteira para não confundir códigos de voo com códigos curtos de folga.
            if re.search(rf"(?<![A-Z0-9]){re.escape(folga)}(?![A-Z0-9])", atividade):
                return True
        return False

    def get_report_data(self) -> Dict[str, str]:
        """
        Retorna um dicionário com os dados formatados das colunas
        Activity a Checkout para o relatório.
        """
        def _fmt(dt_value: Optional[datetime.datetime], raw_value: str = "") -> str:
            if dt_value is not None:
                try:
                    return dt_value.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            raw_value = (raw_value or "").strip()
            return raw_value if raw_value else "N/A"
        
        # Para End, combinar data da atividade com a hora de fim
        # A lógica de virada do dia é tratada na get_end_datetime, mas para a exibição aqui,
        # queremos a data original da atividade com a hora de fim.
        # Se a hora de fim for menor que a de início, o dia da atividade pode não ser o dia do End real.
        # O mais seguro é pegar o datetime que gerou o `end_datetime_full` antes de extrair `hora_fim`.
        # No entanto, para simplificar e dado que o problema é a linha do CSV, usamos a data original + hora_fim.
        end_dt_for_report = datetime.datetime.combine(self.data, self.hora_fim)
        # Se o final da atividade virou o dia, o 'End' no CSV provavelmente reflete isso já na data
        # Mas como ScheduleEntry.data é só a data de início da atividade, combinamos com hora_fim
        # E o CSV pode ter 'End' com data diferente de 'Start'.
        # O ideal seria ScheduleEntry guardar a data exata do campo 'End' do CSV.
        # Por enquanto, mantemos essa lógica, mas se houver inconsistência, revisaremos.
        
        # A forma mais robusta seria ScheduleEntry armazenar o `end_datetime_full` diretamente
        # para exibição, em vez de `data` e `hora_fim` separadamente para o `End` do relatório.
        # Vamos usar o `end_datetime_full` que foi passado para o construtor, se possível,
        # ou reconstruir de `data` e `hora_fim` sabendo que pode não ser exato se virou o dia.
        # A opção mais segura é garantir que o ScheduleEntry armazene o `end_datetime_full` original.
        # Re-verificando o parse_schedule_csv, ele passa `hora_fim` e `data`.
        # Vamos presumir que para o relatório, o Start/End do ScheduleEntry são as referências do CSV.
        
        # Para exibir corretamente o `End` do CSV que pode virar o dia, precisamos do `end_datetime_full`
        # original do `parse_schedule_csv`. Vamos adicionar esse ao ScheduleEntry.
        # Por enquanto, vou usar o que temos, mas com a ressalva.
        # Uma correção mais robusta seria:
        # ScheduleEntry.__init__ adiciona: self.original_start_datetime_full = original_start_datetime_full
        #                                  self.original_end_datetime_full = original_end_datetime_full
        # e aqui usa esses campos. Por brevidade, vou reconstruir.
        
        # Para garantir que o `End` reflita o do CSV, se o `End` do CSV virou o dia, o `hora_fim`
        # do ScheduleEntry será menor que `hora_inicio`, mas o dia do `data` é o do `Start`.
        # Para este relatório, vamos pegar o campo `checkout` que já é um `datetime` completo.
        # Se o objetivo é 'Activity' até 'Checkout' como no cabeçalho original, então usaremos:
        # Activity, Id_Leg, Checkin, Start, Dep, Arr, End, Checkout
        
        # Para 'End', que é 'End' no cabeçalho do CSV:
        # Precisa-se do datetime original que foi lido para 'End'.
        # Atualmente ScheduleEntry.hora_fim é apenas o time.
        # Vamos retornar os datetimes que foram passados na criação do ScheduleEntry.
        
        # Refatorando get_report_data para usar os objetos datetime completos passados para o __init__
        return {
            "Activity": self.tipo_atividade,
            "Id_Leg": self.id_leg,
            "Checkin": _fmt(self.checkin),
            "Start": (self.start_raw.strip() if (self.start_raw or "").strip() else datetime.datetime.combine(self.data, self.hora_inicio).strftime('%Y-%m-%d %H:%M:%S')),
            "Dep": _fmt(self.dep, self.dep_raw),
            "Arr": _fmt(self.arr, self.arr_raw),
            # A coluna 'End' do CSV é tratada como `end_datetime_full` no parsing.
            # ScheduleEntry armazena apenas `hora_fim`.
            # Para reproduzir o 'End' do CSV, vamos usar o `checkout` como proxy
            # ou introduzir `original_end_datetime_full` no ScheduleEntry.
            # Dado que o pedido é 'Activity' até 'Checkout', vou usar o checkout para 'End' também.
            # Mas o mais preciso é ter um campo `original_end_datetime_full` no ScheduleEntry.
            # Para evitar mais mudanças agora, vou usar a hora_fim e data, mas se o CSV End virar dia,
            # pode parecer 'errado'.
            # A melhor solução é que ScheduleEntry.end_datetime seja o datetime completo do CSV 'End'.
            # Mudando ScheduleEntry para armazenar datetimes completos para Start e End.
            "End": (self.end_raw.strip() if (self.end_raw or "").strip() else _fmt(self.checkout)),
            "Checkout": _fmt(self.checkout)
        }


    def __repr__(self):
        return (f"<{self.data.strftime('%Y-%m-%d')} {self.tipo_atividade} "
                f"{self.hora_inicio.strftime('%H:%M')} - {self.hora_fim.strftime('%H:%M')}>")

class Jornada:
    """Representa uma jornada de trabalho, incluindo suas atividades."""
    def __init__(self, aeronauta_profile: AeronautaProfile, data: datetime.date):
        self.aeronauta_profile = aeronauta_profile
        self.data = data
        self.atividades: List[ScheduleEntry] = []
        self.hora_apresentacao: Optional[datetime.datetime] = None # UTC
        self.hora_encerramento: Optional[datetime.datetime] = None # UTC

    def _is_voo_atividade(self, atividade: ScheduleEntry) -> bool:
        """Identifica atividade aérea principal usada para cálculo de voo/pousos."""
        return _is_voo_activity(
            atividade,
            self.aeronauta_profile.folgas_set,
            self.aeronauta_profile.latam_activities_set,
        )

    def add_atividade(self, atividade: ScheduleEntry):
        self.atividades.append(atividade)
        # Re-sort para garantir ordem cronológica após adicionar
        self.atividades.sort(key=lambda x: x.get_start_datetime(self.aeronauta_profile))

        # Atualiza apresentação e encerramento da jornada com base nas atividades
        # A hora de apresentação é o checkin da atividade com id_leg terminado em '-I' ou '-IF'
        # Se não encontrar, usa a mais cedo de todas as atividades
        apresentacao_activity = None
        for a in self.atividades:
            if a.id_leg.endswith('-I') or a.id_leg.endswith('-IF'):
                apresentacao_activity = a
                break
        
        if apresentacao_activity and apresentacao_activity.checkin:
            # Garante que checkin está em UTC
            if apresentacao_activity.checkin.tzinfo is None:
                # Se naive, assume como hora local da base e converte para UTC
                checkin_local = apresentacao_activity.checkin
                self.hora_apresentacao = self.aeronauta_profile.get_utc_datetime(checkin_local)
            else:
                # Se já tem timezone, converte para UTC
                self.hora_apresentacao = apresentacao_activity.checkin.astimezone(datetime.timezone.utc)
        else:
            self.hora_apresentacao = min(
                [a.get_start_datetime(self.aeronauta_profile) for a in self.atividades]
            )
        
        # A hora de encerramento é a mais tarde de todas as atividades da jornada
        self.hora_encerramento = max(
            [a.get_end_datetime(self.aeronauta_profile) for a in self.atividades]
        )

    def duracao_jornada_minutos(self) -> int:
        """Calcula a duração total da jornada em minutos (apresentação a encerramento)."""
        if self.hora_apresentacao and self.hora_encerramento:
            return int((self.hora_encerramento - self.hora_apresentacao).total_seconds() / 60)
        return 0

    def horas_voo_total_minutos(self) -> int:
        """Calcula o tempo total de voo da jornada em minutos."""
        total_voo = 0
        for ativ in self.atividades:
            if self._is_voo_atividade(ativ):
                total_voo += ativ.duration_minutes(self.aeronauta_profile)
        return total_voo

    def numero_pousos(self) -> int:
        """Conta o número de pousos na jornada (assumindo 1 pouso por voo)."""
        return sum(1 for ativ in self.atividades if self._is_voo_atividade(ativ))

    def includes_night_duty(self) -> bool:
        """Verifica se a jornada inclui trabalho noturno (RBAC 117 A117.15(e))."""
        # WOCL (Window of Circadian Low) é de 02:00 a 05:59 hora local da base do aeronauta.
        # Considera "madrugada" se qualquer parte da jornada (apresentação a encerramento)
        # cair entre 00:00 e 06:00 hora local da base, utilizando os horários previstos.

        if not self.hora_apresentacao or not self.hora_encerramento:
            return False

        start_local = self.aeronauta_profile.get_local_datetime(self.hora_apresentacao)
        end_local = self.aeronauta_profile.get_local_datetime(self.hora_encerramento)

        # Madrugada do dia da jornada (00:00 a 06:00)
        madrugada_start_day = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
        madrugada_end_day = start_local.replace(hour=6, minute=0, second=0, microsecond=0)

        # Madrugada do dia seguinte (se a jornada virar o dia)
        madrugada_start_next_day = (start_local + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        madrugada_end_next_day = (start_local + datetime.timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)

        # Verifica sobreposição com a madrugada do dia da jornada
        overlap_day = (start_local < madrugada_end_day and end_local > madrugada_start_day)
        
        # Verifica sobreposição com a madrugada do dia seguinte (se a jornada se estender para lá)
        overlap_next_day = (start_local < madrugada_end_next_day and end_local > madrugada_start_next_day)

        return overlap_day or overlap_next_day

    def get_night_date(self) -> Optional[datetime.date]:
        """Retorna a data civil da madrugada (00:00 - 06:00) que esta jornada toca, se houver."""
        if not self.hora_apresentacao or not self.hora_encerramento:
            return None
            
        start_local = self.aeronauta_profile.get_local_datetime(self.hora_apresentacao)
        end_local = self.aeronauta_profile.get_local_datetime(self.hora_encerramento)
        
        madrugada_start_day = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
        madrugada_end_day = start_local.replace(hour=6, minute=0, second=0, microsecond=0)
        
        if max(start_local, madrugada_start_day) < min(end_local, madrugada_end_day):
            return start_local.date()
            
        next_day = start_local + datetime.timedelta(days=1)
        madrugada_start_next = next_day.replace(hour=0, minute=0, second=0, microsecond=0)
        madrugada_end_next = next_day.replace(hour=6, minute=0, second=0, microsecond=0)
        
        if max(start_local, madrugada_start_next) < min(end_local, madrugada_end_next):
            return next_day.date()
            
        return None

    def __repr__(self):
        return (f"<Jornada {self.data.strftime('%Y-%m-%d')} "
                f"Apresentação: {self.aeronauta_profile.get_local_datetime(self.hora_apresentacao).strftime('%H:%M') if self.hora_apresentacao else 'N/A'} "
                f"Encerramento: {self.aeronauta_profile.get_local_datetime(self.hora_encerramento).strftime('%H:%M') if self.hora_encerramento else 'N/A'} "
                f"Duração: {self.duracao_jornada_minutos() // 60}h{self.duracao_jornada_minutos() % 60}m>")

class Schedule:
    """Contém as jornadas de um aeronauta em um determinado mês."""
    def __init__(self, aeronauta_profile: AeronautaProfile):
        self.aeronauta_profile = aeronauta_profile
        self.jornadas: Dict[datetime.date, Jornada] = {}
        # Todas as entradas, para facilitar a análise sequencial
        self.all_entries: List[ScheduleEntry] = [] 

    def add_entry(self, entry: ScheduleEntry):
        self.all_entries.append(entry)
        # Mantém as jornadas separadas por dia para regras que precisam da agregação diária
        if not entry.is_folga(self.aeronauta_profile.folgas_set): # Jornadas são apenas atividades de trabalho
            if entry.data not in self.jornadas:
                self.jornadas[entry.data] = Jornada(self.aeronauta_profile, entry.data)
            self.jornadas[entry.data].add_atividade(entry)
        
        # Garante que all_entries esteja ordenada cronologicamente
        self.all_entries.sort(key=lambda x: x.get_start_datetime(self.aeronauta_profile))


    def get_jornadas_in_period(self, start_date: datetime.date, end_date: datetime.date) -> List[Jornada]:
        """Retorna as jornadas (de trabalho) dentro de um período."""
        return [j for date, j in self.jornadas.items() if start_date <= date <= end_date]

    def get_all_entries_in_period(self, start_date: datetime.date, end_date: datetime.date) -> List[ScheduleEntry]:
        """Retorna todas as entradas (trabalho, folga, repouso) dentro de um período."""
        return [e for e in self.all_entries if start_date <= e.data <= end_date]

# --- 2. Definições de Regras (Motor de Regras) ---

class Violation:
    """Representa uma violação de uma regra regulatória."""
    def __init__(self, rule_name: str, description: str, reference: str, severity: str = "ALTA",
                 details: str = "", relevant_entries_data: Optional[List[Dict[str, str]]] = None):
        self.rule_name = rule_name
        self.description = description
        self.reference = reference
        self.severity = severity
        self.details = details
        # Novo campo para armazenar os dados das linhas relevantes do CSV
        self.relevant_entries_data = relevant_entries_data if relevant_entries_data is not None else []

    def __repr__(self):
        return f"[VIOLATION] {self.rule_name} ({self.severity}): {self.description} ({self.reference}). {self.details}"

class Rule(ABC):
    """Classe base abstrata para todas as regras regulatórias."""
    def __init__(self, name: str, description: str, base_reference: str, priority: int = 100):
        self.name = name
        self.description = description
        self.base_reference = base_reference
        self.priority = priority # Menor número = maior prioridade

    @abstractmethod
    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        """Verifica a conformidade com esta regra."""
        pass

class DailyDutyLimitRule(Rule):
    """Regra: Limite de jornada diária (RBAC 117, L13475, CCT)."""
    def __init__(self, type_aeronave: str, funcao: str, cct_limit_hours: Optional[int] = None):
        super().__init__(
            name="Limite de Jornada Diária",
            description=f"Jornada diária não deve exceder o limite para {funcao} em aeronave {type_aeronave}.",
            base_reference="RBAC 117 A117.15(a) / L13475 Art. 36",
            priority=50
        )
        self.type_aeronave = type_aeronave
        self.funcao = funcao
        self.cct_limit_hours = cct_limit_hours

    def get_applicable_limit(
        self,
        aeronauta_profile: "AeronautaProfile",
        hora_apresentacao: Optional[datetime.time] = None,
        pousos: int = 1,
        is_wocl: bool = False,
        special_duty_type: Optional[str] = None,
    ) -> float:
        """
        Retorna o FDP máximo em horas (float).
        Prioridade: JSON (legal_overrides / rulepack) → hardcoded RBAC/Lei → CCT override.
        """
        loader = get_limits_loader()

        # Limites especiais por tipo de programação (ex.: SOBREAVISO/RESERVA).
        if loader is not None and special_duty_type:
            special_limit_min = loader.get_special_duty_limit_minutes(
                special_duty_type,
                crew_type=aeronauta_profile.crew_type,
            )
            if special_limit_min is not None and special_limit_min > 0:
                special_limit_h = special_limit_min / 60.0
                if self.cct_limit_hours is not None:
                    return min(special_limit_h, self.cct_limit_hours)
                return special_limit_h

        if loader is not None and hora_apresentacao is not None:
            fdp_max_min = loader.get_fdp_max_minutes(
                hora_apresentacao,
                pousos=pousos,
                crew_type=aeronauta_profile.crew_type,
                aclim=aeronauta_profile.aclimatado,
                frms=aeronauta_profile.frms,
                funcao=aeronauta_profile.funcao,
                is_wocl=is_wocl,
            )
            if fdp_max_min is not None:
                fdp_max_h = fdp_max_min / 60.0
                if self.cct_limit_hours is not None:
                    return min(fdp_max_h, self.cct_limit_hours)
                return fdp_max_h

        # --- Fallback hardcoded ---
        rbac_limit_hours = 9  # Padrão para JATO
        if self.type_aeronave in ("TURBO-HELICE", "CONVENCIONAL"):
            rbac_limit_hours = 10
        lei_limit_hours = 11
        current_limit = min(rbac_limit_hours, lei_limit_hours)
        if self.cct_limit_hours is not None:
            current_limit = min(current_limit, self.cct_limit_hours)
        return current_limit

    def check(self, schedule: "Schedule", aeronauta_profile: "AeronautaProfile") -> List["Violation"]:
        violations = []
        for data, jornada in schedule.jornadas.items():
            # Obtém hora de apresentação local e número de pousos
            hora_apres_local: Optional[datetime.time] = None
            if jornada.hora_apresentacao:
                hora_apres_local = aeronauta_profile.get_local_datetime(jornada.hora_apresentacao).time()
            pousos = jornada.numero_pousos()

            special_types = {
                _infer_entry_special_duty_type(entry, aeronauta_profile)
                for entry in jornada.atividades
            }
            special_types.discard(None)
            special_duty_type = next(iter(special_types)) if len(special_types) == 1 else None

            limit_hours = self.get_applicable_limit(
                aeronauta_profile,
                hora_apres_local,
                pousos,
                is_wocl=jornada.includes_night_duty(),
                special_duty_type=special_duty_type,
            )
            limit_minutes = int(limit_hours * 60)

            if jornada.duracao_jornada_minutos() > limit_minutes:
                relevant_data = [entry.get_report_data() for entry in jornada.atividades]
                # Formata com indicação de origem do limite
                if special_duty_type:
                    origem = f"JSON_{special_duty_type.upper()}"
                else:
                    origem = "JSON" if (get_limits_loader() is not None and hora_apres_local is not None) else "hardcoded"
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description=f"Jornada de {jornada.data.strftime('%d/%m/%Y')} excedeu o limite.",
                        reference=f"{self.base_reference} / CCT {aeronauta_profile.cct_aplicavel}",
                        severity="ALTA",
                        details=(
                            f"Duração: {jornada.duracao_jornada_minutos() // 60}h{jornada.duracao_jornada_minutos() % 60}m. "
                            f"Limite: {limit_hours:.1f}h "
                            f"[apres={hora_apres_local.strftime('%H:%M') if hora_apres_local else 'N/A'}, "
                            f"pousos={pousos}, tipo_trip={aeronauta_profile.crew_type}, "
                            f"frms={aeronauta_profile.frms}, origem={origem}]."
                        ),
                        relevant_entries_data=relevant_data
                    )
                )
        return violations

class MinimumRestPeriodRule(Rule):
    """Regra: Período mínimo de repouso (RBAC 117, L13475, CCT), incluindo regras antes de folgas."""
    def __init__(self, type_aeronave: str, funcao: str, cct_min_rest_hours: Optional[int] = None):
        super().__init__(
            name="Repouso Mínimo",
            description=f"Repouso mínimo após jornada não deve ser inferior ao estabelecido.",
            base_reference="RBAC 117 A117.23(a) / L13475 Art. 48",
            priority=40
        )
        self.type_aeronave = type_aeronave
        self.funcao = funcao
        self.cct_min_rest_hours = cct_min_rest_hours

    def get_applicable_limit(self, jornada_duration_minutes: int, aeronauta_profile: "AeronautaProfile") -> int:
        """
        Retorna o repouso mínimo exigido (em minutos) após um período de jornada/FDP.
        Prioridade: JSON (legal_overrides / rulepack) → hardcoded RBAC/Lei → CCT override.
        """
        loader = get_limits_loader()
        if loader is not None:
            rest_min = loader.get_rest_min_minutes(
                jornada_duration_minutes,
                crew_type=aeronauta_profile.crew_type,
                aclim=aeronauta_profile.aclimatado,
                frms=aeronauta_profile.frms
            )
            if rest_min is not None:
                if self.cct_min_rest_hours is not None:
                    return max(rest_min, self.cct_min_rest_hours * 60)
                return rest_min

        # --- Fallback hardcoded (L13475 Art. 48 + RBAC 117 A117.23a) ---
        lei_limits = {12 * 60: 12 * 60, 15 * 60: 16 * 60, float('inf'): 24 * 60}
        current_lei = 0
        for dur_max, repouso in lei_limits.items():
            if jornada_duration_minutes <= dur_max:
                current_lei = repouso
                break

        rbac_limits = {9 * 60: 10 * 60, 14 * 60: 12 * 60, float('inf'): 16 * 60}
        current_rbac = 0
        for dur_max, repouso in rbac_limits.items():
            if jornada_duration_minutes <= dur_max:
                current_rbac = repouso
                break

        base = max(current_lei, current_rbac)
        if self.cct_min_rest_hours is not None:
            return max(base, self.cct_min_rest_hours * 60)
        return base

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations = []

        sorted_entries = schedule.all_entries
        if len(sorted_entries) < 2:
            return violations

        def _id_leg_norm(entry: ScheduleEntry) -> str:
            return str(getattr(entry, "id_leg", "") or "").upper().strip()

        def _is_start_leg(entry: ScheduleEntry) -> bool:
            leg = _id_leg_norm(entry)
            return leg.endswith("-I") or leg.endswith("-IF")

        def _is_end_leg(entry: ScheduleEntry) -> bool:
            leg = _id_leg_norm(entry)
            return leg.endswith("-F") or leg.endswith("-IF")

        def _to_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
            if dt is None:
                return None
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                return aeronauta_profile.get_utc_datetime(dt)
            return dt.astimezone(datetime.timezone.utc)

        def _entry_start_utc(entry: ScheduleEntry) -> datetime.datetime:
            # Para início de jornada, prioriza Checkin (quando disponível).
            return _to_utc(entry.checkin) or entry.get_start_datetime(aeronauta_profile)

        def _entry_end_utc(entry: ScheduleEntry) -> datetime.datetime:
            # Para fim de jornada, prioriza Checkout (quando disponível).
            return _to_utc(entry.checkout) or entry.get_end_datetime(aeronauta_profile)

        has_leg_markers = any(_id_leg_norm(e) for e in sorted_entries)
        last_start_idx: Optional[int] = None

        for i in range(len(sorted_entries) - 1):
            current_entry = sorted_entries[i]
            next_entry = sorted_entries[i + 1]

            if _is_start_leg(current_entry):
                last_start_idx = i

            if current_entry.is_folga(aeronauta_profile.folgas_set) or next_entry.is_folga(aeronauta_profile.folgas_set):
                continue

            # Regra operacional solicitada:
            # repouso só ocorre quando uma linha termina jornada (-F/-IF)
            # e a próxima inicia jornada (-I).
            if has_leg_markers:
                if not (_is_end_leg(current_entry) and _is_start_leg(next_entry)):
                    continue

            repouso_start = _entry_end_utc(current_entry)
            repouso_end = _entry_start_utc(next_entry)
            if repouso_end <= repouso_start:
                continue

            actual_rest_minutes = int((repouso_end - repouso_start).total_seconds() / 60)

            # Duração da jornada anterior para cálculo do repouso mínimo exigido.
            if last_start_idx is not None and last_start_idx <= i:
                jornada_start = _entry_start_utc(sorted_entries[last_start_idx])
                jornada_end = _entry_end_utc(current_entry)
                jornada_duration_minutes = max(0, int((jornada_end - jornada_start).total_seconds() / 60))
                relevant_slice = sorted_entries[last_start_idx:i + 1]
            else:
                jornada_duration_minutes = current_entry.duration_minutes(aeronauta_profile)
                relevant_slice = [current_entry]

            required_rest_minutes = self.get_applicable_limit(jornada_duration_minutes, aeronauta_profile)

            if actual_rest_minutes < required_rest_minutes:
                relevant_data = [activity.get_report_data() for activity in relevant_slice]
                relevant_data.append(next_entry.get_report_data())
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description=(
                            f"Repouso insuficiente entre as jornadas de "
                            f"{current_entry.data.strftime('%d/%m/%Y')} e {next_entry.data.strftime('%d/%m/%Y')}."
                        ),
                        reference=f"{self.base_reference} / CCT {aeronauta_profile.cct_aplicavel}",
                        severity="ALTA",
                        details=(
                            f"Repouso real: {actual_rest_minutes // 60}h{actual_rest_minutes % 60}m. "
                            f"Repouso mínimo requerido: {required_rest_minutes // 60}h{required_rest_minutes % 60}m. "
                            f"(Jornada anterior: {jornada_duration_minutes // 60}h{jornada_duration_minutes % 60}m)"
                        ),
                        relevant_entries_data=relevant_data,
                    )
                )

        return violations

class ConsecutiveNightDutiesRule(Rule):
    """Regra: Limite de madrugadas consecutivas (L13475, CCT)."""
    def __init__(self, max_consecutive: int, max_total_168h: int, cct_max_consecutive: Optional[int] = None, cct_max_total_168h: Optional[int] = None):
        super().__init__(
            name="Limite de Madrugadas Consecutivas",
            description=f"Não exceder o limite de madrugadas consecutivas ou no período de 168h.",
            base_reference="L13475 Art. 42 / CCT",
            priority=60
        )
        self.max_consecutive = max_consecutive # Limite da Lei 13475
        self.max_total_168h = max_total_168h   # Limite da Lei 13475
        self.cct_max_consecutive = cct_max_consecutive
        self.cct_max_total_168h = cct_max_total_168h

    def get_applicable_limits(self, aeronauta_profile: AeronautaProfile):
        # L13475 Art. 42: 2 madrugadas consecutivas, 4 madrugadas em 168h
        current_consecutive = self.max_consecutive
        current_total_168h = self.max_total_168h

        # CCT pode ser mais restritiva (menor número)
        if self.cct_max_consecutive is not None:
            current_consecutive = min(current_consecutive, self.cct_max_consecutive)
        if self.cct_max_total_168h is not None:
            current_total_168h = min(current_total_168h, self.cct_max_total_168h)
        return current_consecutive, current_total_168h

    def _get_night_date(self, jornada: Jornada) -> Optional[datetime.date]:
        if not jornada.includes_night_duty():
            return None
        
        if not jornada.hora_apresentacao or not jornada.hora_encerramento:
            return None
            
        start_local = jornada.aeronauta_profile.get_local_datetime(jornada.hora_apresentacao)
        end_local = jornada.aeronauta_profile.get_local_datetime(jornada.hora_encerramento)
        
        madrugada_start_day = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
        madrugada_end_day = start_local.replace(hour=6, minute=0, second=0, microsecond=0)
        
        if max(start_local, madrugada_start_day) < min(end_local, madrugada_end_day):
            return start_local.date()
            
        next_day = start_local + datetime.timedelta(days=1)
        madrugada_start_next = next_day.replace(hour=0, minute=0, second=0, microsecond=0)
        madrugada_end_next = next_day.replace(hour=6, minute=0, second=0, microsecond=0)
        
        if max(start_local, madrugada_start_next) < min(end_local, madrugada_end_next):
            return next_day.date()
            
        return None

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations = []
        max_consecutive, max_total_168h = self.get_applicable_limits(aeronauta_profile)
        
        # Identifica o mês de predominância da escala para reportar violações apenas nele
        entries_by_month = {}
        for entry in schedule.all_entries:
            key = (entry.data.year, entry.data.month)
            entries_by_month[key] = entries_by_month.get(key, 0) + 1
        principal_month = max(entries_by_month.items(), key=lambda x: x[1])[0] if entries_by_month else None

        # Filtra apenas as jornadas que NÃO são folga para o cálculo de madrugadas.
        # Jornadas são automaticamente construídas apenas com atividades de trabalho.
        # A detecção de madrugada dentro da jornada já usa os horários previstos.
        
        sorted_jornadas_trabalho = sorted(schedule.jornadas.values(), key=lambda j: j.data)
        
        # Faz a fusão de jornadas que têm um intervalo de repouso < 12 horas
        merged_jornadas_trabalho = []
        for j in sorted_jornadas_trabalho:
            if not merged_jornadas_trabalho:
                merged_jornadas_trabalho.append(j)
            else:
                last_j = merged_jornadas_trabalho[-1]
                gap_hours = 999.0
                if j.hora_apresentacao and last_j.hora_encerramento:
                    gap_hours = (j.hora_apresentacao - last_j.hora_encerramento).total_seconds() / 3600.0
                
                # Se o gap for menor que 12h, é o mesmo bloco de trabalho (não houve pernoite)
                if gap_hours < 12.0:
                    # Fundir: criamos um "novo" objeto Jornada
                    combined = Jornada(aeronauta_profile, last_j.data) # Mantém a data de início
                    # Forçamos a adição das atividades de ambas as jornadas
                    for a in last_j.atividades + j.atividades:
                        combined.add_atividade(a)
                    merged_jornadas_trabalho[-1] = combined
                else:
                    merged_jornadas_trabalho.append(j)
        
        # Verifica madrugadas consecutivas usando a data da noite efetiva (night_date)
        consecutive_night_duties_count = 0
        last_night_date = None

        for j_idx, jornada in enumerate(merged_jornadas_trabalho):
            night_date = self._get_night_date(jornada)
            
            if night_date is not None:
                if last_night_date is None or (night_date - last_night_date).days == 1:
                    # É a primeira madrugada ou imediatamente consecutiva à anterior
                    consecutive_night_duties_count += 1
                elif (night_date - last_night_date).days == 0:
                    # Mesma noite, não incrementa (apenas se não fundiu)
                    pass
                else:
                    # Quebrou a sequência
                    consecutive_night_duties_count = 1
                    
                last_night_date = night_date

                if consecutive_night_duties_count > max_consecutive:
                    is_allowed_by_cct = False
                    if consecutive_night_duties_count == 3:
                        # CCT Parágrafo 1: allowed if tripulante extra in return flight
                        if jornada.atividades:
                            last_activity = jornada.atividades[-1]
                            tipo_ativ = str(last_activity.tipo_atividade).upper()
                            if "EXTRA" in tipo_ativ or "DH" in tipo_ativ:
                                is_allowed_by_cct = True
                                
                    if not is_allowed_by_cct:
                        # (Apenas reporta se caiu no mês predominante)
                        if principal_month and (jornada.data.year, jornada.data.month) != principal_month:
                            pass
                        else:
                            violations.append(
                                Violation(
                                    rule_name=self.name,
                                    severity="ALTA",
                                    details=f"Jornada de {jornada.data.strftime('%d/%m/%Y')} é a {consecutive_night_duties_count}ª madrugada consecutiva de trabalho. Limite: {max_consecutive}.",
                                    relevant_entries_data=relevant_data
                                )
                            )
            else:
                consecutive_night_duties_count = 0 # Reseta a contagem se não for madrugada
            
            last_jornada_date = jornada.data # Atualiza a última data para o próximo check de consecução

            # Verifica limite de madrugadas em 168 horas (7 dias)
            # CCT Parágrafo 2: Reseta contagem se houver um gap de 48h
            end_of_window = jornada.data
            start_of_window = end_of_window - datetime.timedelta(days=7)
            
            madrugadas_in_window = 0
            for i in range(j_idx, -1, -1):
                prev_jornada = merged_jornadas_trabalho[i]
                if prev_jornada.data < start_of_window:
                    break
                
                if prev_jornada.includes_night_duty():
                    madrugadas_in_window += 1
                    
                # Checa se antes dessa jornada houve um gap >= 48h
                if i > 0:
                    pj_before = merged_jornadas_trabalho[i-1]
                    if prev_jornada.hora_apresentacao and pj_before.hora_encerramento:
                        gap_hours = (prev_jornada.hora_apresentacao - pj_before.hora_encerramento).total_seconds() / 3600.0
                        if gap_hours >= 48.0:
                            break # O gap de 48h ocorreu, as jornadas anteriores não contam para o limite de 168h
            
            if madrugadas_in_window > max_total_168h:
                is_predominant_month = principal_month is None or (jornada.data.year, jornada.data.month) == principal_month
                if is_predominant_month:
                    relevant_data = [entry.get_report_data() for entry in jornada.atividades]
                    violations.append(
                        Violation(
                            rule_name=self.name,
                            description=f"Excedido o limite de madrugadas no período de 168 horas.",
                            reference=f"{self.base_reference} / CCT {aeronauta_profile.cct_aplicavel}",
                            severity="ALTA",
                            details=f"Na janela que se encerra em {end_of_window.strftime('%d/%m/%Y')}, foram {madrugadas_in_window} madrugadas de trabalho num período de 168h. Limite: {max_total_168h}.",
                            relevant_entries_data=relevant_data
                        )
                    )

        return violations


class MonthlyAnnualFlightHoursRule(Rule):
    """Regra: Limites de horas de voo mensais e anuais (Tabela A.3)."""
    def __init__(self):
        super().__init__(
            name="Limite Mensal/Anual de Horas de Voo",
            description="Horas de voo não devem exceder os limites mensais e anuais por tipo de aeronave.",
            base_reference="RBAC 117 Tabela A.3",
            priority=70
        )

    @staticmethod
    def _is_voo_atividade(entry: ScheduleEntry, profile: AeronautaProfile) -> bool:
        return _is_voo_activity(entry, profile.folgas_set, profile.latam_activities_set)

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations: List[Violation] = []
        loader = get_limits_loader()
        if loader is None:
            return violations

        limits = loader.get_monthly_annual_voo_limits(aeronauta_profile.tipo_aeronave_principal)
        if not limits:
            return violations

        monthly_limit_min = int(limits.get("limite_horas_voo_mensais", 0)) * 60
        annual_limit_min = int(limits.get("limite_horas_voo_anuais", 0)) * 60
        if monthly_limit_min <= 0 and annual_limit_min <= 0:
            return violations

        monthly_totals: Dict[Tuple[int, int], int] = {}
        yearly_totals: Dict[int, int] = {}
        monthly_entries: Dict[Tuple[int, int], List[ScheduleEntry]] = {}
        yearly_entries: Dict[int, List[ScheduleEntry]] = {}

        for entry in schedule.all_entries:
            if entry.is_folga(aeronauta_profile.folgas_set):
                continue
            if not self._is_voo_atividade(entry, aeronauta_profile):
                continue
            dur = entry.duration_minutes(aeronauta_profile)
            ym = (entry.data.year, entry.data.month)
            yy = entry.data.year
            monthly_totals[ym] = monthly_totals.get(ym, 0) + dur
            yearly_totals[yy] = yearly_totals.get(yy, 0) + dur
            monthly_entries.setdefault(ym, []).append(entry)
            yearly_entries.setdefault(yy, []).append(entry)

        for (year, month), total_min in sorted(monthly_totals.items()):
            if monthly_limit_min > 0 and total_min > monthly_limit_min:
                relevant_data = [e.get_report_data() for e in monthly_entries.get((year, month), [])]
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description=f"Excedido limite mensal de horas de voo ({month:02d}/{year}).",
                        reference=self.base_reference,
                        severity="ALTA",
                        details=(
                            f"Realizado: {total_min // 60}h{total_min % 60:02d}m. "
                            f"Limite mensal A.3: {monthly_limit_min // 60}h00m. "
                            f"Tipo aeronave: {aeronauta_profile.tipo_aeronave_principal}."
                        ),
                        relevant_entries_data=relevant_data
                    )
                )

        for year, total_min in sorted(yearly_totals.items()):
            if annual_limit_min > 0 and total_min > annual_limit_min:
                relevant_data = [e.get_report_data() for e in yearly_entries.get(year, [])]
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description=f"Excedido limite anual de horas de voo ({year}).",
                        reference=self.base_reference,
                        severity="ALTA",
                        details=(
                            f"Realizado: {total_min // 60}h{total_min % 60:02d}m. "
                            f"Limite anual A.3: {annual_limit_min // 60}h00m. "
                            f"Tipo aeronave: {aeronauta_profile.tipo_aeronave_principal}."
                        ),
                        relevant_entries_data=relevant_data
                    )
                )

        return violations


class MonthlyFolgasRule(Rule):
    """Regra: número mensal mínimo de folgas (A117.25(e)/(f))."""
    def __init__(self):
        super().__init__(
            name="Número Mensal de Folgas",
            description="Verifica o mínimo mensal de folgas regulamentares.",
            base_reference="RBAC 117 A117.25(e)/(f)",
            priority=72,
        )

    @staticmethod
    def _folga_dates(schedule: Schedule, profile: AeronautaProfile) -> List[datetime.date]:
        folga_dates: List[datetime.date] = []
        # Filtra apenas entradas de folga
        folga_entries = [e for e in schedule.all_entries if e.is_folga(profile.folgas_set)]
        if not folga_entries:
            return folga_dates
        
        # Ordena pelas datas/horas de início local
        folga_entries.sort(key=lambda e: e.get_local_interval(profile)[0])
        
        # Agrupa folgas contíguas
        merged_blocks = []
        for e in folga_entries:
            start, end = e.get_local_interval(profile)
            if not merged_blocks:
                merged_blocks.append((start, end))
            else:
                last_start, last_end = merged_blocks[-1]
                if start <= last_end:
                    merged_blocks[-1] = (last_start, max(last_end, end))
                else:
                    merged_blocks.append((start, end))
                    
        # Converte a duração de cada bloco ininterrupto em múltiplos de 24h
        for start, end in merged_blocks:
            total_seconds = (end - start).total_seconds()
            num_folgas = int(total_seconds // 86400) # 86400s = 24h
            for i in range(num_folgas):
                # Para cada folga, extrai a data civil em que este período de 24h se iniciou
                chunk_start = start + datetime.timedelta(days=i)
                folga_dates.append(chunk_start.date())
                
        return folga_dates

    @staticmethod
    def _entries_dates_by_month(schedule: Schedule) -> Dict[Tuple[int, int], Set[datetime.date]]:
        out: Dict[Tuple[int, int], Set[datetime.date]] = {}
        for e in schedule.all_entries:
            ym = (e.data.year, e.data.month)
            out.setdefault(ym, set()).add(e.data)
        return out

    @staticmethod
    def _infer_operator_group(profile: AeronautaProfile) -> str:
        # Heurística mínima para selecionar faixa de limite do JSON textual.
        rbac = _normalize_text(profile.empresa_rbac_tipo)
        if "121" in rbac:
            return "rbac_117_1_b_1"
        return "rbac_117_1_b_2_a_b_6"

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations: List[Violation] = []
        loader = get_limits_loader()
        if loader is None:
            return violations

        folgas_cfg = loader.get_folgas_limits()
        min_cfg = folgas_cfg.get("min_mensal", {}) if isinstance(folgas_cfg, dict) else {}
        if not isinstance(min_cfg, dict):
            return violations

        op_group = self._infer_operator_group(aeronauta_profile)
        group_cfg = min_cfg.get(op_group, {}) if isinstance(min_cfg.get(op_group, {}), dict) else {}
        min_month = group_cfg.get("quantidade")
        if min_month is None:
            return violations

        folga_dates = self._folga_dates(schedule, aeronauta_profile)
        entries_by_month = self._entries_dates_by_month(schedule)

        # Define mês principal auditado como o que possui mais dias com programação.
        # Meses de borda (anterior/posterior) com apenas 1 dia não devem gerar
        # avaliação de folgas mensais.
        principal_month: Optional[Tuple[int, int]] = None
        if entries_by_month:
            principal_month = max(
                entries_by_month.items(),
                key=lambda kv: (len(kv[1]), kv[0])
            )[0]

        for (year, month), active_dates in sorted(entries_by_month.items()):
            days_in_month = calendar.monthrange(year, month)[1]
            active_days = len(active_dates)

            if (
                principal_month is not None
                and (year, month) != principal_month
                and active_days <= 1
            ):
                continue

            folgas_month = sum(1 for d in folga_dates if d.year == year and d.month == month)

            # proporcionalidade para mês parcial (A117.25(e)(2))
            required = int(min_month)
            if active_days < days_in_month and active_days > 0:
                required = int((active_days * int(min_month) + days_in_month - 1) // days_in_month)

            if folgas_month < required:
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description=f"Folgas mensais insuficientes em {month:02d}/{year}.",
                        reference=self.base_reference,
                        severity="ALTA",
                        details=(
                            f"Folgas no mês: {folgas_month}. Mínimo exigido: {required}. "
                            f"Grupo regulatório: {op_group}."
                        ),
                        relevant_entries_data=[e.get_report_data() for e in schedule.all_entries if e.data.year == year and e.data.month == month]
                    )
                )

        return violations


class WeekendConsecutiveFolgasRule(Rule):
    """Regra: pelo menos 2 folgas do mês devem formar sábado+domingo consecutivos. sábado e domingo são referências a dias civis, portanto iniciam as 00:00 e terminam também as 00:00, assim o repouso que antecede essas folgas, deve iniciar as 12:00 Horas."""
    def __init__(self):
        super().__init__(
            name="Folgas de Fim de Semana",
            description="Verifica quantidade mínima de folgas contendo sábado e domingo consecutivos. Sábado e domingo são referências a dias civis, portanto iniciam as 00:00 e terminam também as 00:00, assim o repouso que antecede essas folgas, deve iniciar as 12:00 Horas.",
            base_reference="RBAC 117 A117.25(f)",
            priority=73,
        )

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations: List[Violation] = []
        loader = get_limits_loader()
        if loader is None:
            return violations

        folgas_cfg = loader.get_folgas_limits()
        wk_cfg = folgas_cfg.get("finais_de_semana", {}) if isinstance(folgas_cfg, dict) else {}
        if not isinstance(wk_cfg, dict):
            return violations
        min_weekends = wk_cfg.get("min_por_mes")
        if min_weekends is None:
            return violations

        folga_dates = sorted(MonthlyFolgasRule._folga_dates(schedule, aeronauta_profile))
        folga_set = set(folga_dates)
        months = sorted({(d.year, d.month) for d in folga_dates})

        def _is_date_fully_covered(d: datetime.date) -> bool:
            target_start = datetime.datetime.combine(d, datetime.time(0, 0))
            target_end = target_start + datetime.timedelta(days=1)
            for e in schedule.all_entries:
                if not e.is_folga(aeronauta_profile.folgas_set):
                    continue
                start_local, end_local = e.get_local_interval(aeronauta_profile)
                if start_local.replace(tzinfo=None) <= target_start and end_local.replace(tzinfo=None) >= target_end:
                    return True
            return False

        for year, month in months:
            weekend_dates: Set[datetime.date] = set()
            count_pairs = 0
            for d in folga_dates:
                if d.year != year or d.month != month:
                    continue
                if d.weekday() == 5:  # sábado
                    sunday = d + datetime.timedelta(days=1)
                    if sunday in folga_set and sunday.month == month and sunday.weekday() == 6:
                        if _is_date_fully_covered(d) and _is_date_fully_covered(sunday):
                            count_pairs += 1
                            weekend_dates.add(d)
                            weekend_dates.add(sunday)

            found_weekend_folgas = len(weekend_dates)
            required_weekend_folgas = int(min_weekends)

            if found_weekend_folgas < required_weekend_folgas:
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description=f"Folgas de final de semana insuficientes em {month:02d}/{year}.",
                        reference=self.base_reference,
                        severity="MEDIA",
                        details=(
                            f"Encontradas: {found_weekend_folgas} folga(s) de final de semana "
                            f"({count_pairs} par(es) sábado+domingo). Mínimo exigido: {required_weekend_folgas} folga(s) de final de semana.\n"
                            f"Sábado e domingo são referências a dias civis, portanto iniciam as 00:00 e terminam também as 00:00, assim o repouso que antecede essas folgas, deve iniciar as 12:00 Horas."
                        ),
                        relevant_entries_data=[e.get_report_data() for e in schedule.all_entries if e.data.year == year and e.data.month == month]
                    )
                )

        return violations


class GroupedFolgasRule(Rule):
    """Regra: presença de folgas agrupadas quando aplicável (A117.25(c))."""
    def __init__(self):
        super().__init__(
            name="Folgas Agrupadas",
            description="Verifica ocorrência de folgas agrupadas em sequência.",
            base_reference="RBAC 117 A117.25(c)",
            priority=74,
        )

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations: List[Violation] = []
        loader = get_limits_loader()
        if loader is None:
            return violations

        folgas_cfg = loader.get_folgas_limits()
        grp_cfg = folgas_cfg.get("agrupadas", {}) if isinstance(folgas_cfg, dict) else {}
        if not isinstance(grp_cfg, dict):
            return violations

        long_cfg = grp_cfg.get("longo_curso_internacional", {})
        if not isinstance(long_cfg, dict) or not long_cfg.get("permitido"):
            return violations

        # só aplica estritamente se operação indicar longo curso
        if "LONGO" not in _normalize_text(aeronauta_profile.empresa_tipo_operacao):
            return violations

        folga_dates = sorted(MonthlyFolgasRule._folga_dates(schedule, aeronauta_profile))
        if not folga_dates:
            return violations

        max_run = 1
        run = 1
        for i in range(1, len(folga_dates)):
            if (folga_dates[i] - folga_dates[i - 1]).days == 1:
                run += 1
                max_run = max(max_run, run)
            else:
                run = 1

        if max_run < 2:
            violations.append(
                Violation(
                    rule_name=self.name,
                    description="Não foi identificada folga agrupada (consecutiva) em operação de longo curso.",
                    reference=self.base_reference,
                    severity="MEDIA",
                    details="Mínimo esperado: ao menos um agrupamento com 2 folgas consecutivas.",
                    relevant_entries_data=[e.get_report_data() for e in schedule.all_entries]
                )
            )
        return violations


class SixthPeriodRule(Rule):
    """Regra: folga deve iniciar no máximo após o 6º período consecutivo de 24h."""
    def __init__(self):
        super().__init__(
            name="Sexto Período Consecutivo",
            description="Verifica se a folga inicia no máximo após o sexto período consecutivo de 24h.",
            base_reference="RBAC 117 A117.25(a)",
            priority=75,
        )

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations: List[Violation] = []
        loader = get_limits_loader()
        if loader is None:
            return violations

        max_periods = loader.get_sexto_periodo_limit()
        if not max_periods:
            return violations

        work_dates = sorted(schedule.jornadas.keys())
        if not work_dates:
            return violations

        # Sequências de dias consecutivos com tarefas
        runs: List[List[datetime.date]] = []
        cur_run = [work_dates[0]]
        for d in work_dates[1:]:
            if (d - cur_run[-1]).days == 1:
                cur_run.append(d)
            else:
                runs.append(cur_run)
                cur_run = [d]
        runs.append(cur_run)

        folga_entries = [e for e in schedule.all_entries if e.is_folga(aeronauta_profile.folgas_set)]
        folga_entries.sort(key=lambda e: e.get_start_datetime(aeronauta_profile))

        for run in runs:
            if len(run) < int(max_periods):
                continue

            first_day = run[0]
            first_jornada = schedule.jornadas.get(first_day)
            if first_jornada is None:
                continue

            start_dt_utc = first_jornada.hora_apresentacao
            if start_dt_utc is None and first_jornada.atividades:
                start_dt_utc = min(a.get_start_datetime(aeronauta_profile) for a in first_jornada.atividades)
            if start_dt_utc is None:
                continue

            deadline_utc = start_dt_utc + datetime.timedelta(hours=132)
            first_folga_after_start = None
            for fe in folga_entries:
                folga_start = fe.get_start_datetime(aeronauta_profile)
                if folga_start >= start_dt_utc:
                    first_folga_after_start = folga_start
                    break

            if first_folga_after_start is None or first_folga_after_start > deadline_utc:
                violations.append(
                    Violation(
                        rule_name=self.name,
                        description="Excedido prazo do sexto período (132h) sem início de folga.",
                        reference=self.base_reference,
                        severity="ALTA",
                        details=(
                            f"Sequência de tarefas: {run[0].strftime('%d/%m/%Y')} a {run[-1].strftime('%d/%m/%Y')} "
                            f"({len(run)} dias). Vencimento em 132h a partir da apresentação do 1º período. "
                            f"Apresentação inicial: {aeronauta_profile.get_local_datetime(start_dt_utc).strftime('%d/%m/%Y %H:%M')}. "
                            f"Vencimento: {aeronauta_profile.get_local_datetime(deadline_utc).strftime('%d/%m/%Y %H:%M')}. "
                            f"Início de folga: "
                            f"{aeronauta_profile.get_local_datetime(first_folga_after_start).strftime('%d/%m/%Y %H:%M') if first_folga_after_start else 'não identificado'}"
                            f"."
                        ),
                        relevant_entries_data=[e.get_report_data() for e in schedule.all_entries if run[0] <= e.data <= run[-1]]
                    )
                )

        return violations


class CivilDayFolgaRule(Rule):
    """Regra: folgas devem possuir no mínimo 24h ininterruptas."""
    def __init__(self):
        super().__init__(
            name="Folga Mínima de 24h",
            description="Verifica se cada folga possui no mínimo 24 horas ininterruptas.",
            base_reference="Lei 13.475/17 Art. 47 (24h ininterruptas)",
            priority=71,
        )

    def check(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        violations: List[Violation] = []
        sorted_entries = sorted(schedule.all_entries, key=lambda e: e.get_start_datetime(aeronauta_profile))

        for idx, entry in enumerate(sorted_entries):
            if not entry.is_folga(aeronauta_profile.folgas_set):
                continue

            start_local, end_local = entry.get_local_interval(aeronauta_profile)
            duration_minutes = entry.duration_minutes(aeronauta_profile)
            
            if duration_minutes >= 1440:
                continue

            next_programming = None
            for next_entry in sorted_entries[idx + 1:]:
                if next_entry.is_folga(aeronauta_profile.folgas_set):
                    continue
                next_programming = next_entry
                break

            observacao_lastro = ""
            relevant_entries = [entry.get_report_data()]
            if next_programming is not None:
                next_start_local, _ = next_programming.get_local_interval(aeronauta_profile)
                slack_minutes = int((next_start_local - end_local).total_seconds() / 60)
                total_until_next_minutes = int((next_start_local - start_local).total_seconds() / 60)
                if slack_minutes > 0 and total_until_next_minutes >= 1440:
                    observacao_lastro = (
                        " OBS: O TOTAL DE HORAS DA FOLGA ESTÁ EM DESACORDO COM A LEGISLAÇÃO, "
                        "MAS COMO EXISTE LASTRO ATÉ O INÍCIO DA PRÓXIMA PROGRAMAÇÃO O TOTAL DE HORAS "
                        "É SUFICIENTE PARA AS 24H PREVISTAS."
                    )
                    relevant_entries.append(next_programming.get_report_data())

            violations.append(
                Violation(
                    rule_name=self.name,
                    description=f"Folga '{entry.tipo_atividade}' inferior a 24 horas.",
                    reference=self.base_reference,
                    severity="ALTA",
                    details=(
                        f"Início local: {start_local.strftime('%d/%m/%Y %H:%M')}. "
                        f"Fim local: {end_local.strftime('%d/%m/%Y %H:%M')}. "
                        f"Duração apurada: {duration_minutes // 60:02d}:{duration_minutes % 60:02d}. "
                        f"A folga legal deve possuir no mínimo 24:00 horas ininterruptas."
                        f"{observacao_lastro}"
                    ),
                    relevant_entries_data=relevant_entries,
                )
            )
        return violations

# --- 3. Auditor Principal ---

class Auditor:
    """Orquestra a aplicação das regras e a coleta de violações."""
    def __init__(self, rules: List[Rule]):
        self.rules = sorted(rules, key=lambda x: x.priority) # Prioriza regras

    def audit_schedule(self, schedule: Schedule, aeronauta_profile: AeronautaProfile) -> List[Violation]:
        all_violations: List[Violation] = []
        total_rules = len(self.rules)
        # print(f"Aplicando {total_rules} regra(s) de auditoria...")
        for idx, rule in enumerate(self.rules, start=1):
            progress = int((idx / total_rules) * 100) if total_rules > 0 else 100
            bar_len = 30
            filled = int((idx / total_rules) * bar_len) if total_rules > 0 else bar_len
            bar = '█' * filled + '-' * (bar_len - filled)
            # print(f"  [{bar}] {progress:3d}% - Regra {idx}/{total_rules}: {rule.name}")
            violations = rule.check(schedule, aeronauta_profile)
            all_violations.extend(violations)
        return all_violations

# --- 4. Geração de Relatórios ---

class ReportGenerator:
    """Gera o relatório de conformidade em formato de texto."""
    def __init__(self, input_filename: str, aeronauta_ctx: dict = None):
        self.input_filename = input_filename
        self.aeronauta_ctx = aeronauta_ctx or {}

    @staticmethod
    def _fmt_minutes(total_minutes: int) -> str:
        total_minutes = max(0, int(total_minutes))
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    @staticmethod
    def _dt_local_str(dt_utc: Optional[datetime.datetime], profile: AeronautaProfile) -> str:
        if not dt_utc:
            return "N/A"
        try:
            return profile.get_local_datetime(dt_utc).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return dt_utc.strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def _activity_label(entry: ScheduleEntry) -> str:
        if entry.voo_numero and str(entry.voo_numero).strip():
            return str(entry.voo_numero).strip()
        if entry.id_leg and str(entry.id_leg).strip():
            return str(entry.id_leg).strip()
        return str(entry.tipo_atividade).strip()

    @staticmethod
    def _activity_place(entry: ScheduleEntry) -> str:
        return (entry.local_inicio or entry.local_fim or entry.descricao or entry.tipo_atividade or "").strip() or "****"

    @staticmethod
    def _normalize_csv_duration(value: str) -> str:
        txt = str(value or "").strip()
        if not txt or txt.upper() in {"NAN", "NAT", "NONE"}:
            return "N/A"
        # Aceita formatos como "12:00", "12:00:00" e "0 days 12:00:00"
        m = re.search(r"(\d{1,3}):(\d{2})(?::\d{2})?$", txt)
        if m:
            return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        return txt

    def _repouso_csv_jornada(self, entries: List[ScheduleEntry]) -> Optional[str]:
        for e in reversed(entries):
            v = self._normalize_csv_duration(getattr(e, "tempo_repouso_raw", ""))
            if v != "N/A":
                return v
        return None

    @staticmethod
    def _parse_violation_anchor_date(v: Violation) -> Optional[datetime.date]:
        if not v.relevant_entries_data:
            return None
        entry = v.relevant_entries_data[0]
        for key in ("Start", "Checkin", "End", "Checkout"):
            raw = str(entry.get(key, "") or "").strip()
            if not raw or raw == "N/A":
                continue
            try:
                return datetime.datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").date()
            except Exception:
                continue
        return None

    def _compact_rule_violations_for_display(self, rule_name: str, rule_violations: List[Violation]) -> List[Violation]:
        if rule_name != "Folga em Dia Civil Completo" or len(rule_violations) <= 1:
            return rule_violations

        compacted: List[Violation] = []
        current_block: List[Violation] = []
        last_date: Optional[datetime.date] = None
        last_next_programming_date: Optional[datetime.date] = None

        for violation in rule_violations:
            anchor_date = self._parse_violation_anchor_date(violation)
            next_programming_date = None
            if len(violation.relevant_entries_data) > 1:
                next_programming = Violation(
                    rule_name=violation.rule_name,
                    description=violation.description,
                    reference=violation.reference,
                    severity=violation.severity,
                    details=violation.details,
                    relevant_entries_data=[violation.relevant_entries_data[1]],
                )
                next_programming_date = self._parse_violation_anchor_date(next_programming)
            if not current_block:
                current_block = [violation]
                last_date = anchor_date
                last_next_programming_date = next_programming_date
                continue

            same_next_programming = (
                next_programming_date is not None and
                last_next_programming_date is not None and
                next_programming_date == last_next_programming_date
            )
            consecutive_days = (
                anchor_date is not None and
                last_date is not None and
                (anchor_date - last_date).days == 1
            )

            if same_next_programming or consecutive_days:
                current_block.append(violation)
            else:
                compacted.append(current_block[-1])
                current_block = [violation]
            last_date = anchor_date
            last_next_programming_date = next_programming_date

        if current_block:
            compacted.append(current_block[-1])
        return compacted

    @staticmethod
    def _is_voo_atividade(entry: ScheduleEntry, profile: AeronautaProfile) -> bool:
        return _is_voo_activity(entry, profile.folgas_set, profile.latam_activities_set)

    @staticmethod
    def _month_window_from_schedule(schedule: Schedule) -> Optional[Tuple[int, int]]:
        if not schedule.all_entries:
            return None
        counts: Dict[Tuple[int, int], int] = {}
        for e in schedule.all_entries:
            ym = (e.data.year, e.data.month)
            counts[ym] = counts.get(ym, 0) + 1
        return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0][0]

    def _write_monthly_summary(self, f, profile: AeronautaProfile, schedule: Schedule):
        ym = self._month_window_from_schedule(schedule)
        if ym is None:
            f.write("# Sumário mensal do período auditado\n")
            f.write("- Sem dados para consolidação mensal.\n\n")
            return

        year, month = ym
        month_start = datetime.date(year, month, 1)
        month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])

        month_entries = [e for e in schedule.all_entries if e.data.year == year and e.data.month == month]
        month_jornadas = [j for d, j in schedule.jornadas.items() if d.year == year and d.month == month]

        loader = get_limits_loader()
        jsm = loader.get_jornada_semanal_limits() if loader is not None else {}
        try:
            weekly_limit_h = int(jsm.get("limite_semanal_horas", 44))
        except Exception:
            weekly_limit_h = 44
        try:
            monthly_limit_h = int(jsm.get("limite_mensal_horas", 176))
        except Exception:
            monthly_limit_h = 176
        try:
            weekly_ref_hora_extra_h = int(jsm.get("limite_semanal_referencia_hora_extra_horas", 60))
        except Exception:
            weekly_ref_hora_extra_h = 60
        ex44_cfg = jsm.get("excedente_44h", {}) if isinstance(jsm, dict) else {}
        ex44_fonte = ex44_cfg.get("fonte", {}) if isinstance(ex44_cfg, dict) else {}
        ex44_doc = ex44_fonte.get("documento") if isinstance(ex44_fonte, dict) else None
        ex44_clausula = ex44_fonte.get("clausula") if isinstance(ex44_fonte, dict) else None
        ex44_texto = ex44_cfg.get("texto") if isinstance(ex44_cfg, dict) else None

        folga_dates = sorted(d for d in MonthlyFolgasRule._folga_dates(schedule, profile) if d.year == year and d.month == month)
        folga_set = set(folga_dates)

        # Semanas civis calendário (domingo a sábado), com recorte dentro do mês
        week_rows: List[Dict[str, Any]] = []
        cursor, _ = _civil_week_bounds(month_start)
        while cursor <= month_end:
            week_start = cursor
            week_end = cursor + datetime.timedelta(days=DAYS_PER_CIVIL_WEEK - 1)
            clip_start = max(week_start, month_start)
            clip_end = min(week_end, month_end)

            days_in_clip = [clip_start + datetime.timedelta(days=i) for i in range((clip_end - clip_start).days + 1)]
            folgas_week = sum(1 for d in days_in_clip if d in folga_set)

            jornada_week_min = 0
            for j in month_jornadas:
                if clip_start <= j.data <= clip_end:
                    jornada_week_min += j.duracao_jornada_minutos()

            week_rows.append({
                "week_start": clip_start,
                "week_end": clip_end,
                "folgas": folgas_week,
                "jornada_min": jornada_week_min,
            })
            cursor += datetime.timedelta(days=7)

        # Finais de semana (sábado+domingo consecutivos)
        weekend_pairs: List[datetime.date] = []
        for d in folga_dates:
            if d.weekday() == 5:  # sábado
                sunday = d + datetime.timedelta(days=1)
                if sunday in folga_set and sunday.month == month and sunday.year == year and sunday.weekday() == 6:
                    weekend_pairs.append(d)

        # Folgas agrupadas (sequências consecutivas)
        grouped_runs: List[Tuple[datetime.date, datetime.date, int]] = []
        if folga_dates:
            run_start = folga_dates[0]
            run_prev = folga_dates[0]
            run_len = 1
            for d in folga_dates[1:]:
                if (d - run_prev).days == 1:
                    run_prev = d
                    run_len += 1
                else:
                    grouped_runs.append((run_start, run_prev, run_len))
                    run_start = d
                    run_prev = d
                    run_len = 1
            grouped_runs.append((run_start, run_prev, run_len))
        grouped_runs_2p = [r for r in grouped_runs if r[2] >= 2]

        # 2) Sexto período: após 6 dias consecutivos, vence em 132h da apresentação do 1º período
        work_dates = sorted({j.data for j in month_jornadas})
        work_runs: List[List[datetime.date]] = []
        if work_dates:
            cur_run = [work_dates[0]]
            for d in work_dates[1:]:
                if (d - cur_run[-1]).days == 1:
                    cur_run.append(d)
                else:
                    work_runs.append(cur_run)
                    cur_run = [d]
            work_runs.append(cur_run)

        folga_entries_month = [e for e in month_entries if e.is_folga(profile.folgas_set)]
        folga_entries_month.sort(key=lambda e: e.get_start_datetime(profile))

        sixth_checks: List[Dict[str, Any]] = []
        for run in work_runs:
            if len(run) < 6:
                continue
            first_day = run[0]
            first_jornada = schedule.jornadas.get(first_day)
            if first_jornada is None:
                continue

            start_dt_utc = first_jornada.hora_apresentacao
            if start_dt_utc is None and first_jornada.atividades:
                start_dt_utc = min(a.get_start_datetime(profile) for a in first_jornada.atividades)
            if start_dt_utc is None:
                continue

            deadline_utc = start_dt_utc + datetime.timedelta(hours=132)
            first_folga_after_start = None
            for fe in folga_entries_month:
                folga_start_utc = fe.get_start_datetime(profile)
                if folga_start_utc >= start_dt_utc:
                    first_folga_after_start = folga_start_utc
                    break

            compliant = first_folga_after_start is not None and first_folga_after_start <= deadline_utc
            sixth_checks.append({
                "run_start": run[0],
                "run_end": run[-1],
                "run_days": len(run),
                "start_dt_utc": start_dt_utc,
                "deadline_utc": deadline_utc,
                "folga_start_utc": first_folga_after_start,
                "compliant": compliant,
            })

        # 3) Madrugadas consecutivas
        raw_night_dates = []
        for j in month_jornadas:
            nd = j.get_night_date()
            if nd:
                raw_night_dates.append(nd)
                
        night_dates = sorted(list(set(raw_night_dates)))
        night_runs: List[Tuple[datetime.date, datetime.date, int]] = []
        if night_dates:
            rs = night_dates[0]
            rp = night_dates[0]
            rl = 1
            for d in night_dates[1:]:
                if (d - rp).days == 1:
                    rp = d
                    rl += 1
                else:
                    if rl >= 2:
                        night_runs.append((rs, rp, rl))
                    rs = d
                    rp = d
                    rl = 1
            if rl >= 2:
                night_runs.append((rs, rp, rl))

        # 4) Totais de jornada semanal e mensal
        monthly_jornada_min = sum(j.duracao_jornada_minutos() for j in month_jornadas)
        weekly_over_44 = [w for w in week_rows if w["jornada_min"] > weekly_limit_h * 60]
        monthly_over_176 = monthly_jornada_min > monthly_limit_h * 60

        # 5) Total de horas voadas
        total_voo_min = 0
        for e in month_entries:
            if e.is_folga(profile.folgas_set):
                continue
            if self._is_voo_atividade(e, profile):
                total_voo_min += e.duration_minutes(profile)

        f.write("# Sumário mensal do período auditado\n")
        f.write(f"- Mês auditado: {month:02d}/{year}\n\n")

        f.write("1. FOLGAS\n")
        f.write(f"1.1 Totais: {len(folga_dates)} dia(s) de folga no mês.\n")
        f.write("1.2 Semanais:\n")
        for w in week_rows:
            f.write(
                f"  • {w['week_start'].strftime('%d/%m')} a {w['week_end'].strftime('%d/%m')}: "
                f"{w['folgas']} folga(s).\n"
            )
        f.write("1.3 Finais de semana:\n")
        if weekend_pairs:
            pares_txt = ", ".join(d.strftime('%d/%m') for d in weekend_pairs)
            f.write(
                f"  • {len(weekend_pairs) * 2} folga(s) de fim de semana "
                f"({len(weekend_pairs)} par(es) sábado+domingo): {pares_txt}.\n"
            )
        else:
            f.write("  • 0 folgas de fim de semana no mês auditado.\n")
        f.write("1.4 Agrupadas:\n")
        if grouped_runs_2p:
            grupos_txt = ", ".join(
                f"{a.strftime('%d/%m')} a {b.strftime('%d/%m')} ({n} dias)" for a, b, n in grouped_runs_2p
            )
            maior = max(n for _, _, n in grouped_runs_2p)
            f.write(f"  • {len(grouped_runs_2p)} agrupamento(s): {grupos_txt}. Maior sequência: {maior} dias.\n\n")
        else:
            f.write("  • Não houve folgas agrupadas (2 ou mais dias consecutivos).\n\n")

        f.write("2. Verificação do sexto período (132 horas)\n")
        if sixth_checks:
            for idx, c in enumerate(sixth_checks, start=1):
                status = "CONFORME" if c["compliant"] else "NÃO CONFORME"
                folga_txt = self._dt_local_str(c["folga_start_utc"], profile) if c["folga_start_utc"] else "Sem folga no mês após o início da sequência"
                f.write(
                    f"  • Seq. {idx}: {c['run_start'].strftime('%d/%m')} a {c['run_end'].strftime('%d/%m')} "
                    f"({c['run_days']} dias). Início 1º período: {self._dt_local_str(c['start_dt_utc'], profile)}. "
                    f"Vencimento (132h): {self._dt_local_str(c['deadline_utc'], profile)}. "
                    f"Início da folga: {folga_txt}. Status: {status}.\n"
                )
        else:
            f.write("  • Não houve sequência de 6 dias consecutivos de tarefas no mês auditado.\n")
        f.write("\n")

        f.write("3. Madrugadas consecutivas\n")
        f.write(f"  • Total de jornadas com madrugada: {len(night_dates)}.\n")
        if night_runs:
            runs_txt = ", ".join(
                f"{a.strftime('%d/%m')} a {b.strftime('%d/%m')} ({n})" for a, b, n in night_runs
            )
            f.write(f"  • Sequências consecutivas: {len(night_runs)}. Detalhe: {runs_txt}.\n\n")
        else:
            f.write("  • Não houve madrugadas consecutivas no mês auditado.\n\n")

        f.write("4. Total das jornadas semanais e mensais\n")
        if ex44_doc and ex44_clausula:
            f.write(f"  • Referência: {ex44_doc}, cláusula {ex44_clausula}.\n")
        for w in week_rows:
            marca = f" [>{weekly_limit_h}h]" if w["jornada_min"] > weekly_limit_h * 60 else ""
            f.write(
                f"  • {w['week_start'].strftime('%d/%m')} a {w['week_end'].strftime('%d/%m')}: "
                f"{self._fmt_minutes(w['jornada_min'])}{marca}\n"
            )
        f.write(f"  • Total mensal de jornada: {self._fmt_minutes(monthly_jornada_min)}.\n")
        if monthly_over_176:
            f.write(f"  • ALERTA: total mensal de jornada excedeu {monthly_limit_h:02d}:00.\n")
        else:
            f.write(f"  • OK: total mensal de jornada não excedeu {monthly_limit_h:02d}:00.\n")

        if weekly_over_44:
            f.write(f"  • Semanas com jornada superior a {weekly_limit_h:02d}:00:\n")
            for w in weekly_over_44:
                excess_44 = w["jornada_min"] - (weekly_limit_h * 60)
                excess_60 = max(0, w["jornada_min"] - (weekly_ref_hora_extra_h * 60))
                f.write(
                    f"    - {w['week_start'].strftime('%d/%m')} a {w['week_end'].strftime('%d/%m')}: "
                    f"{self._fmt_minutes(w['jornada_min'])} "
                    f"(acima de {weekly_limit_h:02d}:00 em {self._fmt_minutes(excess_44)}; "
                    f"acima de {weekly_ref_hora_extra_h:02d}:00 em {self._fmt_minutes(excess_60)}).\n"
                )
            if ex44_texto:
                clausula_txt = f" (Cláusula {ex44_clausula})" if ex44_clausula else ""
                f.write(f"  • OBS (CCT{clausula_txt}): {ex44_texto}\n")
            else:
                clausula_txt = f" (Cláusula {ex44_clausula})" if ex44_clausula else ""
                f.write(
                    f"  • OBS{clausula_txt}: Havendo excesso semanal de jornada, a hora excedente deve ser objeto de compensação ou de pagamento.\n"
                )
        else:
            f.write(f"  • Não houve semana com jornada superior a {weekly_limit_h:02d}:00.\n")
        f.write("\n")

        f.write("5. Total de horas voadas no período auditado\n")
        f.write(f"  • {self._fmt_minutes(total_voo_min)}\n\n")

    @staticmethod
    def _hora_matches_h_bucket(hora_local: datetime.time, bucket_label: str) -> bool:
        """Verifica se HH:MM pertence a bucket no formato '07h00-13h59'."""
        m = re.match(r"^(\d{2})h(\d{2})-(\d{2})h(\d{2})$", str(bucket_label).strip())
        if not m:
            return False
        h1, m1, h2, m2 = map(int, m.groups())
        start = h1 * 60 + m1
        end = h2 * 60 + m2
        cur = hora_local.hour * 60 + hora_local.minute
        if start <= end:
            return start <= cur <= end
        return cur >= start or cur <= end

    @staticmethod
    def _parse_table_cell_fdp_voo(value: str) -> Tuple[str, str]:
        """Converte célula da tabela ex. '15 (13,5)' para ('15:00', '13:30')."""
        txt = str(value or "").strip()
        m = re.match(r"^(\d+)\s*\(([0-9.,]+)\)$", txt)
        if not m:
            return "00:00", "00:00"
        fdp_h = int(m.group(1))
        voo_num = float(m.group(2).replace(',', '.'))
        voo_min = int(round(voo_num * 60))
        return f"{fdp_h:02d}:00", f"{voo_min // 60:02d}:{voo_min % 60:02d}"

    def _find_table_row_for_time(self, table_path: pathlib.Path, hora_local: datetime.time) -> Optional[Dict[str, Any]]:
        if not table_path.exists():
            return None
        try:
            with open(table_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for row in data[3:]:
                bkt = str(row.get("0", "")).strip()
                if self._hora_matches_h_bucket(hora_local, bkt):
                    return row
        except Exception:
            return None
        return None

    def _write_limits_snapshot(
        self,
        f,
        profile: AeronautaProfile,
        loader: Optional[LimitsLoader],
        hora_apres_local: Optional[datetime.time],
        pousos: int,
    ):
        f.write(f"- Referência documental - FRMS: {profile.frms}\n\n")
        if loader is None:
            f.write("- Limites do JSON indisponíveis.\n\n")
            return

        f.write("**Limites aplicáveis ao horário de apresentação da jornada:**\n")
        if hora_apres_local is None:
            f.write("  • Horário de apresentação indisponível.\n")
            self._write_special_duty_limits_snapshot(f, profile, loader)
            f.write("\n")
            return

        is_wocl = hora_apres_local.hour < 6
        is_comissario = "COMISS" in _normalize_text(profile.funcao)

        if not is_comissario:
            # --- TÉCNICOS (Pilotos) ---
            f.write("  [TÉCNICOS]\n")
            f.write("  • TÉCNICOS | SIMPLES | Classe de acomodação: N/A: ")
            simp_fdp = loader.get_fdp_max_minutes(
                hora_apres_local,
                pousos=pousos,
                crew_type="SIMPLES",
                aclim=profile.aclimatado,
                frms=profile.frms,
                funcao="PILOTO",
                is_wocl=is_wocl,
            )
            simp_voo = loader.get_voo_max_minutes(
                hora_apres_local,
                pousos=pousos,
                crew_type="SIMPLES",
                aclim=profile.aclimatado,
                frms=profile.frms,
                funcao="PILOTO",
                is_wocl=is_wocl,
            )
            simp_pousos_max = loader.get_pousos_max(
                hora_apres_local,
                pousos=pousos,
                crew_type="SIMPLES",
                aclim=profile.aclimatado,
                frms=profile.frms,
            )
            simp_pousos_str = str(simp_pousos_max) if simp_pousos_max is not None else "N/A"
            f.write(
                f"Jornada: {self._fmt_minutes(simp_fdp or 0)} / "
                f"Voo: {self._fmt_minutes(simp_voo or 0)} / "
                f"Pousos máximo: {simp_pousos_str}\n"
            )

            b2_row = self._find_table_row_for_time(TABELA_B2_PATH, hora_apres_local)
            if b2_row is not None:
                c1_fdp, c1_voo = self._parse_table_cell_fdp_voo(b2_row.get("2", ""))
                c2_fdp, c2_voo = self._parse_table_cell_fdp_voo(b2_row.get("4", ""))
                c3_fdp, c3_voo = self._parse_table_cell_fdp_voo(b2_row.get("6", ""))
                r1_fdp, r1_voo = self._parse_table_cell_fdp_voo(b2_row.get("3", ""))
                r2_fdp, r2_voo = self._parse_table_cell_fdp_voo(b2_row.get("5", ""))
                r3_fdp, r3_voo = self._parse_table_cell_fdp_voo(b2_row.get("7", ""))

                f.write(
                    "  • TÉCNICOS | COMPOSTA: "
                    f"Classe 1 (Jornada {c1_fdp} / Voo {c1_voo}); "
                    f"Classe 2 (Jornada {c2_fdp} / Voo {c2_voo}); "
                    f"Classe 3 (Jornada {c3_fdp} / Voo {c3_voo}) / "
                    "Pousos máximo: N/A\n"
                )
                f.write(
                    "  • TÉCNICOS | REVEZAMENTO: "
                    f"Classe 1 (Jornada {r1_fdp} / Voo {r1_voo}); "
                    f"Classe 2 (Jornada {r2_fdp} / Voo {r2_voo}); "
                    f"Classe 3 (Jornada {r3_fdp} / Voo {r3_voo}) / "
                    "Pousos máximo: N/A\n"
                )
            else:
                f.write("  • TÉCNICOS | COMPOSTA: Classe 1 (Jornada 00:00 / Voo 00:00); Classe 2 (Jornada 00:00 / Voo 00:00); Classe 3 (Jornada 00:00 / Voo 00:00) / Pousos máximo: N/A\n")
                f.write("  • TÉCNICOS | REVEZAMENTO: Classe 1 (Jornada 00:00 / Voo 00:00); Classe 2 (Jornada 00:00 / Voo 00:00); Classe 3 (Jornada 00:00 / Voo 00:00) / Pousos máximo: N/A\n")
        else:
            # --- COMISSÁRIOS (Cabine) ---
            f.write("  [COMISSÁRIOS]\n")
            com_simp_fdp = loader.get_fdp_max_minutes(
                hora_apres_local,
                pousos=pousos,
                crew_type="SIMPLES",
                aclim=profile.aclimatado,
                frms=profile.frms,
                funcao="COMISSARIO",
                is_wocl=is_wocl,
            )
            com_simp_voo = loader.get_voo_max_minutes(
                hora_apres_local,
                pousos=pousos,
                crew_type="SIMPLES",
                aclim=profile.aclimatado,
                frms=profile.frms,
                funcao="COMISSARIO",
                is_wocl=is_wocl,
            )
            f.write(
                f"  • COMISSÁRIOS | SIMPLES | Classe de acomodação: N/A: "
                f"Jornada: {self._fmt_minutes(com_simp_fdp or 0)} / "
                f"Voo: {self._fmt_minutes(com_simp_voo or 0)} / "
                f"Pousos máximo: N/A\n"
            )

            b3_row = self._find_table_row_for_time(TABELA_B3_PATH, hora_apres_local)
            if b3_row is not None:
                c12_fdp, c12_voo = self._parse_table_cell_fdp_voo(b3_row.get("2", ""))
                c3_fdp, c3_voo = self._parse_table_cell_fdp_voo(b3_row.get("4", ""))
                r12_fdp, r12_voo = self._parse_table_cell_fdp_voo(b3_row.get("3", ""))
                r3_fdp, r3_voo = self._parse_table_cell_fdp_voo(b3_row.get("5", ""))

                f.write(
                    "  • COMISSÁRIOS | COMPOSTA: "
                    f"Classe 1/2 (Jornada {c12_fdp} / Voo {c12_voo}); "
                    f"Classe 3 (Jornada {c3_fdp} / Voo {c3_voo}) / "
                    "Pousos máximo: N/A\n"
                )
                f.write(
                    "  • COMISSÁRIOS | REVEZAMENTO: "
                    f"Classe 1/2 (Jornada {r12_fdp} / Voo {r12_voo}); "
                    f"Classe 3 (Jornada {r3_fdp} / Voo {r3_voo}) / "
                    "Pousos máximo: N/A\n"
                )
            else:
                f.write("  • COMISSÁRIOS | COMPOSTA: Classe 1/2 (Jornada 00:00 / Voo 00:00); Classe 3 (Jornada 00:00 / Voo 00:00) / Pousos máximo: N/A\n")
                f.write("  • COMISSÁRIOS | REVEZAMENTO: Classe 1/2 (Jornada 00:00 / Voo 00:00); Classe 3 (Jornada 00:00 / Voo 00:00) / Pousos máximo: N/A\n")

        self._write_special_duty_limits_snapshot(f, profile, loader)

        f.write("\n")

    def _write_special_duty_limits_snapshot(
        self,
        f,
        profile: AeronautaProfile,
        loader: Optional[LimitsLoader],
    ):
        """Exibe limites de RESERVA e SOBREAVISO aplicáveis a qualquer empresa."""
        if loader is None:
            return

        reserva_min = loader.get_special_duty_limit_minutes("reserva", crew_type=profile.crew_type)
        sobreaviso_min = loader.get_special_duty_limit_minutes("sobreaviso", crew_type=profile.crew_type)
        standby_rule = loader._standby_rules.get("SOBREAVISO") if hasattr(loader, "_standby_rules") else None
        standby_ratio = standby_rule.get("call_conversion_ratio") if isinstance(standby_rule, dict) else None
        standby_rest_if_called = None
        standby_rest_if_not_called = None
        if isinstance(standby_rule, dict):
            post_rest = standby_rule.get("post_standby_rest", {})
            if isinstance(post_rest, dict):
                standby_rest_if_called = post_rest.get("if_called_min")
                standby_rest_if_not_called = post_rest.get("if_not_called_min")

        f.write("  [RESERVA / SOBREAVISO]\n")
        f.write(
            f"  • RESERVA | SIMPLES | Classe de acomodação: N/A: "
            f"Jornada: {self._fmt_minutes(reserva_min or 0) if reserva_min is not None else 'N/A'} / "
            f"Voo: N/A / Pousos máximo: N/A\n"
        )
        reserva_note = (
            "Prevista a reserva por prazo superior a 3 (três) horas, o operador deve "
            "assegurar ao tripulante acomodação para reserva, conforme estabelecido "
            "no parágrafo 117.3(b)(2)."
        )
        f.write(textwrap.fill(reserva_note, width=88, initial_indent="  • OBS RESERVA: ", subsequent_indent="                ") + "\n")
        
        sobreaviso_line = (
            f"SOBREAVISO | SIMPLES | Classe de acomodação: N/A: "
            f"Jornada: {self._fmt_minutes(sobreaviso_min or 0) if sobreaviso_min is not None else 'N/A'} / "
            f"Voo: N/A / Pousos máximo: N/A"
        )
        extras = []
        if standby_ratio:
            extras.append(f"Conversão chamada: {standby_ratio}")
        if standby_rest_if_called:
            extras.append(f"Repouso pós-chamada: {standby_rest_if_called}")
        if standby_rest_if_not_called:
            extras.append(f"Repouso sem chamada: {standby_rest_if_not_called}")
        if extras:
            sobreaviso_line += f" / {'; '.join(extras)}"
        
        f.write(textwrap.fill(sobreaviso_line, width=88, initial_indent="  • ", subsequent_indent="    ") + "\n")

    def _write_rest_limits_snapshot(
        self,
        f,
        profile: AeronautaProfile,
        loader: Optional[LimitsLoader],
        jornada_minutes: int,
    ):
        f.write("**Limites de repouso mínimo para a jornada executada:**\n")
        f.write(f"- Jornada executada considerada: {self._fmt_minutes(jornada_minutes)}\n")
        if loader is None:
            f.write("- Limites de repouso do JSON indisponíveis.\n\n")
            return

        faixas = loader.get_rest_ranges_snapshot(
            aclim=profile.aclimatado,
            frms=profile.frms,
        )

        if faixas:
            for faixa in faixas:
                fdp_min = faixa.get("fdp_min")
                fdp_max = faixa.get("fdp_max")
                descanso = faixa.get("descanso_min")
                if fdp_max is None:
                    faixa_label = f"Jornada superior a {self._fmt_minutes(max(0, (fdp_min or 0) - 1))}"
                else:
                    faixa_label = f"Jornada até {self._fmt_minutes(fdp_max)}"
                f.write(
                    f"  • TRIPULAÇÃO | {faixa_label}: "
                    f"Repouso mínimo: {self._fmt_minutes(descanso or 0)}\n"
                )
        else:
            rest_min = loader.get_rest_min_minutes(
                jornada_minutes,
                crew_type=profile.crew_type,
                aclim=profile.aclimatado,
                frms=profile.frms,
            )
            f.write(
                "  • TRIPULAÇÃO: "
                f"Repouso mínimo: {self._fmt_minutes(rest_min or 0) if rest_min is not None else 'N/A'}\n"
            )
        f.write("\n")

    def _write_jornada_detail(
        self,
        f,
        profile: AeronautaProfile,
        jornada: Jornada,
        next_jornada: Optional[Jornada],
        loader: Optional[LimitsLoader],
    ):
        entries = list(jornada.atividades)
        print(f"[DEBUG] Chamou _write_jornada_detail para {jornada.data.strftime('%d/%m/%Y')}")
        print(f"[DEBUG] entries (len={len(entries)}): {entries}")

        if not entries:
            print(f"[DEBUG] Nenhuma atividade encontrada para o dia {jornada.data.strftime('%d/%m/%Y')}")
            print(f"[DEBUG] entries: {entries}")
            return

        blocos = self._extrair_blocos(entries)
        print(f"[DEBUG] blocos (len={len(blocos)}): {blocos}")
        if not blocos:
            print(f"[DEBUG] Nenhum bloco extraído para o dia {jornada.data.strftime('%d/%m/%Y')}")
            print(f"[DEBUG] blocos: {blocos}")
            return
        bloco = blocos[0]  # Usa apenas o primeiro bloco do dia
        print(f"[DEBUG] Bloco do dia {jornada.data.strftime('%d/%m/%Y')}: {len(bloco)} atividades")
        for e in bloco:
            # Exibe todos os atributos do objeto de atividade
            print(f"[DEBUG]   Atividade: {e.__dict__ if hasattr(e, '__dict__') else str(e)}")
            # Exibe também os principais campos esperados
            print(f"[DEBUG]     voo_numero={getattr(e, 'voo_numero', '')!r}  id_leg={getattr(e, 'id_leg', '')!r}")

        block_minutes = sum(e.duration_minutes(profile) for e in bloco)
        jornada_minutes = jornada.duracao_jornada_minutos()
        flight_minutes = sum(e.duration_minutes(profile) for e in bloco if self._is_voo_atividade(e, profile))
        pousos = sum(1 for e in bloco if hasattr(e, 'is_pouso') and e.is_pouso()) if bloco else 0

        first_entry = bloco[0]
        last_entry = bloco[-1]

        pre_minutes = 0
        if jornada.hora_apresentacao:
            pre_minutes = max(0, int((first_entry.get_start_datetime(profile) - jornada.hora_apresentacao).total_seconds() / 60))

        post_minutes = 0
        if jornada.hora_encerramento:
            post_minutes = max(0, int((jornada.hora_encerramento - last_entry.get_end_datetime(profile)).total_seconds() / 60))

        duty_rule = DailyDutyLimitRule(profile.tipo_aeronave_principal, profile.funcao, cct_limit_hours=None)
        hora_apres_local = profile.get_local_datetime(jornada.hora_apresentacao).time() if jornada.hora_apresentacao else None
        limit_hours = duty_rule.get_applicable_limit(
            profile,
            hora_apres_local,
            pousos=pousos,
            is_wocl=jornada.includes_night_duty(),
        )
        limit_minutes = int(limit_hours * 60)

        rest_obt = None
        if next_jornada and jornada.hora_encerramento and next_jornada.hora_apresentacao:
            rest_obt = int((next_jornada.hora_apresentacao - jornada.hora_encerramento).total_seconds() / 60)

        repouso_csv = self._repouso_csv_jornada(entries)
        repouso_apos_jornada = repouso_csv if repouso_csv else (self._fmt_minutes(rest_obt) if rest_obt is not None else "N/A")

        f.write(f"# Cálculos objetivos ({jornada.data.strftime('%d/%m/%Y')})\n")
        f.write(f"- **Blocos:**\n")
        for e in bloco:
            voo = getattr(e, 'voo_numero', '') or ''
            id_leg = (getattr(e, 'id_leg', '') or '')
            f.write(f"  • {voo} {id_leg}\n")
        f.write(f"  = **{self._fmt_minutes(block_minutes)}**\n")

        f.write(f"- **Solo entre pernas:**\n")
        if len(entries) > 1:
            for prev, curr in zip(entries, entries[1:]):
                try:
                    gap_minutes = int((curr.get_start_datetime(profile) - prev.get_end_datetime(profile)).total_seconds() / 60)
                except Exception:
                    gap_minutes = 0
                f.write(f"  • {self._activity_place(prev)}: -> = **{self._fmt_minutes(gap_minutes)}**\n")
        else:
            f.write(f"  • ****: -> = ****\n")


        # Exibe Tempo Apresentacao apenas se houver id_leg terminando em '-IF' ou '-I'
        has_apresentacao = any(
            (getattr(a, 'id_leg', '') or '').upper().endswith('-IF') or (getattr(a, 'id_leg', '') or '').upper().endswith('-I')
            for a in entries
        )
        if has_apresentacao:
            f.write(f"- **Aps até Início:** -> = **{self._fmt_minutes(pre_minutes)}**\n")
        else:
            f.write(f"- **Aps até Início:** -> = **N/A**\n")

        # Exibe Tempo Corte apenas se houver id_leg terminando em '_IF' ou '-F'
        has_corte = any(
            (getattr(a, 'id_leg', '') or '').upper().endswith('_IF') or (getattr(a, 'id_leg', '') or '').upper().endswith('-F')
            for a in entries
        )
        if has_corte:
            _corte_raw = last_entry.tempo_corte_raw if last_entry and last_entry.tempo_corte_raw else ''
            try:
                # Converte "0 days 00:30:00" ou "00:30:00" para HH:MM
                import re as _re
                _m = _re.search(r'(\d+):(\d+):\d+', _corte_raw)
                if _m:
                    _h, _mi = int(_m.group(1)), int(_m.group(2))
                    # Se vier "X days HH:MM:SS", soma os dias
                    _d = _re.search(r'(\d+)\s+day', _corte_raw)
                    if _d:
                        _h += int(_d.group(1)) * 24
                    corte_fmt = f"{_h:02d}:{_mi:02d}"
                else:
                    corte_fmt = self._fmt_minutes(post_minutes)
            except Exception:
                corte_fmt = self._fmt_minutes(post_minutes)
            f.write(f"- **Corte até Início do Repouso:** -> = **{corte_fmt}**\n\n")
        else:
            f.write(f"- **Corte até Início do Repouso:** -> = **N/A**\n\n")

        if flight_minutes > 0:
            f.write(f"**Tempo de voo do dia:** {self._fmt_minutes(flight_minutes)}\n")
        f.write(f"**Jornada do dia (apresentação->liberação):** {self._fmt_minutes(jornada_minutes)}\n")
        f.write(f"**Repouso após a jornada:** {repouso_apos_jornada}\n\n")

        self._write_limits_snapshot(f, profile, loader, hora_apres_local, pousos)
        self._write_rest_limits_snapshot(f, profile, loader, jornada_minutes)

        if flight_minutes > 0 and flight_minutes > limit_minutes:
            f.write(f"- CRÍTICA - Tempo de voo {self._fmt_minutes(flight_minutes)} excede {self._fmt_minutes(limit_minutes)}.\n")
        if flight_minutes > 0:
            f.write("- OBS: Os valores de Tempo de voo, Jornada do dia e Repouso após a jornada foram reportados acima, você deve conferir com os limites disponibilizados.\n")
        else:
            f.write("- OBS: Sem atividade de voo no dia (apenas jornada/folga). Verifique os limites de repouso/folga aplicáveis.\n")
        f.write("\n------------------------------------------------------------------------------\n\n")

    @staticmethod
    def _find_next_non_folga_entry(
        entry: ScheduleEntry,
        profile: AeronautaProfile,
        all_entries_sorted: List[ScheduleEntry],
    ) -> Optional[ScheduleEntry]:
        passed_current = False
        for candidate in all_entries_sorted:
            if not passed_current:
                if candidate is entry:
                    passed_current = True
                continue
            if candidate.is_folga(profile.folgas_set):
                continue
            return candidate
        return None

    def _build_folga_lastro_observation(
        self,
        entry: ScheduleEntry,
        profile: AeronautaProfile,
        all_entries_sorted: List[ScheduleEntry],
    ) -> Optional[str]:
        if not entry.is_folga(profile.folgas_set):
            return None
        if entry.is_full_civil_day(profile):
            return None

        next_programming = self._find_next_non_folga_entry(entry, profile, all_entries_sorted)
        if next_programming is None:
            return None

        start_local, end_local = entry.get_local_interval(profile)
        next_start_local, _ = next_programming.get_local_interval(profile)
        slack_minutes = int((next_start_local - end_local).total_seconds() / 60)
        total_until_next_minutes = int((next_start_local - start_local).total_seconds() / 60)

        if slack_minutes > 0 and total_until_next_minutes >= MINUTES_PER_CIVIL_DAY:
            return (
                "O TOTAL DE HORAS DA FOLGA ESTÁ EM DESACORDO COM A LEGISLAÇÃO, "
                "MAS COMO EXISTE LASTRO ATÉ O INÍCIO DA PRÓXIMA PROGRAMAÇÃO O TOTAL DE HORAS "
                "É SUFICIENTE PARA O MÍNIMO TOTAL DE HORAS PREVISTAS."
            )
        return None

    def _write_non_work_day_detail(
        self,
        f,
        profile: AeronautaProfile,
        day_date: datetime.date,
        entries: List[ScheduleEntry],
        all_entries_sorted: List[ScheduleEntry],
    ):
        """Detalha dias sem jornada operacional (ex.: DO/DR/RO/RP), para manter rastreabilidade completa."""
        if not entries:
            return

        sorted_entries = sorted(entries, key=lambda e: e.get_start_datetime(profile))
        block_label = "+".join(self._activity_label(e) for e in sorted_entries)
        origin = self._activity_place(sorted_entries[0])
        destination = self._activity_place(sorted_entries[-1])
        total_minutes = sum(e.duration_minutes(profile) for e in sorted_entries)

        f.write(f"# Cálculos objetivos ({day_date.strftime('%d/%m/%Y')})\n")
        f.write("- **Blocos:**\n")
        f.write(f"  • {block_label} {origin}->{destination} - = **{self._fmt_minutes(total_minutes)}**\n")
        f.write("- **Itens do dia:**\n")

        for e in sorted_entries:
            try:
                ini = profile.get_local_datetime(e.get_start_datetime(profile)).strftime('%H:%M')
                fim = profile.get_local_datetime(e.get_end_datetime(profile)).strftime('%H:%M')
            except Exception:
                ini, fim = "N/A", "N/A"
            f.write(
                f"  • {self._activity_label(e)} {self._activity_place(e)} "
                f"({ini}->{fim}) = **{self._fmt_minutes(e.duration_minutes(profile))}**\n"
            )
            lastro_obs = self._build_folga_lastro_observation(e, profile, all_entries_sorted)
            if lastro_obs:
                f.write(textwrap.fill(lastro_obs, width=88, initial_indent="    - OBS LASTRO: ", subsequent_indent="                    ") + "\n")

        f.write("\n**Tempo de voo do dia:** 00:00\n")
        f.write("**Jornada do dia (apresentação->liberação):** N/A (dia sem jornada operacional)\n")
        f.write("**Repouso após a jornada:** N/A\n\n")
        f.write("- OBS: Dia registrado com programação não operacional (folga/repouso).\n")
        f.write("\n------------------------------------------------------------------------------\n\n")

    def generate_report(self,
                        aeronauta_profile: AeronautaProfile,
                        schedule: Schedule,
                        violations: List[Violation],
                        output_path: pathlib.Path):
        # print("Iniciando geração do relatório em texto...")

        def _print_progress(current: int, total: int, prefix: str = "Progresso"):
            total = max(total, 1)
            pct = int((current / total) * 100)
            bar_len = 30
            filled = int((current / total) * bar_len)
            bar = '█' * filled + '-' * (bar_len - filled)
            # print(f"  [{bar}] {pct:3d}% - {prefix} ({current}/{total})")

        #with open(output_path, 'w', encoding='utf-8', newline='') as f:
        with smart_open(output_path) as f:    


            f.write("==== RELATÓRIO GERADO EM " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " ====\n")
            f.write("Análise 100% OFFLINE do período fornecido\n")
            f.write("(Dados do aeronauta extraídos do nome do arquivo)\n\n")

            f.write("==== RELATÓRIO DE CONFORMIDADE COMPLETO ====\n\n")
            f.write("# Dados do aeronauta\n")
            f.write(f"- Nome: {self.aeronauta_ctx.get('nome', 'N/A')}\n")
            f.write(f"- Matrícula: {self.aeronauta_ctx.get('matricula', 'N/A')}\n")
            f.write(f"- Base domiciliar: {self.aeronauta_ctx.get('base', 'N/A')}\n")
            f.write(f"- Função: {self.aeronauta_ctx.get('funcao', 'N/A')}\n")
            f.write(f"- Tipo de aeronave principal: {aeronauta_profile.tipo_aeronave_principal}\n\n")

            f.write("# Dados da empresa\n")
            f.write(f"- Nome completo: {aeronauta_profile.empresa_nome_completo or 'N/A'}\n")
            f.write(f"- Nome abreviado: {aeronauta_profile.empresa_nome_abreviado or 'N/A'}\n")
            f.write(f"- Nome fantasia: {aeronauta_profile.empresa_nome_fantasia or 'N/A'}\n")
            f.write(f"- RBAC: {aeronauta_profile.empresa_rbac_tipo or 'N/A'}\n")
            f.write(f"- Tipo de operação: {aeronauta_profile.empresa_tipo_operacao or 'N/A'}\n")
            f.write(f"- Gestão de fadiga: {aeronauta_profile.empresa_gestao_fadiga or 'N/A'}\n")
            f.write(f"- FRMS: {aeronauta_profile.frms}\n\n")

            f.write("# Dados da escala\n")
            f.write(f"- Arquivo fonte: {self.input_filename}\n")
            if schedule.jornadas:
                min_date = min(schedule.jornadas.keys())
                max_date = max(schedule.jornadas.keys())
                f.write(f"- Período analisado: {min_date.strftime('%d/%m/%Y')} a {max_date.strftime('%d/%m/%Y')}\n")
                f.write(f"- Total de jornadas: {len(schedule.jornadas)}\n\n")
            else:
                f.write("- Nenhuma jornada de trabalho encontrada na escala.\n\n")

            f.write("\n==============================================================================\n")
            f.write("# RESULTADO DA AUDITORIA\n")
            f.write("==============================================================================\n\n")
            if not violations:
                f.write("- Nenhuma não conformidade detectada para as regras aplicadas.\n\n")
                _print_progress(1, 1, "Sem não conformidades")
            else:
                violations_by_rule = {}
                for v in violations:
                    violations_by_rule.setdefault(v.rule_name, []).append(v)

                display_violations_by_rule = {
                    rule_name: self._compact_rule_violations_for_display(rule_name, rule_violations)
                    for rule_name, rule_violations in violations_by_rule.items()
                }
                display_total_violations = sum(len(vs) for vs in display_violations_by_rule.values())

                f.write(f"- Total de não conformidades apuradas: {len(violations)}\n")
                f.write(f"- Total de não conformidades exibidas: {display_total_violations}\n\n")
                total_violations = display_total_violations
                processed_violations = 0

                for rule_name, rule_violations in display_violations_by_rule.items():
                    f.write(f"** {rule_name} **\n")
                    for v in rule_violations:
                        f.write(f"  - Descrição: {v.description}\n")
                        f.write(f"    Referência: {v.reference}\n")
                        f.write(f"    Severidade: {v.severity}\n")
                        details_wrapped = textwrap.fill(v.details, width=70, subsequent_indent="    ")
                        f.write(f"    Detalhes: {details_wrapped}\n")

                        if v.relevant_entries_data:
                            f.write("    Dados da(s) linha(s) relevante(s):\n")
                            headers = ["Activity", "Id_Leg", "Checkin", "Start", "Dep", "Arr", "End", "Checkout"]
                            col_widths = {header: len(header) for header in headers}
                            for entry_data in v.relevant_entries_data:
                                for key, val in entry_data.items():
                                    if key in col_widths:
                                        col_widths[key] = max(col_widths[key], len(str(val)))
                            header_line = " | ".join([header.ljust(col_widths[header]) for header in headers])
                            f.write(f"      {header_line}\n")
                            f.write(f"      {'-' * len(header_line)}\n")
                            for entry_data in v.relevant_entries_data:
                                data_line = " | ".join([str(entry_data.get(header, '')).ljust(col_widths[header]) for header in headers])
                                f.write(f"      {data_line}\n")
                            f.write("\n")

                        f.write("-----------------------------------------------------------\n\n")
                        processed_violations += 1
                        _print_progress(processed_violations, total_violations, "Gerando relatório")

            self._write_monthly_summary(f, aeronauta_profile, schedule)

            f.write("\n==============================================================================\n")
            f.write("==============================================================================\n\n")
            f.write("# Cálculos objetivos por dia (todas as programações)\n\n")
            loader = get_limits_loader()
            sorted_jornadas = sorted(schedule.jornadas.values(), key=lambda j: j.data)
            next_jornada_by_date = {
                j.data: (sorted_jornadas[idx + 1] if idx + 1 < len(sorted_jornadas) else None)
                for idx, j in enumerate(sorted_jornadas)
            }

            entries_by_date: Dict[datetime.date, List[ScheduleEntry]] = {}
            for e in schedule.all_entries:
                entries_by_date.setdefault(e.data, []).append(e)
            all_entries_sorted = sorted(schedule.all_entries, key=lambda e: e.get_start_datetime(aeronauta_profile))

            all_dates = sorted(entries_by_date.keys())
            for idx, day_date in enumerate(all_dates):
                _print_progress(idx + 1, len(all_dates), "Gerando dias")
                jornada = schedule.jornadas.get(day_date)
                if jornada is not None:
                    self._write_jornada_detail(
                        f,
                        aeronauta_profile,
                        jornada,
                        next_jornada_by_date.get(day_date),
                        loader,
                    )
                else:
                    self._write_non_work_day_detail(
                        f,
                        aeronauta_profile,
                        day_date,
                        entries_by_date.get(day_date, []),
                        all_entries_sorted,
                    )

            f.write("# Informações adicionais\n")
            f.write("- Este relatório é baseado nas informações fornecidas pelo aeronauta e na legislação vigente.\n")
            f.write("- Para questões legais, recomenda-se consultar um advogado trabalhista especializado.\n")
            f.write("- Este documento não constitui aconselhamento jurídico.\n\n")
            f.write("# Fim do relatório\n")

        # print(f"Processamento finalizado com sucesso. Relatório salvo em: {output_path}")
        # print("Geração do relatório concluída.")

# --- 5. Funções de Suporte (Parsing CSV) ---

def parse_schedule_csv(
    file_path: pathlib.Path,
    aeronauta_profile: AeronautaProfile,
    audit_year_month: Optional[Tuple[int, int]] = None,
) -> Schedule:
    """
    Lê o CSV da escala e preenche o objeto Schedule.
    Tenta ler com diferentes delimitadores e codificações.
    Normaliza os nomes das colunas e mapeia para o formato esperado.
    """
    schedule = Schedule(aeronauta_profile)
    
    # Tenta ler com diferentes delimitadores e codificações
    possible_seps = [',', ';', '\t']
    possible_encodings = ['utf-8', 'latin1', 'iso-8859-1']
    df = None
    
    for enc in possible_encodings:
        for sep in possible_seps:
            try:
                df = pd.read_csv(file_path, encoding=enc, sep=sep)
                # Normaliza os nomes das colunas imediatamente após a leitura
                df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
                
                # Verifica se as colunas essenciais estão presentes após a normalização
                required_cols_check = ['activity', 'start', 'end']
                
                if all(col in df.columns for col in required_cols_check):
                    # print(f"CSV lido com sucesso usando delimitador '{sep}' e codificação '{enc}'.")
                    break # Sai do loop de delimitadores
            except Exception as e:
                continue # Tenta a próxima combinação
        if df is not None and all(col in df.columns for col in required_cols_check):
            break # Sai do loop de codificações
    
    if df is None or not all(col in df.columns for col in required_cols_check):
        raise ValueError(
            "Não foi possível ler o CSV com os delimitadores e codificações comuns, "
            "ou as colunas obrigatórias ('Activity', 'Start', 'End') não foram encontradas. "
            "Verifique o formato do seu arquivo CSV e os nomes das colunas."
        )

    # Mapeamento de colunas para garantir nomes padronizados no DataFrame
    # Note que 'data' e 'hora_inicio' serão extraídos da coluna 'start'
    # e 'hora_fim' da coluna 'end'
    standard_names_map = {
        'activity': 'tipo_atividade',
        'id_leg': 'id_leg_csv', # Renomeado para evitar conflito e indicar origem do CSV
        'checkin': 'checkin_csv',
        'start': 'start_datetime_full', 
        'dep': 'dep_csv',
        'arr': 'arr_csv',
        'end': 'end_datetime_full', 
        'checkout': 'checkout_csv',
        'tempo_operacao': 'tempo_operacao',
        'tempo_apresentacao': 'tempo_apresentacao',
        'tempo_corte': 'tempo_corte',
        'tempo_solo': 'tempo_solo',
        'tempo_jornada': 'tempo_jornada',
        'tempo_repouso': 'tempo_repouso',
        'tempo_repouso_extra_simples': 'tempo_repouso_extra_simples',
        'tempo_repouso_extra_composta': 'tempo_repouso_extra_composta',
        'tempo_repouso_extra_revezamento': 'tempo_repouso_extra_revezamento',
        'tempo_reserva': 'tempo_reserva',
        'tempo_plantao': 'tempo_plantao',
        'tempo_treinamento': 'tempo_treinamento'
    }

    # Renomeia colunas para o padrão do script
    df = df.rename(columns={k: v for k, v in standard_names_map.items() if k in df.columns})

    # Preserva valores brutos das colunas temporais para exibição fiel no relatório.
    if 'start_datetime_full' in df.columns:
        df['start_raw_csv'] = df['start_datetime_full'].fillna('').astype(str)
    else:
        df['start_raw_csv'] = ''

    if 'end_datetime_full' in df.columns:
        df['end_raw_csv'] = df['end_datetime_full'].fillna('').astype(str)
    else:
        df['end_raw_csv'] = ''

    # Preserva valores brutos de colunas opcionais para exibição fiel no relatório,
    # mesmo quando o parse de datetime falhar.
    if 'dep_csv' in df.columns:
        df['dep_raw_csv'] = df['dep_csv'].fillna('').astype(str)
    else:
        df['dep_raw_csv'] = ''

    if 'arr_csv' in df.columns:
        df['arr_raw_csv'] = df['arr_csv'].fillna('').astype(str)
    else:
        df['arr_raw_csv'] = ''

    # Adiciona colunas que podem estar faltando, mas não são essenciais para ScheduleEntry primário
    for col in ['local_inicio', 'local_fim', 'descricao', 'voo_numero']:
        if col not in df.columns:
            df[col] = ''

    # Conversão de tipos de dados para datetimes, com tratamento para erros.
    # Start/End são obrigatórios (mantém formato estrito). Campos opcionais usam parse tolerante.
    required_datetime_cols = ['start_datetime_full', 'end_datetime_full']
    optional_datetime_cols = ['checkin_csv', 'dep_csv', 'arr_csv', 'checkout_csv']

    for col in required_datetime_cols:
        if col in df.columns:
            parsed = pd.to_datetime(df[col], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            missing_mask = parsed.isna() & df[col].notna() & (df[col].astype(str).str.strip() != '')
            if missing_mask.any():
                parsed_fallback = pd.to_datetime(df.loc[missing_mask, col], errors='coerce')
                parsed.loc[missing_mask] = parsed_fallback
            df[col] = parsed
        else:
            df[col] = pd.NaT

    for col in optional_datetime_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format='%Y-%m-%d %H:%M:%S', errors='coerce')
        else:
            df[col] = pd.NaT

    # Prepara as colunas que serão usadas para construir ScheduleEntry
    df['data'] = df['start_datetime_full'].dt.date
    df['hora_inicio'] = df['start_datetime_full'].dt.time
    df['hora_fim'] = df['end_datetime_full'].dt.time # O ScheduleEntry.get_end_datetime lida com a virada do dia se hora_fim < hora_inicio

    # Considera apenas o mês auditado, desconsiderando dias fora do período (início/final)
    if audit_year_month is not None:
        y, m = audit_year_month
        before_count = len(df)
        mask_month = (
            (df['start_datetime_full'].dt.year == y) &
            (df['start_datetime_full'].dt.month == m)
        )
        df = df.loc[mask_month].copy()
        after_count = len(df)
        # print(
            # f"Filtro de período aplicado: mês auditado {m:02d}/{y}. "
            # f"Registros considerados: {after_count}/{before_count}."
        # )

    # Preenche apenas colunas textuais para evitar transformar data/hora em string
    text_cols = ['tipo_atividade', 'local_inicio', 'local_fim', 'descricao', 'voo_numero', 'id_leg_csv', 'tempo_repouso']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str)

    total_rows = len(df)
    # print(f"Iniciando parse do CSV ({total_rows} linha(s))...")

    processadas = 0
    ignoradas = 0
    passo = max(1, total_rows // 40)  # ~40 atualizações

    for i, row in df.iterrows():
        # Barra de progresso no terminal
        if (i + 1) % passo == 0 or (i + 1) == total_rows:
            pct = int(((i + 1) / total_rows) * 100) if total_rows > 0 else 100
            bar_len = 30
            filled = int(((i + 1) / total_rows) * bar_len) if total_rows > 0 else bar_len
            bar = '█' * filled + '-' * (bar_len - filled)
            # print(f"  [{bar}] {pct:3d}% - Linha {i + 1}/{total_rows}")

        # Valida data/hora obrigatórias
        if not isinstance(row['data'], datetime.date) or not isinstance(row['hora_inicio'], datetime.time) or not isinstance(row['hora_fim'], datetime.time):
            ignoradas += 1
            continue

        entry = ScheduleEntry(
            data=row['data'],
            tipo_atividade=row['tipo_atividade'].upper().strip(),
            hora_inicio=row['hora_inicio'],
            hora_fim=row['hora_fim'],
            local_inicio=row['local_inicio'].strip(), # Será string vazia se coluna não existia
            local_fim=row['local_fim'].strip(),     # Será string vazia se coluna não existia
            descricao=row['descricao'].strip(),     # Será string vazia se coluna não existia
            voo_numero=row['voo_numero'].strip() if row['voo_numero'] else None, # Será None se coluna não existia
            # Passando os novos campos do CSV
            id_leg=row['id_leg_csv'] if 'id_leg_csv' in row and pd.notna(row['id_leg_csv']) else '',
            checkin=row['checkin_csv'] if 'checkin_csv' in row and pd.notna(row['checkin_csv']) else None,
            dep=row['dep_csv'] if 'dep_csv' in row and pd.notna(row['dep_csv']) else None,
            arr=row['arr_csv'] if 'arr_csv' in row and pd.notna(row['arr_csv']) else None,
            checkout=row['checkout_csv'] if 'checkout_csv' in row and pd.notna(row['checkout_csv']) else None,
            start_raw=row['start_raw_csv'] if 'start_raw_csv' in row else '',
            end_raw=row['end_raw_csv'] if 'end_raw_csv' in row else '',
            dep_raw=row['dep_raw_csv'] if 'dep_raw_csv' in row else '',
            arr_raw=row['arr_raw_csv'] if 'arr_raw_csv' in row else '',
            tempo_repouso_raw=row['tempo_repouso'] if 'tempo_repouso' in row and pd.notna(row['tempo_repouso']) else '',
            tempo_corte_raw=str(row['tempo_corte']) if 'tempo_corte' in row and pd.notna(row['tempo_corte']) else ''
        )
        schedule.add_entry(entry)
        processadas += 1

    # print(f"Parse concluído: {processadas} linha(s) processada(s), {ignoradas} linha(s) ignorada(s).")

    return schedule


def _resolve_preferred_input_csv(selected_path: pathlib.Path) -> pathlib.Path:
    """Prefere automaticamente a QUARTA_VERSAO quando o usuário seleciona a PRIMEIRA_VERSAO."""
    stage_token = "PRIMEIRA_VERSAO"
    preferred_token = "QUARTA_VERSAO"

    if stage_token not in selected_path.name.upper():
        return selected_path

    direct_candidate = selected_path.with_name(
        re.sub(stage_token, preferred_token, selected_path.name, flags=re.IGNORECASE)
    )
    if direct_candidate.exists() and direct_candidate.is_file():
        return direct_candidate

    normalized_selected_parts = [
        part for part in re.split(r'[_\s\-]+', selected_path.stem.upper())
        if part and part not in {"PRIMEIRA", "QUARTA", "VERSAO"}
    ]

    best_candidate = None
    best_score = -1
    for candidate in selected_path.parent.glob("*.csv"):
        candidate_name_upper = candidate.name.upper()
        if preferred_token not in candidate_name_upper:
            continue
        candidate_parts = set(
            part for part in re.split(r'[_\s\-]+', candidate.stem.upper())
            if part and part not in {"PRIMEIRA", "QUARTA", "VERSAO"}
        )
        score = sum(1 for part in normalized_selected_parts if part in candidate_parts)
        if score > best_score:
            best_candidate = candidate
            best_score = score

    if best_candidate is not None and best_score > 0:
        return best_candidate

    return selected_path

# --- 6. Função Principal (main) ---

import sys
import argparse

import pytz
from pytz.exceptions import UnknownTimeZoneError

#from aeronauta import AeronautaProfile

import datetime
import pytz

def get_current_time(timezone_name='America/Sao_Paulo'):
    try:
        tz = pytz.timezone(timezone_name)
        return datetime.datetime.now(tz)
    except Exception:
        return datetime.datetime.now()

def safe_get_metadata(data, key, default=''):
    try:
        return data.get(key, default)
    except AttributeError:
        return default

def smart_open(filename, mode='r'):
    import os
    if not os.path.exists(filename):
        fallback = os.path.join('/tmp', os.path.basename(filename))
        if os.path.exists(fallback):
            return open(fallback, mode)
        else:
            raise FileNotFoundError(f"Arquivo não encontrado: {filename}")
    return open(filename, mode)

class AeronautaProfile:
    def __init__(self, nome, base, fuso, horas_voo, horas_servico, tipo_licenca):
        self.nome = nome
        self.base = base
        self.fuso = fuso if fuso else 'UTC'
        self.horas_voo = horas_voo
        self.horas_servico = horas_servico
        self.tipo_licenca = tipo_licenca

import sys
import os
import csv
from config_caminhos import BASE_COMMON_FILES_PATH, BASE_OFFICIAL_DOCS_PATH, BASE_LEGISLACAO_PATH

def main():
    # Tratamento do argumento de linha de comando ou entrada interativa
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = input("Digite o caminho do arquivo CSV: ").strip()
    
    # Validação da existência do arquivo
    if not os.path.isfile(csv_path):
        print(f"Erro: Arquivo '{csv_path}' não encontrado.")
        sys.exit(1)
    
    # Leitura do CSV com fallback de fuso_base (assumindo que possa haver coluna 'fuso_base')
    records = []
    with open(csv_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            print("Erro: Arquivo CSV vazio ou inválido.")
            sys.exit(1)
        expected_fields = ['nome', 'matricula', 'base', 'fuso_base', 'tipo', 'escala']
        fuso_col = 'fuso_base' if 'fuso_base' in reader.fieldnames else None
        for row in reader:
            # Fallback: se fuso_base não existir, usar valor padrão '-03:00'
            if fuso_col is None:
                row['fuso_base'] = '-03:00'
            records.append(row)
    
    # Mapeamento dos 6 argumentos obrigatórios da classe AeronautaProfile
    profiles = []
    for rec in records:
        try:
            profile = AeronautaProfile(
                nome=rec['nome'],
                matricula=rec['matricula'],
                base=rec['base'],
                fuso_base=rec['fuso_base'],
                tipo=rec['tipo'],
                escala=rec['escala']
            )
            profiles.append(profile)
        except KeyError as e:
            print(f"Erro: Coluna obrigatória ausente no CSV: {e}")
            sys.exit(1)
    
    # Execução da auditoria e exibição usando smart_open
    resultados = auditar_escalas(profiles)
    smart_open(resultados)

if __name__ == "__main__":
    main()