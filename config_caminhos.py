import os
import sys
from pathlib import Path

# Detecta se estamos no Windows ou Linux e ajusta o diretório base
if os.name == 'nt':
    BASE_DRIVE = "R:"
else:
    BASE_DRIVE = "/run/media/ricardo/RAID"

# Caminhos base centrais
BASE_AERONAUTAS_PATH = Path(f"{BASE_DRIVE}/SPECTRUM_SYSTEM/Aeronautas")
BASE_COMMON_FILES_PATH = Path(f"{BASE_DRIVE}/SPECTRUM_SYSTEM/Aeronautas/Documentos_Comuns/Arquivos_Diversos")
BASE_OFFICIAL_DOCS_PATH = Path(f"{BASE_DRIVE}/SPECTRUM_SYSTEM/Aeronautas/Documentos_Comuns/Documentacao_Oficial")
BASE_LEGISLACAO_PATH = Path(f"{BASE_DRIVE}/SPECTRUM_SYSTEM/Aeronautas/Documentos_Comuns/Legislacao_Aeronautica")

# Adiciona o diretório atual ao sys.path para garantir que scripts isolados encontrem esse arquivo
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)
