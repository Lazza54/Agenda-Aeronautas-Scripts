import sys, os, re, importlib.util
os.environ['AERO_ESCALA_PDF'] = sys.argv[1]
spec = importlib.util.spec_from_file_location('crew', 'c:/Users/rilaz/Agenda Aeronautas Scripts/IMPORTA ESCALA PDF LATAM CREWTOPIA PASSO 1.py')
crew = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crew)

import ast, inspect
source = inspect.getsource(crew.extrair_texto_pdf)
source = source.replace(
    r"m = re.search(r'^(LA\s*\d{4}|OFT_J|LOFT_J)$', w['text'].replace('\ue539', '').replace('\ue80c', '').strip())",
    r"m = re.search(r'^(LA\s*\d{4}|OFT_J|LOFT_J|DO|ASB|HSB|OFF|DOF|DR|CMA)$', w['text'].replace('\ue539', '').replace('\ue80c', '').strip())"
)
exec(source, globals())
linhas = extrair_texto_pdf(sys.argv[1])

source2 = inspect.getsource(crew.parse_crewtopia)
source2 = re.sub(
    r"(?s)if act == 'DO':\s*m_prev.*?temp_leg = \{\}",
    r"",
    source2
)
exec(source2, globals())

dados = parse_crewtopia(linhas, sys.argv[1])
for d in dados:
    if d.get('Start') and (d['Start'].startswith('21/') or d['Start'].startswith('22/') or d['Start'].startswith('23/') or d['Start'].startswith('24/') or d['Start'].startswith('25/')):
        print(d)
