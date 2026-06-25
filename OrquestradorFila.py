#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestrador de Fila de Processamento de Escalas.
Busca tarefas pendentes no Supabase, executa o pipeline headless e faz upload dos relatórios gerados.
"""

import os
import sys
import time
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path
from SUPABASE_CONEXAO_DEV import obter_config, criar_cliente

# Garante que a saída do console utilize UTF-8 para suportar caracteres especiais (como emojis de check e erro)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def process_job(supabase, job):
    job_id = job["id"]
    file_name = job["file_name"]
    storage_path = job["storage_path"]
    empresa = job["empresa"]
    nome_completo = job["nome_completo"]
    registro_empresa = job["registro_empresa"]

    import re
    
    # Se os metadados são None ou se o arquivo é pendente, tenta localizá-los a partir do arquivo definitivo no storage
    if not nome_completo or not registro_empresa or "pending_" in file_name:
        log("[ORQUESTRADOR] Metadados incompletos no job. Buscando arquivo definitivo no storage...")
        parts = storage_path.split("/")
        if "_pending" in parts:
            idx = parts.index("_pending")
            dir_pai = "/".join(parts[:idx])
        else:
            dir_pai = "/".join(parts[:-1])
            
        try:
            itens = supabase.storage.from_(job["bucket"]).list(path=dir_pai)
            pdfs = []
            for item in itens:
                name = item.get("name")
                if name and name.lower().endswith(".pdf") and not name.startswith("pending_") and "SUMARIO" not in name.upper():
                    updated_at = item.get("updated_at") or ""
                    pdfs.append((updated_at, name))
            
            if pdfs:
                pdfs.sort(key=lambda x: x[0], reverse=True)
                pdf_escolhido = pdfs[0][1]
                storage_path = f"{dir_pai}/{pdf_escolhido}"
                file_name = pdf_escolhido
                log(f"[ORQUESTRADOR] ✓ Arquivo definitivo localizado no storage: {storage_path}")
                
                # Extrai os metadados a partir do nome do arquivo
                base_stem = Path(file_name).stem
                
                # Empresa
                for emp in ("LATAM", "AZUL", "SABRE", "SIMPL"):
                    if emp in base_stem.upper():
                        empresa = emp
                        break
                if not empresa:
                    empresa = "EMPRESA"
                    
                # RE
                m_re = re.search(r"_[A-Z]{3,4}__+(\d+)_", base_stem, flags=re.IGNORECASE)
                if m_re:
                    registro_empresa = m_re.group(1)
                    
                # Nome Completo
                m_nome = re.search(r"escala_[pe]_(.+?)_(?:[A-Z]{3,4})__", base_stem, flags=re.IGNORECASE)
                if m_nome:
                    nome_completo = m_nome.group(1).replace("_", " ").strip().title()
                else:
                    nome_completo = "AERONAUTA"
            else:
                log("[ORQUESTRADOR] ⚠️ Nenhum PDF definitivo foi localizado no storage.")
        except Exception as e_scan:
            log(f"[ORQUESTRADOR] ⚠️ Falha ao escanear a pasta no storage: {e_scan}")

    log(f"\n--- INICIANDO TRABALHO: Job {job_id} ---")
    log(f"Aeronauta: {nome_completo} | Registro: {registro_empresa} | Empresa: {empresa}")
    log(f"Arquivo de origem no storage: {storage_path}")

    # 1. Bloqueia o Job (status = 'processando')
    try:
        supabase.table("upload_jobs").update({
            "status": "processando",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "locked_at": datetime.now(timezone.utc).isoformat(),
            "locked_by": "local_server_orchestrator"
        }).eq("id", job_id).execute()
        log("✓ Status da tarefa updated para 'processando'.")
    except Exception as e:
        log(f"❌ Falha ao dar lock no job {job_id}: {e}")
        return

    try:
        # 2. Cria as pastas locais
        base_local_dir = "R:/SPECTRUM_SYSTEM/Aeronautas"
        
        # Sanitização simples para caminhos válidos no Windows
        def clean_path_segment(s: str) -> str:
            return "".join([c for c in str(s) if c.isalnum() or c in " _-"]).strip()
        
        clean_empresa = clean_path_segment(empresa) or "EMPRESA"
        clean_nome = clean_path_segment(nome_completo) or "AERONAUTA"
        
        aeronauta_dir = os.path.join(base_local_dir, clean_empresa, clean_nome)
        auditoria_dir = os.path.join(aeronauta_dir, "Auditoria_Calculos")
        
        log(f"Criando diretório do aeronauta: {auditoria_dir}")
        os.makedirs(auditoria_dir, exist_ok=True)

        # Limpa arquivos antigos da pasta de auditoria para evitar erro de múltiplos PDFs
        for arq_antigo in Path(auditoria_dir).glob("*"):
            if arq_antigo.is_file() and arq_antigo.suffix.lower() in (".pdf", ".csv", ".txt"):
                try:
                    arq_antigo.unlink()
                except Exception:
                    pass

        local_pdf_path = os.path.join(auditoria_dir, file_name)

        # 3. Download do PDF da escala original
        log(f"Baixando escala para {local_pdf_path}...")
        with open(local_pdf_path, 'wb') as f:
            res = supabase.storage.from_(job["bucket"]).download(storage_path)
            f.write(res)
        log("✓ Escala original salva localmente com sucesso.")

        # 4. Executa RODA SCRIPTS COMPLETOS.py em modo automático/headless
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_roda = os.path.join(script_dir, "RODA SCRIPTS COMPLETOS.py")
        
        # Detecta se há um ambiente virtual (.venv) para executar os subprocessos
        python_exec = sys.executable
        venv_dir = Path(script_dir) / ".venv"
        if os.name == "nt":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"
            
        if venv_python.exists():
            python_exec = str(venv_python.resolve())
            log(f"Usando interpretador Python do ambiente virtual: {python_exec}")
        else:
            log(f"Ambiente virtual não localizado em {venv_dir}. Usando interpretador atual: {python_exec}")

        log("Disparando RODA SCRIPTS COMPLETOS.py...")
        env = os.environ.copy()
        env["AERO_AUTOMACAO_DIR"] = auditoria_dir
        env["AERO_NO_POPUP"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        # Chama o subprocesso usando o interpretador do ambiente virtual se disponível
        proc_roda = subprocess.run(
            [python_exec, script_roda],
            env=env,
            cwd=script_dir,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )

        log(f"RODA encerrado com retorno: {proc_roda.returncode}")
        if proc_roda.stdout:
            print("--- RODA OUTPUT ---")
            print(proc_roda.stdout)
        if proc_roda.stderr:
            print("--- RODA STDERR ---")
            print(proc_roda.stderr)

        if proc_roda.returncode != 0:
            raise RuntimeError(f"O script RODA SCRIPTS COMPLETOS.py falhou (código {proc_roda.returncode}).")

        # 5. Pós-processamento e Uploads (Integrados ao RODA SCRIPTS COMPLETOS.py)
        log("[ORQUESTRADOR] Renomeação, envio de e-mails e uploads ao Supabase gerenciados internamente pelo script de processamento.")

        # 7. Finaliza a tarefa com sucesso
        supabase.table("upload_jobs").update({
            "status": "concluido",
            "finished_at": datetime.utcnow().isoformat(),
            "error_message": None,
            "error_code": None
        }).eq("id", job_id).execute()
        log(f"✓ Job {job_id} concluído com sucesso total!")

    except Exception as e:
        err_msg = traceback.format_exc()
        log(f"❌ ERRO ao processar Job {job_id}:\n{err_msg}")
        try:
            supabase.table("upload_jobs").update({
                "status": "erro",
                "error_message": err_msg,
                "finished_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", job_id).execute()
            log("✓ Status de erro gravado na fila.")
        except Exception as update_err:
            log(f"Falha crítica ao gravar status de erro no banco: {update_err}")

def main():
    log("=== ORQUESTRADOR DE FILA SUPABASE INICIADO ===")
    try:
        config = obter_config()
        supabase = criar_cliente(config)
        log("✓ Conexão com Supabase restabelecida.")
    except Exception as e:
        log(f"❌ Falha ao conectar ao Supabase: {e}")
        sys.exit(1)

    log("Monitorando fila de tarefas pendentes...")
    while True:
        try:
            res = (supabase.table("upload_jobs")
                   .select("*")
                   .eq("status", "pendente")
                   .order("created_at")
                   .limit(1)
                   .execute())
            
            if res.data:
                job = res.data[0]
                process_job(supabase, job)
            else:
                # Nenhuma tarefa pendente, dorme 15 segundos
                time.sleep(15)
                
        except KeyboardInterrupt:
            log("Processo encerrado pelo usuário via teclado.")
            break
        except Exception as e:
            log(f"Erro no loop principal do orquestrador: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
