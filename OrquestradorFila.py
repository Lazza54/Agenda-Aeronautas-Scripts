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
from datetime import datetime
from pathlib import Path
from SUPABASE_CONEXAO_DEV import obter_config, criar_cliente

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def process_job(supabase, job):
    job_id = job["id"]
    file_name = job["file_name"]
    storage_path = job["storage_path"]
    empresa = job["empresa"]
    nome_completo = job["nome_completo"]
    registro_empresa = job["registro_empresa"]

    log(f"\n--- INICIANDO TRABALHO: Job {job_id} ---")
    log(f"Aeronauta: {nome_completo} | Registro: {registro_empresa} | Empresa: {empresa}")
    log(f"Arquivo de origem no storage: {storage_path}")

    # 1. Bloqueia o Job (status = 'processando')
    try:
        supabase.table("upload_jobs").update({
            "status": "processando",
            "started_at": datetime.utcnow().isoformat(),
            "locked_at": datetime.utcnow().isoformat(),
            "locked_by": "local_server_orchestrator"
        }).eq("id", job_id).execute()
        log("✓ Status da tarefa atualizado para 'processando'.")
    except Exception as e:
        log(f"❌ Falha ao dar lock no job {job_id}: {e}")
        return

    try:
        # 2. Cria as pastas locais
        base_local_dir = "G:/SPECTRUM_SYSTEM/Aeronautas"
        
        # Sanitização simples para caminhos válidos no Windows
        def clean_path_segment(s: str) -> str:
            return "".join([c for c in str(s) if c.isalnum() or c in " _-"]).strip()
        
        clean_empresa = clean_path_segment(empresa) or "EMPRESA"
        clean_nome = clean_path_segment(nome_completo) or "AERONAUTA"
        
        aeronauta_dir = os.path.join(base_local_dir, clean_empresa, clean_nome)
        auditoria_dir = os.path.join(aeronauta_dir, "Auditoria_Calculos")
        
        log(f"Criando diretório do aeronauta: {auditoria_dir}")
        os.makedirs(auditoria_dir, exist_ok=True)

        local_pdf_path = os.path.join(auditoria_dir, file_name)

        # 3. Download do PDF da escala original
        log(f"Baixando escala para {local_pdf_path}...")
        with open(local_pdf_path, 'wb') as f:
            res = supabase.storage.from_(job["bucket"]).download(storage_path)
            f.write(res)
        log("✓ Escala original salva localmente.")

        # 4. Executa RODA SCRIPTS COMPLETOS.py em modo automático/headless
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_roda = os.path.join(script_dir, "RODA SCRIPTS COMPLETOS.py")
        
        log("Disparando RODA SCRIPTS COMPLETOS.py...")
        env = os.environ.copy()
        env["AERO_AUTOMACAO_DIR"] = auditoria_dir
        env["AERO_NO_POPUP"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        # Chama o subprocesso
        proc_roda = subprocess.run(
            [sys.executable, script_roda],
            env=env,
            cwd=script_dir,
            capture_output=True,
            text=True
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

        # 5. Executa Orquestrado 1.py para renomear PDFs e rodar pós-processamento
        script_orq = os.path.join(script_dir, "Orquestrado 1.py")
        log("Disparando Orquestrado 1.py...")
        
        proc_orq = subprocess.run(
            [sys.executable, script_orq],
            env=env, # Passa AERO_AUTOMACAO_DIR
            cwd=script_dir,
            capture_output=True,
            text=True
        )

        log(f"Orquestrado 1 encerrado com retorno: {proc_orq.returncode}")
        if proc_orq.stdout:
            print("--- ORQUESTRADO Output ---")
            print(proc_orq.stdout)
        if proc_orq.stderr:
            print("--- ORQUESTRADO Stderr ---")
            print(proc_orq.stderr)

        if proc_orq.returncode != 0:
            raise RuntimeError(f"O pós-processamento do Orquestrado 1.py falhou (código {proc_orq.returncode}).")

        # 6. Escaneia a pasta e faz upload dos PDFs resultantes de volta ao Supabase
        log("Realizando varredura para upload de relatórios gerados...")
        relatorios_bucket = "relatorios"
        re_prefix = str(registro_empresa).strip()
        
        relatorios_gerados = list(Path(auditoria_dir).glob("*.pdf"))
        uploaded_count = 0

        for r_file in relatorios_gerados:
            # Ignora a escala original
            if r_file.name == file_name:
                continue
            
            dest_path = f"{re_prefix}/{r_file.name}"
            log(f"Subindo {r_file.name} -> relatorios/{dest_path}...")
            
            with open(r_file, 'rb') as f:
                file_bytes = f.read()
                
            supabase.storage.from_(relatorios_bucket).upload(
                path=dest_path,
                file=file_bytes,
                file_options={"content-type": "application/pdf", "x-upsert": "true"}
            )
            uploaded_count += 1

        log(f"✓ Upload concluído. {uploaded_count} relatórios enviados com sucesso.")

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
                "finished_at": datetime.utcnow().isoformat()
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
            # Busca o primeiro job pendente ordenado pela criação
            res = supabase.table("upload_jobs").select("*").eq("status", "pendente").order("created_at").limit(1).execute()
            
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
