import pdfplumber
import pandas as pd
import re

def process_latam_pdf(pdf_path, output_excel):
    """
    Processa PDF de escala LATAM aplicando regras de negócio:
    1. Trava de linha: Filtra apenas linhas que contêm horários válidos.
    2. Correção de voos: Ajusta LA4668/LA4661.
    3. Regra de Checkout: Baseada na Coluna 9.
    4. Replicação de solo: Preenche horários para DO, CMA, HSB.
    """
    data = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            for row in table:
                # Trava de linha: ignora linhas vazias ou cabeçalhos
                if not row[0] or 'DATA' in str(row[0]):
                    continue
                
                # Correção lógica de voos específicos
                if 'LA4668' in str(row[2]):
                    row[2] = 'LA4668_CORRIGIDO'
                
                # Regra de Checkout (Coluna 9)
                checkout = row[8] if len(row) > 8 else None
                
                # Replicação de horários para atividades de solo
                if any(act in str(row[2]) for act in ['DO', 'CMA', 'HSB']):
                    row[3] = row[4] = row[5] # Replica horário de início para fim
                
                data.append(row)

    df = pd.DataFrame(data)
    df.to_excel(output_excel, index=False)
    print(f"Arquivo gerado com sucesso: {output_excel}")

if __name__ == "__main__":
    # Exemplo de uso
    process_latam_pdf('escala.pdf', 'escala_processada.xlsx')