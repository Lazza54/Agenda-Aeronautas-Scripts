import sys
import os
os.environ['AERO_ESCALA_PDF'] = sys.argv[1]
import importlib.util

spec = importlib.util.spec_from_file_location('crew', 'c:/Users/rilaz/Agenda Aeronautas Scripts/IMPORTA ESCALA PDF LATAM CREWTOPIA PASSO 1.py')
crew = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crew)

linhas = crew.extrair_texto_pdf(sys.argv[1])
dados = crew.parse_crewtopia(linhas, sys.argv[1])

for i in range(1, len(dados)):
    prev = dados[i-1]
    curr = dados[i]
    if prev['Activity'] == 'ASB':
        print("ASB:", prev)
        print("Next:", curr)
