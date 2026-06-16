#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ORQUESTRADOR - IMPORTAÇÃO DE ESCALA
====================================
1. Seleciona diretório de trabalho
2. Encontra o único arquivo PDF no diretório
3. Detecta o tipo pelo nome: LATAM, SIMPL, SABRE ou CIV
4. Executa o script de importação (Passo 1) → gera CSV _PRIMEIRA_VERSAO
5. Executa COMPOEM Checkin e Checkout (Passo 2) → gera CSV _SEGUNDA_VERSAO
6. Executa ADICIONA SUFIXO NA COLUNA Id_Leg (Passo 3) → gera CSV _TERCEIRA_VERSAO
7. Executa CALCULOS VALORES INICIAIS (Passo 4) → gera CSV _QUARTA_VERSAO
8. Executa em lote os scripts finais usando o CSV _QUARTA_VERSAO
9. Exibe log em tempo real
"""

import os, sys, re, json, subprocess, shutil, smtplib, ssl, unicodedata, time
from pathlib import Path
from datetime import datetime
from email.message import EmailMessage
from tkinter import Tk, filedialog, messagebox, StringVar
from tkinter import ttk, scrolledtext
import threading

ENCODING         = "utf-8"
DIR_SCRIPTS      = Path(__file__).parent
CONFIG_FILE      = DIR_SCRIPTS / "orquestrador_config.json"

SCRIPTS = {
    "LATAM": "IMPORTA ESCALA PDF LATAM PASSO 1.py",
    "SIMPL": "IMPORTA ESCALA PDF SIMPL AZUL 19082025 PASSO 1.py",
    "SABRE": "IMPORTA ESCALA PDF SABRE AZUL 19082025 PASSO 1A.py",
    "CIV":   "IMPORTA ESCALA PDF CIV PASSO 1.py",
}
SCRIPT_PASSO2 = "COMPOEM Checkin e Checkout PASSO 2.py"
SCRIPT_PASSO3 = "ADICIONA SUFIXO NA COLUNA Id_Leg PASSO 3.py"
SCRIPT_PASSO4 = "CALCULOS VALORES INICIAIS 22082025 PASSO 4.py"
SCRIPT_MONTA_BOOK = "MONTA BOOK GERAL.py"
SCRIPT_RELATORIO_CONFORMIDADES_2 = "RELATORIO CONFORMIDADES 2.py"
SCRIPT_RELATORIO_APRESENTACAO_DETALHADO = "RELATORIO APRESENTACAO DETALHADO.py"
SCRIPT_RELATORIO_APRESENTACAO = "RELATORIO APRESENTACAO.py"
SCRIPTS_FINAIS_QUARTA = [
    "CRIA VALORES FINAIS APRESENTACAO.py",
    "CRIA VALORES FINAIS TREINAMENTO.py",
    "CRIA VALORES FINAIS CORTE.py",
    "CRIA VALORES FINAIS JORNADA.py",
    "CRIA VALORES FINAIS OPERACAO.py",
    "CRIA VALORES FINAIS PLANTAO.py",
    "CRIA VALORES FINAIS REPOUSO EXTRA.py",
    "CRIA VALORES FINAIS REPOUSO.py",
    "CRIA VALORES FINAIS RESERVA.py",
    "CRIA VALORES FINAIS TEMPO SOLO.py",
]

SCRIPTS_RELATORIOS = [
    ("RELATORIO APRESENTACAO DETALHADO.py", ("APRESENTACAO",), ()),
    ("RELATORIO APRESENTACAO.py", ("APRESENTACAO",), ()),
    ("RELATORIO TREINAMENTO DETALHADO.py", ("TREINAMENTO",), ()),
    ("RELATORIO TREINAMENTO.py", ("TREINAMENTO",), ()),
    ("RELATORIO CORTE DETALHADO.py", ("CORTE",), ()),
    ("RELATORIO CORTE.py", ("CORTE",), ()),
    ("RELATORIO JORNADA DETALHADA.py", ("JORNADA",), ()),
    ("RELATORIO JORNADA.py", ("JORNADA",), ()),
    ("RELATORIO OPERACAO DETALHADO.py", ("OPERACAO",), ()),
    ("RELATORIO OPERACAO.py", ("OPERACAO",), ()),
    ("RELATORIO PLANTAO DETALHADO.py", ("PLANTAO",), ()),
    ("RELATORIO PLANTAO.py", ("PLANTAO",), ()),
    ("RELATORIO REPOUSO EXTRA DETALHADO.py", ("REPOUSO", "EXTRA"), ()),
    ("RELATORIO REPOUSO EXTRA.py", ("REPOUSO", "EXTRA"), ()),
    ("RELATORIO REPOUSO DETALHADO.py", ("REPOUSO",), ("EXTRA",)),
    ("RELATORIO REPOUSO.py", ("REPOUSO",), ("EXTRA",)),
    ("RELATORIO RESERVAS DETALHADAS.py", ("RESERVA",), ()),
    ("RELATORIO RESERVAS.py", ("RESERVA",), ()),
    ("RELATORIO TEMPO SOLO DETALHADO.py", ("TEMPO", "SOLO"), ()),
    ("RELATORIO TEMPO EM SOLO.py", ("TEMPO", "SOLO"), ()),
]

def detectar_tipo(nome: str):
    n = nome.upper()
    # Prioridade explícita para evitar ambiguidades no nome do arquivo.
    for tipo in ("LATAM", "SIMPL", "SABRE", "CIV"):
        if tipo in n:
            return tipo
    return None

def carregar_ultimo_dir():
    try:
        if CONFIG_FILE.exists():
            d = json.loads(CONFIG_FILE.read_text(ENCODING)).get("dir_trabalho", "")
            if d and Path(d).exists():
                return d
    except Exception:
        pass
    return ""

def salvar_dir(d: str):
    try:
        CONFIG_FILE.write_text(json.dumps({"dir_trabalho": d}, indent=2, ensure_ascii=False), ENCODING)
    except Exception:
        pass


class App:
    def __init__(self, root, modo_automatico: bool = False):
        self.root = root
        self.modo_automatico = modo_automatico
        self.root.title("SPECTRUM - Importação de Escala")
        self.root.geometry("750x480")
        self._pdf  = None
        self._tipo = None
        self._processamento_ok = False
        # Inicializa variáveis de status dos scripts
        from tkinter import StringVar
        self.vPdf = StringVar()
        self.vTipo = StringVar()
        self.vScript = StringVar()
        self.vScript2 = StringVar()
        self.vScript3 = StringVar()
        self.vScript4 = StringVar()
        self.vScript5 = StringVar()
        self.vScript6 = StringVar()
        self.vScript7 = StringVar()
        self.vScript8 = StringVar()
        self._build()
        self.python_exe = self._resolver_python_exec()
        ultimo = carregar_ultimo_dir()
        if ultimo:
            self.var_dir.set(ultimo)
            self._inspecionar(ultimo)

    def _avisar(self, titulo: str, mensagem: str):
        if self.modo_automatico:
            self._log(f"[AUTO][AVISO] {titulo}: {mensagem}")
            return
        messagebox.showwarning(titulo, mensagem)

    def _erro(self, titulo: str, mensagem: str):
        if self.modo_automatico:
            self._log(f"[AUTO][ERRO] {titulo}: {mensagem}")
            return
        messagebox.showerror(titulo, mensagem)

    def _resolver_python_exec(self) -> str:
        """Escolhe um interpretador Python válido (preferindo um com pandas)."""
        candidatos = []

        py_env = os.environ.get("AERO_PYTHON_EXE", "").strip()
        if py_env:
            candidatos.append(py_env)

        candidatos.extend([
            sys.executable,
            shutil.which("python") or "",
            shutil.which("python3") or "",
        ])

        vistos = set()
        for py in candidatos:
            if not py:
                continue
            py_norm = str(Path(py)).lower()
            if py_norm in vistos:
                continue
            vistos.add(py_norm)

            try:
                r = subprocess.run(
                    [py, "-c", "import pandas"],
                    capture_output=True, text=True, timeout=20,
                    encoding=ENCODING, errors="replace"
                )
                if r.returncode == 0:
                    return py
            except Exception:
                continue

        return sys.executable

    def _build(self):
        # ── Diretório ─────────────────────────────────────────────────
        f = ttk.LabelFrame(self.root, text="Diretório de Trabalho", padding=10)
        f.pack(fill="x", padx=10, pady=10)
        self.var_dir = StringVar()
        ttk.Entry(f, textvariable=self.var_dir, width=68,
                  font=("Courier", 10), state="readonly").pack(side="left")
        ttk.Button(f, text="Selecionar...",
                   command=self._selecionar).pack(side="left", padx=8)

        # ── Detecção ──────────────────────────────────────────────────
        f2 = ttk.LabelFrame(self.root, text="Detecção Automática", padding=10)
        f2.pack(fill="x", padx=10)
        for row, (label, attr) in enumerate([
            ("PDF encontrado:", "vPdf"),
            ("Tipo detectado:", "vTipo"),
            ("Passo 1 - Importar:", "vScript"),
            ("Passo 2 - Checkin/out:", "vScript2"),
            ("Passo 3 - Id_Leg:", "vScript3"),
            ("Passo 4 - Cálculos:", "vScript4"),
            ("Finais via QUARTA:", "vScript5"),
            ("Relatórios (lote):", "vScript6"),
            ("Montar BOOK:", "vScript7"),
            ("Conformidades:", "vScript8"),
        ]):
            ttk.Label(f2, text=label, width=18, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            v = StringVar(value="—")
            setattr(self, attr, v)
            ttk.Label(f2, textvariable=v, foreground="#0055CC").grid(row=row, column=1, sticky="w")

        # ── Botão ─────────────────────────────────────────────────────
        fb = ttk.Frame(self.root)
        fb.pack(fill="x", padx=10, pady=8)
        self.btn = ttk.Button(fb, text="▶  Executar processamento completo",
                              command=self._executar, width=35, state="disabled")
        self.btn.pack(side="left")
        ttk.Button(fb, text="Sair", command=self.root.quit, width=12).pack(side="right")

        # ── Log ───────────────────────────────────────────────────────
        fl = ttk.LabelFrame(self.root, text="Log", padding=8)
        fl.pack(fill="both", expand=True, padx=10, pady=5)
        self.log = scrolledtext.ScrolledText(fl, state="disabled",
                                             font=("Courier", 9), height=10)
        self.log.pack(fill="both", expand=True)

    def _pdf_parece_escala(self, nome_pdf: str) -> bool:
        """Filtra PDFs gerados pelo próprio pipeline para não serem usados como escala de entrada."""
        n = (nome_pdf or "").upper()
        bloqueios = (
            "RELATORIO", "RELATÓRIO", "BOOK_FINAL", "HOLERITE", "CONFORMIDADE"
        )
        return not any(tok in n for tok in bloqueios)

    def _selecionar(self):
        d = filedialog.askdirectory(title="Selecione o diretório de trabalho")
        if not d:
            return
        self.var_dir.set(d)
        salvar_dir(d)
        self._inspecionar(d)

    def _inspecionar(self, d: str):
        self.vPdf.set("—"); self.vTipo.set("—"); self.vScript.set("—")
        self.vScript2.set("—"); self.vScript3.set("—"); self.vScript4.set("—"); self.vScript5.set("—"); self.vScript6.set("—"); self.vScript7.set("—"); self.vScript8.set("—")
        self.btn.config(state="disabled")
        self._pdf = self._tipo = None

        pdfs_todos = list(Path(d).glob("*.pdf"))
        pdfs = [p for p in pdfs_todos if self._pdf_parece_escala(p.name)]

        if not pdfs_todos:
            self._avisar("Sem PDF", "Nenhum PDF encontrado no diretório.")
            return
        if not pdfs:
            self._avisar(
                "PDF inválido para importação",
                "Nenhum PDF de escala foi encontrado.\n\n"
                "Há apenas PDFs gerados pelo próprio processamento "
                "(relatório/book/holerite/conformidade)."
            )
            return
        if len(pdfs) > 1:
            self._avisar("Múltiplos PDFs",
                "Mais de um PDF encontrado.\nDeixe apenas o PDF da escala no diretório.")
            return

        pdf  = pdfs[0]
        tipo = detectar_tipo(pdf.name)
        self.vPdf.set(pdf.name)

        if not tipo:
            self.vTipo.set("❌ Não identificado (precisa conter LATAM, SIMPL, SABRE ou CIV)")
            self._erro("Tipo não identificado",
                f"Não foi possível identificar o tipo de:\n{pdf.name}\n\n"
                "O nome do arquivo deve conter LATAM, SIMPL, SABRE ou CIV.")
            return

        script = SCRIPTS[tipo]
        if not (DIR_SCRIPTS / script).exists():
            self.vScript.set(f"❌ Script não encontrado: {script}")
            self._erro("Script ausente", f"Script não encontrado:\n{script}")
            return

        self.vTipo.set(f"✓ {tipo}")
        self.vScript.set(script)
        p2_ok = (DIR_SCRIPTS / SCRIPT_PASSO2).exists()
        self.vScript2.set(SCRIPT_PASSO2 if p2_ok else f"❌ {SCRIPT_PASSO2} (não encontrado)")
        p3_ok = (DIR_SCRIPTS / SCRIPT_PASSO3).exists()
        self.vScript3.set(SCRIPT_PASSO3 if p3_ok else f"❌ {SCRIPT_PASSO3} (não encontrado)")
        p4_ok = (DIR_SCRIPTS / SCRIPT_PASSO4).exists()
        self.vScript4.set(SCRIPT_PASSO4 if p4_ok else f"❌ {SCRIPT_PASSO4} (não encontrado)")
        faltando_finais = [nome for nome in SCRIPTS_FINAIS_QUARTA if not (DIR_SCRIPTS / nome).exists()]
        self.vScript5.set(
            f"{len(SCRIPTS_FINAIS_QUARTA)} scripts" if not faltando_finais
            else f"❌ faltando {len(faltando_finais)} script(s)"
        )
        faltando_rel = [nome for (nome, _, _) in SCRIPTS_RELATORIOS if not (DIR_SCRIPTS / nome).exists()]
        self.vScript6.set(
            f"{len(SCRIPTS_RELATORIOS)} scripts" if not faltando_rel
            else f"❌ faltando {len(faltando_rel)} script(s)"
        )
        monta_ok = (DIR_SCRIPTS / SCRIPT_MONTA_BOOK).exists()
        self.vScript7.set(SCRIPT_MONTA_BOOK if monta_ok else f"❌ {SCRIPT_MONTA_BOOK} (não encontrado)")
        conform_ok = (DIR_SCRIPTS / SCRIPT_RELATORIO_CONFORMIDADES_2).exists()
        self.vScript8.set(SCRIPT_RELATORIO_CONFORMIDADES_2 if conform_ok else f"❌ {SCRIPT_RELATORIO_CONFORMIDADES_2} (não encontrado)")
        self._pdf  = pdf
        self._tipo = tipo
        self.btn.config(state="normal")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        linha = f"[{ts}] {msg}\n"

        def _append_ui():
            self.log.config(state="normal")
            self.log.insert("end", linha)
            self.log.see("end")
            self.log.config(state="disabled")

        # Em modo automático/headless, evita tocar no Tk fora da main thread.
        # Também imprime no stdout para o worker capturar os logs em tempo real.
        if self.modo_automatico:
            try:
                print(linha, end="")
            except UnicodeEncodeError:
                txt = linha.encode("cp1252", errors="replace").decode("cp1252", errors="replace")
                print(txt, end="")
        else:
            try:
                if threading.current_thread() is threading.main_thread():
                    _append_ui()
                else:
                    self.root.after(0, _append_ui)
            except Exception:
                pass
        # grava em arquivo
        try:
            with open(Path(self.var_dir.get()) / "orquestrador.log", "a", encoding=ENCODING) as f:
                f.write(linha)
        except Exception:
            pass

    def _executar(self):
        self.btn.config(state="disabled")
        self._log("=" * 60)
        self._log(f"Python : {self.python_exe}")
        self._log(f"PDF    : {self._pdf.name if self._pdf and hasattr(self._pdf, 'name') else '—'}")
        self._log(f"Tipo   : {self._tipo if self._tipo else '—'}")
        self._log(f"Passo 1: {SCRIPTS[self._tipo] if self._tipo in SCRIPTS else '—'}")
        self._log(f"Passo 2: {SCRIPT_PASSO2}")
        self._log(f"Passo 3: {SCRIPT_PASSO3}")
        self._log(f"Passo 4: {SCRIPT_PASSO4}")
        self._log(f"Finais: {len(SCRIPTS_FINAIS_QUARTA)} scripts via _QUARTA_VERSAO")
        self._log(f"Relatórios: {len(SCRIPTS_RELATORIOS)} scripts")
        self._log(f"Conformidades: {SCRIPT_RELATORIO_CONFORMIDADES_2}")
        self._log(f"BOOK: {SCRIPT_MONTA_BOOK}")
        self._log("-" * 60)
        if self.modo_automatico:
            # Em headless, executa no thread principal para evitar erros de Tk.
            self._run()
        else:
            threading.Thread(target=self._run, daemon=True).start()

    def _normalizar_nome_para_comparacao(self, nome: str) -> str:
        txt = (nome or "")
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        txt = txt.upper().replace("_", " ")
        txt = re.sub(r"\s+", "", txt)
        txt = re.sub(r"[^A-Z0-9]", "", txt)
        return txt

    def _extrair_nome_e_re_do_pdf_escala(self) -> tuple[str | None, str | None]:
        """Extrai nome completo e RE do PDF de escala pelo padrão do nome do arquivo."""
        if not self._pdf:
            return None, None

        base = Path(self._pdf).stem
        nome = None
        re_empresa = None

        m_nome = re.search(r"(?i)^escala_[pe]_(.+?)_(?:[A-Z]{3,4})(?:_|$)", base)
        if m_nome:
            nome = m_nome.group(1).strip(" _-")

        m_re = re.search(r"_[A-Z]{3,4}__+(\d+)_", base, flags=re.IGNORECASE)
        if m_re:
            re_empresa = m_re.group(1)

        return nome, re_empresa

    def _extrair_re_texto(self, valor) -> str:
        if valor is None:
            return ""
        return re.sub(r"\D+", "", str(valor))

    def _valor_campo(self, registro: dict, chaves_preferenciais: tuple[str, ...]) -> str:
        """Retorna o valor textual do primeiro campo existente (case-insensitive)."""
        mapa = {str(k).lower(): k for k in registro.keys()}
        for chave in chaves_preferenciais:
            key_real = mapa.get(chave.lower())
            if key_real is not None:
                valor = registro.get(key_real)
                return "" if valor is None else str(valor)
        return ""

    def _extrair_emails_de_texto(self, texto: str) -> list[str]:
        if not texto:
            return []
        encontrados = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", texto)
        vistos = set()
        emails = []
        for e in encontrados:
            el = e.strip().lower()
            if el and el not in vistos:
                vistos.add(el)
                emails.append(el)
        return emails

    def _coletar_emails_registro(self, registro: dict) -> list[str]:
        """Coleta emails em qualquer campo que contenha 'mail' no nome."""
        emails = []
        vistos = set()
        for k, v in registro.items():
            nome_campo = str(k).lower()
            if "mail" not in nome_campo:
                continue

            if isinstance(v, list):
                partes = [str(x) for x in v]
                texto = " ; ".join(partes)
            else:
                texto = "" if v is None else str(v)

            for em in self._extrair_emails_de_texto(texto):
                if em not in vistos:
                    vistos.add(em)
                    emails.append(em)
        return emails

    def _extrair_emails_payload_rpc(self, payload) -> list[str]:
        """Extrai emails de payloads variados retornados por RPC (str/dict/list)."""
        emails = []
        vistos = set()

        def _add_texto(valor):
            texto = "" if valor is None else str(valor)
            for em in self._extrair_emails_de_texto(texto):
                if em not in vistos:
                    vistos.add(em)
                    emails.append(em)

        if payload is None:
            return emails

        if isinstance(payload, str):
            _add_texto(payload)
            return emails

        if isinstance(payload, dict):
            # Primeiro tenta chaves mais prováveis.
            chaves_prioritarias = ("get_user_email", "email", "user_email")
            for chave in chaves_prioritarias:
                if chave in payload:
                    _add_texto(payload.get(chave))

            # Depois qualquer chave relacionada a email.
            for k, v in payload.items():
                if "mail" in str(k).lower():
                    _add_texto(v)

            # Fallback: tenta todos os valores do dicionário.
            if not emails:
                for v in payload.values():
                    _add_texto(v)
            return emails

        if isinstance(payload, (list, tuple, set)):
            for item in payload:
                for em in self._extrair_emails_payload_rpc(item):
                    if em not in vistos:
                        vistos.add(em)
                        emails.append(em)
            return emails

        _add_texto(payload)
        return emails

    def _buscar_emails_aeronauta_supabase(self) -> list[str]:
        """
        Busca email do aeronauta via Supabase usando:
        1) tabela public.profiles (nome_completo / registro_empresa / user_id)
        2) RPC get_user_email(user_uuid uuid), que lê auth.users(email)
        """
        try:
            import sys
            if str(DIR_SCRIPTS) not in sys.path:
                sys.path.append(str(DIR_SCRIPTS))
            import SUPABASE_CONEXAO_DEV as supabase_dev
        except Exception as exc:
            self._log(f"[ENVIO] ⚠️ Supabase indisponível: {exc}")
            return []

        nome_pdf, re_pdf = self._extrair_nome_e_re_do_pdf_escala()
        if not nome_pdf:
            self._log("[ENVIO] ⚠️ Não foi possível extrair nome do aeronauta do PDF de escala.")
            return []

        nome_base = nome_pdf.replace("_", " ").strip()
        nome_alvo = self._normalizar_nome_para_comparacao(nome_pdf)
        re_alvo = self._extrair_re_texto(re_pdf)

        self._log(f"[ENVIO] Nome extraído para busca: {nome_pdf}")
        if re_alvo:
            self._log(f"[ENVIO] RE extraído para busca: {re_alvo}")

        try:
            config = supabase_dev.obter_config()
            cliente = supabase_dev.criar_cliente(config)

            tabelas_candidatas = []
            for t in ("profiles", config.tabela_associados, "associados"):
                if t and t not in tabelas_candidatas:
                    tabelas_candidatas.append(t)

            campos_nome = ("nome_completo", "nome", "associado", "aeronauta", "full_name", "nome_associado")
            campos_re = ("registro_empresa", "registro", "matricula", "num_matricula", "re")

            registros = []
            vistos = set()

            def _adicionar_registros(lista):
                for r in (lista or []):
                    chave = str(r.get("user_id") or r.get("id") or r)
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    registros.append(r)

            # 1) Busca por RE (mais assertiva)
            if re_alvo:
                for tabela in tabelas_candidatas:
                    for campo in campos_re:
                        try:
                            resp_re = cliente.table(tabela).select("*").eq(campo, re_alvo).limit(30).execute()
                            _adicionar_registros(resp_re.data)
                        except Exception:
                            continue

            # 2) Busca por nome (com variações)
            nome_tokens = [nome_base]
            partes_nome = [p for p in nome_base.split() if p]
            if len(partes_nome) >= 2:
                nome_tokens.append(f"{partes_nome[0]} {partes_nome[-1]}")

            for token in nome_tokens:
                for tabela in tabelas_candidatas:
                    for campo in campos_nome:
                        try:
                            resp_nome = cliente.table(tabela).select("*").ilike(campo, f"%{token}%").limit(50).execute()
                            _adicionar_registros(resp_nome.data)
                        except Exception:
                            continue

            if not registros:
                if hasattr(supabase_dev, "chave_parece_publica") and supabase_dev.chave_parece_publica(config.key):
                    self._log("[ENVIO] ⚠️ Nenhum perfil retornado. A chave atual é publishable/anon e pode estar bloqueada por RLS.")
                    self._log("[ENVIO] ⚠️ Libere policy SELECT em profiles para anon/authenticated ou use SUPABASE_KEY com service role.")
                self._log(f"[ENVIO] ⚠️ Nenhum perfil encontrado. Tabelas tentadas: {', '.join(tabelas_candidatas)}")
                return []

            # Filtra por nome normalizado
            candidatos_nome = []
            for reg in registros:
                nome_reg = self._valor_campo(reg, campos_nome)
                if self._normalizar_nome_para_comparacao(nome_reg) == nome_alvo:
                    candidatos_nome.append(reg)

            if not candidatos_nome:
                self._log("[ENVIO] ⚠️ Perfil encontrado, mas nenhum nome bateu após normalização.")
                return []

            # Desempate por RE/registro_empresa quando houver mais de um candidato
            selecionados = candidatos_nome
            if len(candidatos_nome) > 1 and re_alvo:
                por_re = []
                for reg in candidatos_nome:
                    registro = str(reg.get("registro_empresa") or "")
                    if self._extrair_re_texto(registro) == re_alvo:
                        por_re.append(reg)
                if por_re:
                    selecionados = por_re

            # Consulta email via RPC get_user_email(user_uuid)
            emails = []
            vistos = set()
            for reg in selecionados:
                user_id = reg.get("user_id")
                if not user_id:
                    continue
                try:
                    rpc_resp = cliente.rpc("get_user_email", {"user_uuid": user_id}).execute()
                    for em in self._extrair_emails_payload_rpc(rpc_resp.data):
                        if em and em not in vistos:
                            vistos.add(em)
                            emails.append(em)
                except Exception as exc_rpc:
                    self._log(f"[ENVIO] ⚠️ Falha RPC get_user_email para user_id={user_id}: {exc_rpc}")

            if not emails:
                self._log("[ENVIO] ⚠️ Perfil localizado, mas sem email retornado pela RPC get_user_email.")
                return []

            self._log(f"[ENVIO] Emails encontrados: {', '.join(emails)}")
            return emails

        except Exception as exc:
            self._log(f"[ENVIO] ⚠️ Falha na busca Supabase: {exc}")
            return []

    def _encontrar_book_final(self, base_dir: Path) -> Path | None:
        books = sorted(base_dir.glob("BOOK_FINAL_*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        return books[0] if books else None

    def _encontrar_relatorios_conformidade(self, base_dir: Path) -> list[Path]:
        rels_espaco = list(base_dir.glob("*RELATORIO CONFORMIDADE*.txt"))
        rels_sublinhado = list(base_dir.glob("*RELATORIO_CONFORMIDADE*.txt"))
        rels = sorted(list(set(rels_espaco + rels_sublinhado)), key=lambda p: p.stat().st_mtime, reverse=True)
        return rels

    def _converter_txt_conformidade_para_pdf(self, txt_path: Path) -> Path | None:
        """Converte arquivo TXT de conformidade para PDF simples (texto corrido)."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
        except Exception as exc:
            self._log(f"[ENVIO] ⚠️ reportlab não disponível para converter PDF: {exc}")
            return None

        try:
            try:
                conteudo = txt_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                conteudo = txt_path.read_text(encoding="latin-1", errors="replace")

            pdf_path = txt_path.with_suffix(".pdf")
            c = canvas.Canvas(str(pdf_path), pagesize=A4)
            largura, altura = A4

            margem_esq = 2.0 * cm
            margem_dir = 2.0 * cm
            y = altura - 2.0 * cm
            altura_linha = 12
            max_chars = 120

            c.setFont("Helvetica", 9)
            for linha in conteudo.splitlines():
                texto = linha if linha else " "
                blocos = [texto[i:i + max_chars] for i in range(0, len(texto), max_chars)] or [" "]
                for bloco in blocos:
                    if y <= 2.0 * cm:
                        c.showPage()
                        c.setFont("Helvetica", 9)
                        y = altura - 2.0 * cm
                    c.drawString(margem_esq, y, bloco)
                    y -= altura_linha

            c.save()
            self._log(f"[ENVIO] PDF de conformidade gerado: {pdf_path.name}")
            return pdf_path
        except Exception as exc:
            self._log(f"[ENVIO] ⚠️ Falha ao converter '{txt_path.name}' para PDF: {exc}")
            return None

    def _coletar_anexos_email(self, base_dir: Path, arquivo_book: Path) -> list[Path]:
        """Define anexos do email: somente relatório(s) de conformidade em PDF."""
        anexos: list[Path] = []
        relatorios_txt = self._encontrar_relatorios_conformidade(base_dir)
        for txt in relatorios_txt:
            pdf = self._converter_txt_conformidade_para_pdf(txt)
            if pdf:
                anexos.append(pdf)

        vistos = set()
        anexos_unicos = []
        for anexo in anexos:
            chave = str(anexo).lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            if anexo.exists() and anexo.is_file():
                anexos_unicos.append(anexo)
        return anexos_unicos

    def _enviar_book_por_email(self, destinatarios: list[str], anexos: list[Path]) -> bool:
        """Envia email por SMTP para os destinatários com os anexos definidos."""
        host = os.getenv("AERO_SMTP_HOST", "smtppro.zoho.com").strip()
        port = int(os.getenv("AERO_SMTP_PORT", "465").strip() or "465")
        usuario = os.getenv("AERO_SMTP_USER", "contato@spectrum-system.com").strip()
        senha = os.getenv("AERO_SMTP_PASS", "zCFYkvjP4QY6").strip()
        remetente = os.getenv("AERO_SMTP_FROM", "contato@spectrum-system.com").strip() or usuario
        usar_ssl_env = os.getenv("AERO_SMTP_SSL", "").strip().lower()
        usar_ssl = usar_ssl_env in {"1", "true", "yes", "sim"} or port == 465

        # Segurança para testes: por padrão envia apenas para o próprio login.
        modo_teste = os.getenv("AERO_EMAIL_MODO_TESTE", "0").strip().lower() in {"1", "true", "yes", "sim"}
        destino_teste = os.getenv("AERO_EMAIL_DESTINO_TESTE", "").strip().lower()
        destinatarios_finais = list(destinatarios)
        if modo_teste:
            alvo_teste = destino_teste or remetente or usuario
            if not alvo_teste:
                self._log("[ENVIO] ⚠️ Modo teste ativo, mas sem destino de teste definido.")
                return False
            destinatarios_finais = [alvo_teste]
            self._log(f"[ENVIO] Modo teste ativo. Destino forçado: {alvo_teste}")

        if not host or not remetente:
            self._log("[ENVIO] ⚠️ SMTP não configurado (AERO_SMTP_HOST / AERO_SMTP_FROM). Envio ignorado.")
            return False

        # Tenta formatar um agradecimento personalizado
        nome_aeronauta, _ = self._extrair_nome_e_re_do_pdf_escala()
        nome_formatado = nome_aeronauta.replace('_', ' ').strip().title() if nome_aeronauta else "assinante"

        msg = EmailMessage()
        msg["Subject"] = f"SPECTRUM - Seu Relatório de Conformidade - {nome_formatado}"
        msg["From"] = remetente
        msg["To"] = ", ".join(destinatarios_finais)
        if not modo_teste:
            msg["Cc"] = "spectrum-system@spectrum-system.com"
        msg.set_content(
            f"Olá, {nome_formatado}!\n\n"
            "Muito obrigado por estar conosco e utilizar o SPECTRUM.\n\n"
            "Segue em anexo o seu Relatório de Conformidade gerado automaticamente a partir do processamento de sua escala.\n\n"
            "Atenciosamente,\n"
            "Equipe SPECTRUM"
        )

        if not anexos:
            self._log("[ENVIO] ⚠️ Nenhum anexo disponível para envio.")
            return False

        for anexo in anexos:
            dados = anexo.read_bytes()
            ext = anexo.suffix.lower()
            if ext == ".pdf":
                msg.add_attachment(dados, maintype="application", subtype="pdf", filename=anexo.name)
            elif ext == ".txt":
                msg.add_attachment(dados, maintype="text", subtype="plain", filename=anexo.name)
            else:
                msg.add_attachment(dados, maintype="application", subtype="octet-stream", filename=anexo.name)

        def _enviar_com_contexto(ctx: ssl.SSLContext):
            if usar_ssl:
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as smtp:
                    if usuario and senha:
                        smtp.login(usuario, senha)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=60) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                    if usuario and senha:
                        smtp.login(usuario, senha)
                    smtp.send_message(msg)

        def _log_erro_envio(exc: Exception):
            self._log(f"[ENVIO] ✗ Falha no envio do email: {exc}")
            if isinstance(exc, smtplib.SMTPAuthenticationError):
                self._log("[ENVIO] ⚠️ Autenticação SMTP recusada (erro 535).")
                self._log("[ENVIO] ⚠️ Verifique AERO_SMTP_USER/AERO_SMTP_PASS e gere App Password no Zoho Mail.")
                self._log("[ENVIO] ⚠️ Garanta também AERO_SMTP_FROM igual ao usuário autenticado.")

        permitir_tls_inseguro = os.getenv("AERO_SMTP_PERMITIR_TLS_INSEGURO", "1").strip().lower() in {"1", "true", "yes", "sim"}

        try:
            _enviar_com_contexto(ssl.create_default_context())
        except ssl.SSLCertVerificationError as exc:
            if not permitir_tls_inseguro:
                self._log(f"[ENVIO] ✗ Falha no envio do email: {exc}")
                return False

            self._log("[ENVIO] ⚠️ Falha de validação TLS. Aplicando modo compatível (sem validação de certificado).")
            self._log("[ENVIO] ⚠️ Para bloquear esse fallback, defina AERO_SMTP_PERMITIR_TLS_INSEGURO=0.")
            try:
                _enviar_com_contexto(ssl._create_unverified_context())
            except Exception as exc2:
                _log_erro_envio(exc2)
                return False
        except Exception as exc:
            _log_erro_envio(exc)
            return False

        self._log(f"[ENVIO] ✓ Email enviado para: {', '.join(destinatarios_finais)}")
        self._log(f"[ENVIO] Anexos: {', '.join(a.name for a in anexos)}")
        return True

    def _upload_para_supabase_storage(self, caminho_arquivo: Path, nome_aeronauta: str, re_aeronauta: str) -> bool:
        """Faz upload de um arquivo para o bucket do Supabase Storage."""
        try:
            try:
                import sys
                if str(DIR_SCRIPTS) not in sys.path:
                    sys.path.append(str(DIR_SCRIPTS))
                import SUPABASE_CONEXAO_DEV as supabase_dev
            except Exception as e:
                self._log(f"[SUPABASE STORAGE] ⚠️ Erro ao importar conexao: {e}")
                return False

            config = supabase_dev.obter_config()
            cliente = supabase_dev.criar_cliente(config)

            bucket_name = os.environ.get("SUPABASE_BUCKET_RELATORIOS", "relatorios").strip()
            
            # Organiza os arquivos por RE ou nome do aeronauta para evitar colisão
            pasta_destino = re_aeronauta if re_aeronauta else (nome_aeronauta if nome_aeronauta else "geral")
            caminho_storage = f"{pasta_destino}/{caminho_arquivo.name}"

            self._log(f"[SUPABASE STORAGE] Enviando '{caminho_arquivo.name}' para '{bucket_name}/{caminho_storage}'...")
            
            ext = caminho_arquivo.suffix.lower()
            content_type = "application/pdf"
            if ext == ".csv":
                content_type = "text/csv"
            elif ext == ".txt":
                content_type = "text/plain"

            with open(caminho_arquivo, "rb") as f:
                cliente.storage.from_(bucket_name).upload(
                    path=caminho_storage,
                    file=f,
                    file_options={"content-type": content_type, "x-upsert": "true"}
                )
            
            self._log(f"[SUPABASE STORAGE] ✓ Upload concluído com sucesso!")
            return True
        except Exception as e:
            self._log(f"[SUPABASE STORAGE] ✗ Erro no upload de '{caminho_arquivo.name}': {e}")
            return False

    def _renomear_relatorios_e_sumarios(self, base_dir: Path):
        """Renomeia fisicamente os relatórios de conformidade e sumários locais no disco para o formato padronizado."""
        try:
            nome_aero, re_aero = self._extrair_nome_e_re_do_pdf_escala()
            nome_formatado = nome_aero.replace(" ", "_").strip() if nome_aero else "Aeronauta"
            registro_formatado = re_aero.strip() if re_aero else ""
            
            # Encontra o CSV da quarta versão para pegar o período e timestamp de forma precisa
            csv_path = self._encontrar_csv_passo4() or self._encontrar_csv_passo3() or self._encontrar_csv_passo2() or self._encontrar_csv_gerado()
            periodo = ""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if csv_path:
                m_periodo = re.search(r"(\d{8}_\d{8})", csv_path.name)
                if m_periodo:
                    periodo = m_periodo.group(1)
                m_ts = re.search(r"_VERSAO_(\d{8}_\d{6})", csv_path.name, re.IGNORECASE)
                if m_ts:
                    timestamp = m_ts.group(1)
                    
            periodo_suffix = f"_{periodo}" if periodo else ""
            
            # 1. Renomeia Relatório de Conformidade (TXT e PDF)
            for ext in (".txt", ".pdf"):
                for arq in base_dir.glob(f"*RELATORIO CONFORMIDADE*{ext}"):
                    if "RELATORIO_CONFORMIDADE" in arq.name and nome_formatado in arq.name:
                        continue
                    
                    if registro_formatado:
                        novo_nome = f"{nome_formatado}_{registro_formatado}_RELATORIO_CONFORMIDADE{periodo_suffix}_{timestamp}{ext}"
                    else:
                        novo_nome = f"{nome_formatado}_RELATORIO_CONFORMIDADE{periodo_suffix}_{timestamp}{ext}"
                    
                    novo_nome = novo_nome.replace(" ", "_")
                    novo_path = arq.parent / novo_nome
                    try:
                        arq.rename(novo_path)
                        self._log(f"[PADRONIZAÇÃO] Arquivo renomeado: {arq.name} -> {novo_nome}")
                    except Exception as e:
                        self._log(f"[PADRONIZAÇÃO] ⚠️ Falha ao renomear {arq.name}: {e}")

            # 2. Renomeia Sumários de Horas (.pdf)
            for arq in base_dir.glob("*.pdf"):
                nome_up = arq.name.upper()
                if arq.name.startswith(nome_formatado) and "SUMARIO_HORAS" in nome_up:
                    continue
                
                tipo_sumario = None
                if "SUMARIO" in nome_up or "SUMÁRIO" in nome_up:
                    if "APRESENTA" in nome_up:
                        tipo_sumario = "APRESENTACAO"
                    elif "CORTE" in nome_up:
                        tipo_sumario = "TEMPO_CORTE"
                    elif "TREINAMENTO" in nome_up:
                        tipo_sumario = "TREINAMENTO"
                    elif "SOLO" in nome_up:
                        tipo_sumario = "EM_SOLO"
                    elif "RESERVA" in nome_up or "EXPLORAR" in nome_up:
                        tipo_sumario = "EXPLORAR_RESERVA"
                    elif "REPOUSO" in nome_up:
                        tipo_sumario = "REPOUSO_EXTRA" if "EXTRA" in nome_up else "REPOUSO"
                    elif "PLANTAO" in nome_up or "PLANTÃO" in nome_up:
                        tipo_sumario = "PLANTAO"
                    elif "OPERACAO" in nome_up or "OPERAÇÃO" in nome_up:
                        tipo_sumario = "OPERACAO"
                    elif "JORNADA" in nome_up:
                        tipo_sumario = "JORNADA"
                    elif "DIARIA" in nome_up:
                        tipo_sumario = "DIARIAS"
                
                if tipo_sumario:
                    if registro_formatado:
                        novo_nome = f"{nome_formatado}_{registro_formatado}_SUMARIO_HORAS_{tipo_sumario}{periodo_suffix}_{timestamp}.pdf"
                    else:
                        novo_nome = f"{nome_formatado}_SUMARIO_HORAS_{tipo_sumario}{periodo_suffix}_{timestamp}.pdf"
                    
                    novo_nome = novo_nome.replace(" ", "_")
                    novo_path = arq.parent / novo_nome
                    try:
                        arq.rename(novo_path)
                        self._log(f"[PADRONIZAÇÃO] Sumário renomeado: {arq.name} -> {novo_nome}")
                    except Exception as e:
                        self._log(f"[PADRONIZAÇÃO] ⚠️ Falha ao renomear sumário {arq.name}: {e}")
        except Exception as e:
            self._log(f"[PADRONIZAÇÃO] ⚠️ Erro geral na renomeação: {e}")

    def _enviar_relatorios_supabase(self, base_dir: Path, relatorios_anexados: list[Path]):
        """Coleta e envia o relatório de conformidade e os PDFs de SUMARIO para o Supabase."""
        self._log("-" * 60)
        self._log("[SUPABASE STORAGE] Iniciando upload de relatórios...")

        nome_aero, re_aero = self._extrair_nome_e_re_do_pdf_escala()
        nome_aero_pasta = nome_aero if nome_aero else "geral"
        re_aero_pasta = re_aero if re_aero else ""

        # Arquivos de conformidade (convertidos que foram passados como anexos)
        arquivos_enviar = list(relatorios_anexados)

        # Buscar o CSV da QUARTA_VERSAO para fazer upload
        csv_quarta = self._encontrar_csv_passo4()
        if csv_quarta and csv_quarta.exists():
            arquivos_enviar.append(csv_quarta)

        # Buscar todos os PDFs que contêm SUMARIO ou SUMÁRIO no nome
        pdfs_sumario = list(base_dir.glob("*.pdf"))
        for pdf in pdfs_sumario:
            if "SUMARIO" in pdf.name.upper() or "SUMÁRIO" in pdf.name.upper():
                arquivos_enviar.append(pdf)

        # Evitar duplicados
        vistos = set()
        arquivos_unicos = []
        for arq in arquivos_enviar:
            if arq.exists() and arq.is_file():
                path_str = str(arq).lower()
                if path_str not in vistos:
                    vistos.add(path_str)
                    arquivos_unicos.append(arq)

        if not arquivos_unicos:
            self._log("[SUPABASE STORAGE] ⚠️ Nenhum PDF de sumário ou conformidade encontrado para upload.")
            return

        self._log(f"[SUPABASE STORAGE] Total de {len(arquivos_unicos)} arquivo(s) localizado(s) para upload.")
        
        sucessos = 0
        for arq in arquivos_unicos:
            if self._upload_para_supabase_storage(arq, nome_aero_pasta, re_aero_pasta):
                sucessos += 1

        self._log(f"[SUPABASE STORAGE] Uploads concluídos: {sucessos} de {len(arquivos_unicos)} arquivo(s) enviados.")

    def _limpar_subpasta_auditoria_calculos(self, base_dir: Path):
        """Remove todos os arquivos da subpasta Auditoria_Calculos (ou Auditori_Calculos)."""
        candidatos = ["Auditoria_Calculos", "Auditori_Calculos"]
        pasta_auditoria = None

        for nome in candidatos:
            p = base_dir / nome
            if p.exists() and p.is_dir():
                pasta_auditoria = p
                break

        if not pasta_auditoria:
            self._log("[LIMPEZA] Subpasta Auditoria_Calculos não encontrada. Nada para remover.")
            return

        removidos = 0
        erros = 0
        for item in pasta_auditoria.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    removidos += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    removidos += 1
            except Exception as exc:
                erros += 1
                self._log(f"[LIMPEZA] ⚠️ Falha ao remover '{item.name}': {exc}")

        self._log(f"[LIMPEZA] Auditoria_Calculos: {removidos} item(ns) removido(s), {erros} erro(s).")

    def _arquivar_arquivos_processados(self, base_dir: Path):
        """Move arquivos do diretório de trabalho para Arquivos Processados/data."""
        pasta_base = base_dir / "Arquivos Processados"
        pasta_base.mkdir(parents=True, exist_ok=True)

        data_proc = datetime.now().strftime("%d%m%Y")
        pasta_destino = pasta_base / data_proc
        if pasta_destino.exists():
            pasta_destino = pasta_base / f"{data_proc}_{datetime.now().strftime('%H%M%S')}"
        pasta_destino.mkdir(parents=True, exist_ok=True)

        movidos = 0
        erros = 0
        nomes_protegidos = {"Arquivos Processados", "holerites", "Auditoria_Calculos", "Auditori_Calculos"}

        for item in base_dir.iterdir():
            if item.name in nomes_protegidos:
                continue
            if item.is_dir():
                continue

            try:
                destino = pasta_destino / item.name

                # Em Windows, caminhos muito longos podem gerar WinError 3 durante move.
                if len(str(destino)) > 240:
                    stem_curto = re.sub(r"[^A-Za-z0-9._-]+", "_", item.stem)[:80].rstrip("._-") or "arquivo"
                    destino = pasta_destino / f"{stem_curto}_{datetime.now().strftime('%H%M%S')}{item.suffix.lower()}"

                if destino.exists():
                    destino = pasta_destino / f"{destino.stem}_{datetime.now().strftime('%H%M%S')}{destino.suffix}"

                ultimo_erro = None
                for tentativa in range(1, 4):
                    try:
                        shutil.move(str(item), str(destino))
                        movidos += 1
                        ultimo_erro = None
                        break
                    except Exception as exc_move:
                        ultimo_erro = exc_move
                        if tentativa < 3:
                            time.sleep(0.3)

                if ultimo_erro is not None:
                    raise ultimo_erro
            except Exception as exc:
                erros += 1
                self._log(f"[ARQUIVAMENTO] ⚠️ Falha ao mover '{item.name}': {exc}")

        self._log(f"[ARQUIVAMENTO] {movidos} arquivo(s) movido(s) para: {pasta_destino}")
        if erros:
            self._log(f"[ARQUIVAMENTO] Erros no arquivamento: {erros}")

        # Copia o orquestrador para o mesmo destino final dos arquivos processados.
        try:
            origem_orquestrador = Path(__file__)
            destino_orquestrador = pasta_destino / origem_orquestrador.name
            if destino_orquestrador.exists():
                destino_orquestrador = pasta_destino / f"{origem_orquestrador.stem}_{datetime.now().strftime('%H%M%S')}{origem_orquestrador.suffix}"
            shutil.copy2(str(origem_orquestrador), str(destino_orquestrador))
            self._log(f"[ARQUIVAMENTO] Orquestrador copiado para: {destino_orquestrador}")
        except Exception as exc:
            self._log(f"[ARQUIVAMENTO] ⚠️ Falha ao copiar o orquestrador: {exc}")

    def _executar_script(self, script_path: Path, env: dict) -> bool:
        """Executa um script e retorna True se OK."""
        import threading, queue as _queue

        proc = subprocess.Popen(
            [self.python_exe, str(script_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding=ENCODING, errors="replace", env=env
        )

        output_lines: list[str] = []

        def _leitor(pipe, q):
            try:
                for linha in iter(pipe.readline, ""):
                    q.put(linha)
            finally:
                q.put(None)

        q: _queue.Queue = _queue.Queue()
        t = threading.Thread(target=_leitor, args=(proc.stdout, q), daemon=True)
        t.start()

        import time as _time
        deadline = _time.monotonic() + 600
        while True:
            try:
                linha = q.get(timeout=1)
            except _queue.Empty:
                if _time.monotonic() > deadline:
                    proc.kill()
                    self._log("  [TIMEOUT] Script encerrado após 600s.")
                    return False
                continue
            if linha is None:
                break
            linha = linha.rstrip("\n")
            if linha.strip():
                self._log(f"  {linha}")
                output_lines.append(linha)

        proc.wait()
        output = "\n".join(output_lines)
        r_returncode = proc.returncode

        if r_returncode != 0:
            return False

        # Alguns scripts encerram com código 0 mesmo após abortar por erro de apoio.
        if "Erro ao carregar arquivos de apoio" in output:
            self._log("  [ORQUESTRADOR] Execução marcada como falha por erro de arquivos de apoio.")
            return False

        return True

    def _encontrar_csv_gerado(self) -> Path | None:
        """Encontra o CSV _PRIMEIRA_VERSAO gerado no diretório de trabalho."""
        dir_path = Path(self.var_dir.get())
        csvs = sorted(dir_path.glob("*_PRIMEIRA_VERSAO*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return csvs[0] if csvs else None

    def _encontrar_csv_passo2(self) -> Path | None:
        """Encontra o CSV _SEGUNDA_VERSAO gerado no diretório de trabalho."""
        dir_path = Path(self.var_dir.get())
        csvs = sorted(dir_path.glob("*_SEGUNDA_VERSAO*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return csvs[0] if csvs else None

    def _encontrar_csv_passo3(self) -> Path | None:
        """Encontra o CSV _TERCEIRA_VERSAO gerado no diretório de trabalho."""
        dir_path = Path(self.var_dir.get())
        csvs = sorted(dir_path.glob("*_TERCEIRA_VERSAO*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return csvs[0] if csvs else None

    def _encontrar_csv_passo4(self) -> Path | None:
        """Encontra o CSV _QUARTA_VERSAO gerado no diretório de trabalho."""
        dir_path = Path(self.var_dir.get())
        csvs = sorted(dir_path.glob("*_QUARTA_VERSAO*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return csvs[0] if csvs else None

    def _encontrar_csv_por_termos(self, include_terms: tuple[str, ...], exclude_terms: tuple[str, ...] = ()) -> Path | None:
        """Encontra o CSV mais recente contendo todos os termos de inclusão e nenhum termo de exclusão."""
        dir_path = Path(self.var_dir.get())
        def _norm(s: str) -> str:
            return s.upper().replace("_", " ").replace("-", " ")

        incl = tuple(_norm(t) for t in include_terms)
        excl = tuple(_norm(t) for t in exclude_terms)

        csvs = []
        for p in dir_path.glob("*.csv"):
            n = _norm(p.name)
            if not all(t in n for t in incl):
                continue
            if any(t in n for t in excl):
                continue
            csvs.append(p)

        csvs = sorted(csvs, key=lambda p: p.stat().st_mtime, reverse=True)
        return csvs[0] if csvs else None

    def _run(self):
        total_relatorios_previstos = len(SCRIPTS_RELATORIOS)
        relatorios_executados = 0
        relatorios_concluidos = 0
        relatorios_falharam = 0
        relatorios_nao_executados = total_relatorios_previstos
        scripts_nao_executados = []
        processamento_completo = False

        def registrar_nao_executado(nome_script: str, motivo: str):
            scripts_nao_executados.append((nome_script, motivo))

        def registrar_todos_nao_executados(lista_nomes, motivo: str):
            for nome in lista_nomes:
                registrar_nao_executado(nome, motivo)
        try:
            env = os.environ.copy()
            env["AERO_ESCALA_PDF"]  = str(self._pdf)
            env["PYTHONIOENCODING"] = "utf-8"
            env["AERO_NO_POPUP"] = "1"

            # ── PASSO 1: Importação ──────────────────────────────────
            self._log("[PASSO 1] Executando importação...")
            if self._tipo in SCRIPTS:
                ok1 = self._executar_script(DIR_SCRIPTS / SCRIPTS[self._tipo], env)
            else:
                self._log("[PASSO 1] Tipo de escala não reconhecido. Importação não executada.")
                ok1 = False
            if ok1:
                self._log("[PASSO 1] ✓ Concluído com sucesso!")
            else:
                self._log("[PASSO 1] ✗ Falhou — Passo 2 não será executado.")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO2, SCRIPT_PASSO3, SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "dependência anterior falhou no Passo 1"
                )
                return

            # ── PASSO 2: Checkin / Checkout ──────────────────────────
            self._log("-" * 60)
            self._log("[PASSO 2] Localizando CSV gerado...")
            csv_p1 = self._encontrar_csv_gerado()
            if not csv_p1:
                self._log("[PASSO 2] ✗ CSV _PRIMEIRA_VERSAO não encontrado no diretório.")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO2, SCRIPT_PASSO3, SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "CSV _PRIMEIRA_VERSAO não encontrado"
                )
                return

            self._log(f"[PASSO 2] CSV encontrado: {csv_p1.name}")
            script_p2 = DIR_SCRIPTS / SCRIPT_PASSO2
            if not script_p2.exists():
                self._log(f"[PASSO 2] ✗ Script não encontrado: {SCRIPT_PASSO2}")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO2, SCRIPT_PASSO3, SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    f"script ausente: {SCRIPT_PASSO2}"
                )
                return

            env2 = env.copy()
            env2["AERO_ESCALA_CSV"] = str(csv_p1)
            self._log("[PASSO 2] Executando Checkin e Checkout...")
            ok2 = self._executar_script(script_p2, env2)
            if ok2:
                self._log("[PASSO 2] ✓ Concluído com sucesso!")
            else:
                self._log("[PASSO 2] ✗ Falhou — Passo 3 não será executado.")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO3, SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "dependência anterior falhou no Passo 2"
                )
                return

            # ── PASSO 3: Id_Leg ─────────────────────────────────────
            self._log("-" * 60)
            self._log("[PASSO 3] Localizando CSV do Passo 2...")
            csv_p2 = self._encontrar_csv_passo2()
            if not csv_p2:
                self._log("[PASSO 3] ✗ CSV _SEGUNDA_VERSAO não encontrado no diretório.")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO3, SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "CSV _SEGUNDA_VERSAO não encontrado"
                )
                return

            self._log(f"[PASSO 3] CSV encontrado: {csv_p2.name}")
            script_p3 = DIR_SCRIPTS / SCRIPT_PASSO3
            if not script_p3.exists():
                self._log(f"[PASSO 3] ✗ Script não encontrado: {SCRIPT_PASSO3}")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO3, SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    f"script ausente: {SCRIPT_PASSO3}"
                )
                return

            env3 = env.copy()
            env3["AERO_ESCALA_CSV"] = str(csv_p2)
            self._log("[PASSO 3] Executando sufixo Id_Leg...")
            ok3 = self._executar_script(script_p3, env3)
            if ok3:
                self._log("[PASSO 3] ✓ Concluído com sucesso!")
            else:
                self._log("[PASSO 3] ✗ Falhou — Passo 4 não será executado.")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "dependência anterior falhou no Passo 3"
                )
                return

            # ── PASSO 4: Cálculos iniciais ──────────────────────────
            self._log("-" * 60)
            self._log("[PASSO 4] Localizando CSV do Passo 3...")
            csv_p3 = self._encontrar_csv_passo3()
            if not csv_p3:
                self._log("[PASSO 4] ✗ CSV _TERCEIRA_VERSAO não encontrado no diretório.")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "CSV _TERCEIRA_VERSAO não encontrado"
                )
                return

            self._log(f"[PASSO 4] CSV encontrado: {csv_p3.name}")
            script_p4 = DIR_SCRIPTS / SCRIPT_PASSO4
            if not script_p4.exists():
                self._log(f"[PASSO 4] ✗ Script não encontrado: {SCRIPT_PASSO4}")
                registrar_todos_nao_executados(
                    [SCRIPT_PASSO4] + SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    f"script ausente: {SCRIPT_PASSO4}"
                )
                return

            env4 = env.copy()
            env4["AERO_ESCALA_CSV"] = str(csv_p3)
            env4["AERO_OUTPUT_DIR"] = self.var_dir.get()
            self._log("[PASSO 4] Executando cálculos iniciais...")
            ok4 = self._executar_script(script_p4, env4)
            if ok4:
                self._log("[PASSO 4] ✓ Concluído com sucesso!")
            else:
                self._log("[PASSO 4] ✗ Falhou — scripts finais não serão executados.")
                registrar_todos_nao_executados(
                    SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "dependência anterior falhou no Passo 4"
                )
                return

            # ── SCRIPTS FINAIS VIA QUARTA_VERSAO ────────────────────
            self._log("-" * 60)
            self._log("[FINAIS] Localizando CSV do Passo 4...")
            csv_p4 = self._encontrar_csv_passo4()
            if not csv_p4:
                self._log("[FINAIS] ✗ CSV _QUARTA_VERSAO não encontrado no diretório.")
                registrar_todos_nao_executados(
                    SCRIPTS_FINAIS_QUARTA + [n for (n, _, _) in SCRIPTS_RELATORIOS],
                    "CSV _QUARTA_VERSAO não encontrado"
                )
                return

            self._log(f"[FINAIS] CSV encontrado: {csv_p4.name}")
            env_finais = env.copy()
            env_finais["AERO_ESCALA_CSV"] = str(csv_p4)
            env_finais["AERO_OUTPUT_DIR"] = self.var_dir.get()

            for nome_script in SCRIPTS_FINAIS_QUARTA:
                script_final = DIR_SCRIPTS / nome_script
                if not script_final.exists():
                    self._log(f"[FINAIS] ✗ Script não encontrado: {nome_script}")
                    registrar_nao_executado(nome_script, f"script ausente: {nome_script}")
                    continue

                self._log(f"[FINAIS] Executando: {nome_script}")
                ok_final = self._executar_script(script_final, env_finais.copy())
                if ok_final:
                    self._log(f"[FINAIS] ✓ Concluído: {nome_script}")
                else:
                    self._log(f"[FINAIS] ✗ Falhou: {nome_script}")
                    registrar_nao_executado(nome_script, "falha na execução")

            # ── RELATÓRIOS (LOTE) ───────────────────────────────────
            self._log("-" * 60)
            for nome_script, include_terms, exclude_terms in SCRIPTS_RELATORIOS:
                script_rel = DIR_SCRIPTS / nome_script
                if not script_rel.exists():
                    self._log(f"[RELATÓRIOS] ✗ Script não encontrado: {nome_script}")
                    registrar_nao_executado(nome_script, f"script ausente: {nome_script}")
                    continue

                csv_fonte = self._encontrar_csv_por_termos(include_terms, exclude_terms)
                if not csv_fonte:
                    self._log(
                        f"[RELATÓRIOS] ✗ CSV não encontrado para {nome_script} "
                        f"(inclui: {include_terms}, exclui: {exclude_terms})"
                    )
                    registrar_nao_executado(nome_script, "CSV fonte não encontrado para os termos exigidos")
                    continue

                env_rel = env.copy()
                env_rel["AERO_ESCALA_CSV"] = str(csv_fonte)
                env_rel["AERO_OUTPUT_DIR"] = self.var_dir.get()
                self._log(f"[RELATÓRIOS] CSV fonte ({nome_script}): {csv_fonte.name}")

                self._log(f"[RELATÓRIOS] Executando: {nome_script}")
                ok_rel = self._executar_script(script_rel, env_rel.copy())
                relatorios_executados += 1
                if ok_rel:
                    relatorios_concluidos += 1
                    self._log(f"[RELATÓRIOS] ✓ Concluído: {nome_script}")
                else:
                    relatorios_falharam += 1
                    self._log(f"[RELATÓRIOS] ✗ Falhou: {nome_script}")
                    registrar_nao_executado(nome_script, "falha na execução")

            # ── RELATÓRIO DE CONFORMIDADES 2 ───────────────────────
            self._log("-" * 60)
            script_conf = DIR_SCRIPTS / SCRIPT_RELATORIO_CONFORMIDADES_2
            if not script_conf.exists():
                self._log(f"[CONFORMIDADES] ✗ Script não encontrado: {SCRIPT_RELATORIO_CONFORMIDADES_2}")
                registrar_nao_executado(SCRIPT_RELATORIO_CONFORMIDADES_2, f"script ausente: {SCRIPT_RELATORIO_CONFORMIDADES_2}")
            else:
                csv_conf = self._encontrar_csv_passo4() or self._encontrar_csv_passo3() or self._encontrar_csv_passo2() or self._encontrar_csv_gerado()
                if not csv_conf:
                    self._log("[CONFORMIDADES] ✗ CSV fonte não encontrado para execução.")
                    registrar_nao_executado(SCRIPT_RELATORIO_CONFORMIDADES_2, "CSV fonte não encontrado")
                else:
                    env_conf = env.copy()
                    env_conf["AERO_ESCALA_CSV"] = str(csv_conf)
                    env_conf["AERO_OUTPUT_DIR"] = self.var_dir.get()
                    env_conf["AERO_NO_POPUP"] = "1"
                    self._log(f"[CONFORMIDADES] CSV fonte: {csv_conf.name}")
                    self._log(f"[CONFORMIDADES] Executando: {SCRIPT_RELATORIO_CONFORMIDADES_2}")
                    ok_conf = self._executar_script(script_conf, env_conf)
                    if ok_conf:
                        self._log(f"[CONFORMIDADES] ✓ Concluído: {SCRIPT_RELATORIO_CONFORMIDADES_2}")
                    else:
                        self._log(f"[CONFORMIDADES] ✗ Falhou: {SCRIPT_RELATORIO_CONFORMIDADES_2}")
                        registrar_nao_executado(SCRIPT_RELATORIO_CONFORMIDADES_2, "falha na execução")

            # ── RELATÓRIO DE DIÁRIAS ───────────────────────────────
            self._log("-" * 60)
            script_diarias = DIR_SCRIPTS / "RELATORIO DIARIAS.py"
            if not script_diarias.exists():
                self._log(f"[DIÁRIAS] ✗ Script não encontrado: {script_diarias.name}")
                registrar_nao_executado("RELATORIO DIARIAS.py", f"script ausente: {script_diarias.name}")
            else:
                csv_diarias = self._encontrar_csv_passo4()
                if not csv_diarias:
                    self._log("[DIÁRIAS] ✗ CSV fonte não encontrado para execução.")
                    registrar_nao_executado("RELATORIO DIARIAS.py", "CSV fonte não encontrado")
                else:
                    env_diarias = env.copy()
                    env_diarias["AERO_ESCALA_CSV"] = str(csv_diarias)
                    env_diarias["AERO_OUTPUT_DIR"] = self.var_dir.get()
                    env_diarias["AERO_NO_POPUP"] = "1"
                    self._log(f"[DIÁRIAS] CSV fonte: {csv_diarias.name}")
                    self._log(f"[DIÁRIAS] Executando: RELATORIO DIARIAS.py")
                    ok_diarias = self._executar_script(script_diarias, env_diarias)
                    if ok_diarias:
                        self._log(f"[DIÁRIAS] ✓ Concluído: RELATORIO DIARIAS.py")
                    else:
                        self._log(f"[DIÁRIAS] ✗ Falhou: RELATORIO DIARIAS.py")
                        registrar_nao_executado("RELATORIO DIARIAS.py", "falha na execução")

            # ── MONTA BOOK GERAL ───────────────────────────────────
            self._log("-" * 60)
            script_book = DIR_SCRIPTS / SCRIPT_MONTA_BOOK
            if not script_book.exists():
                self._log(f"[BOOK] ✗ Script não encontrado: {SCRIPT_MONTA_BOOK}")
                registrar_nao_executado(SCRIPT_MONTA_BOOK, f"script ausente: {SCRIPT_MONTA_BOOK}")
            else:
                env_book = env.copy()
                env_book["AERO_OUTPUT_DIR"] = self.var_dir.get()
                env_book["AERO_NO_POPUP"] = "1"
                self._log(f"[BOOK] Executando: {SCRIPT_MONTA_BOOK}")
                ok_book = self._executar_script(script_book, env_book)
                if ok_book:
                    self._log(f"[BOOK] ✓ Concluído: {SCRIPT_MONTA_BOOK}")
                    dir_trabalho = Path(self.var_dir.get())
                    self._renomear_relatorios_e_sumarios(dir_trabalho)
                    arquivo_book = self._encontrar_book_final(dir_trabalho)
                    if arquivo_book:
                        self._log(f"[ENVIO] BOOK localizado para envio: {arquivo_book.name}")
                        # Coleta e converte o PDF do relatório de conformidade
                        anexos_email = self._coletar_anexos_email(dir_trabalho, arquivo_book)
                        
                        # Tenta enviar para o assinante
                        emails = self._buscar_emails_aeronauta_supabase()
                        if emails:
                            self._enviar_book_por_email(emails, anexos_email)
                        else:
                            self._log("[ENVIO] ⚠️ Sem destinatários válidos. Envio por e-mail não realizado.")
                        
                        # Envia relatórios (conformidade e os que contêm SUMARIO) para o Supabase
                        self._enviar_relatorios_supabase(dir_trabalho, anexos_email)
                    else:
                        self._log("[ENVIO] ⚠️ BOOK_FINAL não encontrado para envio.")
                else:
                    self._log(f"[BOOK] ✗ Falhou: {SCRIPT_MONTA_BOOK}")
                    registrar_nao_executado(SCRIPT_MONTA_BOOK, "falha na execução")

            processamento_completo = True

            relatorios_nao_executados = total_relatorios_previstos - relatorios_executados

        except subprocess.TimeoutExpired:
            self._log("✗ Timeout excedido (10 min)")
        except Exception as e:
            self._log(f"✗ Erro: {e}")
        finally:
            self._log("-" * 60)
            self._log("PROCESSAMENTO ENCERRADO")
            self._log(f"[RESUMO RELATÓRIOS] Total previsto: {total_relatorios_previstos}")
            self._log(f"[RESUMO RELATÓRIOS] Efetivamente executados: {relatorios_executados}")
            self._log(f"[RESUMO RELATÓRIOS] Concluídos com sucesso: {relatorios_concluidos}")
            self._log(f"[RESUMO RELATÓRIOS] Falharam na execução: {relatorios_falharam}")
            self._log(f"[RESUMO RELATÓRIOS] Não executados: {relatorios_nao_executados}")
            if scripts_nao_executados:
                self._log("[DETALHE] Scripts não executados:")
                for nome_script, motivo in scripts_nao_executados:
                    self._log(f"[DETALHE] - {nome_script}: {motivo}")
            else:
                self._log("[DETALHE] Nenhum script ficou sem execução.")

            if processamento_completo:
                self._log("-" * 60)
                self._log("✅ PROCESSAMENTO DE TODOS OS SCRIPTS CONCLUÍDO")
                dir_trabalho = Path(self.var_dir.get())
                self._limpar_subpasta_auditoria_calculos(dir_trabalho)
                self._arquivar_arquivos_processados(dir_trabalho)
                self._processamento_ok = True
            else:
                self._processamento_ok = False

            self._log("=" * 60)
            if self.modo_automatico:
                self.btn.config(state="normal")
            else:
                self.root.after(0, lambda: self.btn.config(state="normal"))


if __name__ == "__main__":
    auto_dir = os.getenv("AERO_AUTOMACAO_DIR", "").strip()
    if auto_dir:
        root = Tk()
        root.withdraw()
        app = App(root, modo_automatico=True)
        app.var_dir.set(auto_dir)
        salvar_dir(auto_dir)
        app._inspecionar(auto_dir)

        if str(app.btn.cget("state")) != "normal":
            app._log("[AUTO] ✗ Pré-validação falhou. Processamento não iniciado.")
            root.destroy()
            sys.exit(1)

        app._executar()
        while str(app.btn.cget("state")) != "normal":
            root.update()
            time.sleep(0.2)

        rc = 0 if app._processamento_ok else 1
        root.destroy()
        sys.exit(rc)

    root = Tk()
    App(root)
    root.mainloop()
