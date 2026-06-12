#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de conexão com Supabase para buscar dados de aeronautas.
"""

import os
from dataclasses import dataclass
from typing import Optional

# Tente usar as variáveis de ambiente ou valores padrão
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gjthsykuqbimitpxudbz.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdqdGhzeWt1cWJpbWl0cHh1ZGJ6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDA2NjI1MCwiZXhwIjoyMDY5NjQyMjUwfQ.EhJ4fLk1At81Tvcwpfs_hcACts-R8r4qvZ-1Hos6YXs")


@dataclass
class ConfigSupabase:
    """Configuração de conexão com Supabase."""
    url: str
    key: str
    tabela_associados: Optional[str] = "associados"


def obter_config() -> ConfigSupabase:
    """Obtém configuração do Supabase de variáveis de ambiente."""
    url = os.environ.get("SUPABASE_URL", SUPABASE_URL)
    key = os.environ.get("SUPABASE_KEY", SUPABASE_KEY)
    tabela_assoc = os.environ.get("SUPABASE_TABELA_ASSOCIADOS", "associados")
    
    if not url or url == "https://seu-projeto.supabase.co":
        raise ValueError(
            "SUPABASE_URL não configurado. "
            "Configure as variáveis de ambiente SUPABASE_URL e SUPABASE_KEY."
        )
    
    if not key or key == "sua-chave-publica-ou-service-role":
        raise ValueError(
            "SUPABASE_KEY não configurado. "
            "Configure as variáveis de ambiente SUPABASE_URL e SUPABASE_KEY."
        )
    
    return ConfigSupabase(url=url, key=key, tabela_associados=tabela_assoc)


def criar_cliente(config: ConfigSupabase):
    """Cria cliente Supabase usando supabase-py."""
    from supabase import create_client
    
    cliente = create_client(config.url, config.key)
    return cliente


def chave_parece_publica(key: str) -> bool:
    """Verifica se a chave é pública (anon/public) em vez de service_role."""
    # Chaves públicas geralmente são mais longas e contêm "_"
    # Chaves service_role geralmente começam com "eyJ"
    # Esta é uma heurística simples
    if key.startswith("eyJ"):
        return False  # Parece JWT (service role)
    return True  # Assume que é anon/public
