import csv
import os
import smtplib
import ssl
import subprocess
import sys
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

def main():
    # Garante que o diretório de trabalho seja a pasta do script
    base_dir = Path(__file__).parent.resolve()
    os.chdir(base_dir)

    # ===== 1. INÍCIO DO MESTRE =====
    print('=== INICIANDO: RODA SCRIPTS COMPLETOS ===')
    script_roda = base_dir / 'RODA SCRIPTS COMPLETOS.py'
    
    if not script_roda.exists():
        print(f"ERRO: Arquivo '{script_roda.name}' não encontrado em {base_dir}")
        return

    # Executa o mestre e aguarda o fechamento da janela (somente se não estiver em automação de fila)
    if not os.environ.get("AERO_AUTOMACAO_DIR"):
        subprocess.run([sys.executable, str(script_roda)], check=True, cwd=base_dir)
    else:
        print("Ignorando execução secundária do RODA SCRIPTS COMPLETOS.py (já executado pelo orquestrador da fila).")
    
    # ===== 2. TÉRMINO DO MESTRE =====
    print('=== FINALIZADO: RODA SCRIPTS COMPLETOS ===')

    # ===== 3. INÍCIO DO ORQUESTRADOR =====
    print('=== INICIANDO: PÓS-PROCESSAMENTO (ORQUESTRADO 1) ===')

    # ===== 4. BUSCA EXAUSTIVA PELO CSV =====
    print("Buscando QUARTA_VERSAO.csv...")
    search_dir = Path(os.environ.get("AERO_AUTOMACAO_DIR", str(base_dir)))
    csv_path = None
    for f in search_dir.rglob("QUARTA_VERSAO.csv"):
        csv_path = f
        break

    if not csv_path:
        print("!!! ERRO: Arquivo 'QUARTA_VERSAO.csv' não localizado.")
        print("Certifique-se de que o processamento no RODA chegou até a última versão.")
        return

    print(f"Arquivo localizado em: {csv_path}")
    csv_dir = csv_path.parent
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Lê dados do auditado
    try:
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            row = next(reader)
    except Exception as e:
        print(f"!!! ERRO ao ler o CSV: {e}")
        return

    auditado = {
        'nome': row.get('nome_completo', 'Auditado').strip(),
        'registro': row.get('registro', '').strip(),
        'email': row.get('email', '').strip(),
        'periodo': row.get('periodo', '').strip()
    }

    # ===== 5. RENOMEAÇÃO (13 ARQUIVOS) =====
    print(f"Renomeando arquivos para: {auditado['nome']}")
    relatorio_path = None

    # Varre apenas a pasta onde o CSV foi encontrado
    for file in csv_dir.glob("*.pdf"):
        nome_up = file.name.upper()
        novo_nome = None

        # Mapeamento de termos para extrair o tipo de sumário de forma padronizada
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
            novo_nome = f"{auditado['nome']}_{auditado['registro']}_SUMARIO_HORAS_{tipo_sumario}_{auditado['periodo']}_{timestamp}.pdf"
        elif "RELATORIO_CONFORMIDADE" in nome_up:
            novo_nome = f"{auditado['nome']}_{auditado['registro']}_RELATORIO_CONFORMIDADE_{auditado['periodo']}_{timestamp}.pdf"
            relatorio_path = csv_dir / novo_nome.replace(" ", "_")
        elif "BOOK" in nome_up:
            novo_nome = f"Book_{auditado['nome']}_{auditado['registro']}_{auditado['periodo']}_{timestamp}.pdf"

        if novo_nome:
            novo_path = csv_dir / novo_nome.replace(" ", "_")
            file.rename(novo_path)
            print(f" -> {novo_nome}")

    # ===== 6. ENVIO DE E-MAIL (ZOHO) =====
    if relatorio_path and auditado['email']:
        print(f"Enviando e-mail para: {auditado['email']}")
        try:
            msg = MIMEMultipart()
            msg['From'] = 'contato@spectrum-system.com'
            msg['To'] = auditado['email']
            msg['Subject'] = f"Relatório de Conformidade - {auditado['nome']}"

            corpo = f"Olá {auditado['nome']}, Segue o relatório de Conformidades da escala enviada por você."
            msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

            with open(relatorio_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{relatorio_path.name}"')
            msg.attach(part)

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL('smtppro.zoho.com', 465, context=context) as server:
                server.login('contato@spectrum-system.com', 'zCFYkvjP4QY6')
                server.send_message(msg)
            print("✓ E-mail enviado com sucesso!")
        except Exception as e:
            print(f"!!! FALHA no e-mail: {e}")

    # ===== 7. TÉRMINO =====
    print('=== FINALIZADO: PÓS-PROCESSAMENTO (ORQUESTRADO 1) ===')

if __name__ == '__main__':
    main()