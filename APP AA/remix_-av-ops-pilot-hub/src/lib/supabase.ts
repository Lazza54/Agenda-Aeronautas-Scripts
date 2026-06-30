import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { Flight, Document, CrewMember, LodgingInfo, OperationLog } from '../types';

// Retrieve credentials from environment variables
const metaEnv = (import.meta as any).env || {};
const envUrl = metaEnv.VITE_SUPABASE_URL || '';
const envKey = metaEnv.VITE_SUPABASE_ANON_KEY || '';

// Internal memory for dynamic key configuration via UI settings
let dynamicUrl = localStorage.getItem('supabase_dynamic_url') || '';
let dynamicKey = localStorage.getItem('supabase_dynamic_key') || '';

export function getSupabaseConfig() {
  return {
    url: dynamicUrl || envUrl,
    key: dynamicKey || envKey,
    isConfigured: !!(dynamicUrl || envUrl) && !!(dynamicKey || envKey),
    source: dynamicUrl ? 'Dynamic UI' : (envUrl ? 'Env Variables' : 'None')
  };
}

export function saveDynamicSupabaseConfig(url: string, key: string) {
  dynamicUrl = url;
  dynamicKey = key;
  localStorage.setItem('supabase_dynamic_url', url);
  localStorage.setItem('supabase_dynamic_key', key);
  
  // Re-initialize client
  supabaseInstance = initClient();
}

export function clearDynamicSupabaseConfig() {
  dynamicUrl = '';
  dynamicKey = '';
  localStorage.removeItem('supabase_dynamic_url');
  localStorage.removeItem('supabase_dynamic_key');
  supabaseInstance = initClient();
}

function initClient(): SupabaseClient | null {
  const activeUrl = dynamicUrl || envUrl;
  const activeKey = dynamicKey || envKey;
  
  if (!activeUrl || !activeKey) {
    return null;
  }
  
  try {
    return createClient(activeUrl, activeKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true
      }
    });
  } catch (err) {
    console.error('Erro ao inicializar Supabase:', err);
    return null;
  }
}

let supabaseInstance = initClient();

export function getSupabaseClient() {
  return supabaseInstance;
}

// Check subscription and membership status
export interface SubscriptionStatus {
  isPaid: boolean;
  type: 'mensal' | 'anual' | 'demo' | 'none';
  validUntil: string;
  userName: string;
  email: string;
  isRealDb?: boolean;
  dbError?: string;
}

export async function checkUserSubscription(email: string, token?: string): Promise<SubscriptionStatus> {
  const client = getSupabaseClient();
  
  // Fallback if client is not configured
  if (!client) {
    // Local fallback for quick testing
    const localUser = localStorage.getItem('mock_subscribed_user');
    if (localUser) {
      return JSON.parse(localUser);
    }
    
    // Default mock behavior for testing
    if (email.toLowerCase() === 'atrasado@avops.com') {
      return {
        isPaid: false,
        type: 'mensal',
        validUntil: '15/06/2026',
        userName: 'RICARDO LAZZARINI (BLOQUEADO)',
        email: 'atrasado@avops.com',
        isRealDb: false,
        dbError: 'Supabase não inicializado (VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY não configurados)'
      };
    }
    
    return {
      isPaid: true,
      type: 'anual',
      validUntil: '31/12/2026',
      userName: 'RICARDO LAZZARINI (DEMO)',
      email: email || 'piloto@avops.com',
      isRealDb: false,
      dbError: 'Supabase não inicializado (VITE_SUPABASE_URL e VITE_SUPABASE_ANON_KEY não configurados)'
    };
  }

  try {
    // 1. Try to fetch from 'usuarios_assinaturas' table
    const query = client
      .from('usuarios_assinaturas')
      .select('*');
      
    let result;
    if (token) {
      result = await query.eq('chave_acesso', token).maybeSingle();
    } else {
      result = await query.eq('email', email).maybeSingle();
    }
    
    if (result.error) {
      console.warn('Subscription table query issue:', result.error.message);
      return {
        isPaid: true,
        type: 'demo',
        validUntil: '2026-12-31',
        userName: email.split('@')[0].toUpperCase(),
        email: email,
        isRealDb: false,
        dbError: `Supabase retornou erro: ${result.error.message} (Código: ${result.error.code || 'N/A'})`
      };
    }

    if (!result.data) {
      return {
        isPaid: true,
        type: 'demo',
        validUntil: '2026-12-31',
        userName: email.split('@')[0].toUpperCase(),
        email: email,
        isRealDb: false,
        dbError: `Nenhum registro encontrado na tabela 'usuarios_assinaturas' para o e-mail: ${email}`
      };
    }

    const data = result.data;
    return {
      isPaid: !!data.pago,
      type: data.tipo_assinatura || 'mensal',
      validUntil: data.valido_ate || '',
      userName: data.nome_usuario || 'PILOTO AV-OPS',
      email: data.email || email,
      isRealDb: true
    };
  } catch (error: any) {
    console.error('Erro na chamada Supabase:', error);
    return {
      isPaid: true,
      type: 'demo',
      validUntil: '2026-12-31',
      userName: 'PILOTO LOCAL',
      email: email,
      isRealDb: false,
      dbError: `Exceção ao conectar: ${error.message || String(error)}`
    };
  }
}

// Fetch general system configurations / version metadata (e.g. QUARTA_VERSAO)
export interface QuartaVersaoConfig {
  versionCode: string;
  description: string;
  diariasNacionalRate: number;
  diariasInternacionalRate: number;
  updatedAt: string;
}

export async function fetchQuartaVersaoConfig(): Promise<QuartaVersaoConfig> {
  const client = getSupabaseClient();
  const defaultVal: QuartaVersaoConfig = {
    versionCode: 'v4.0.2',
    description: 'Cockpit Quarta Versão - Escala & Diárias Sincronizadas',
    diariasNacionalRate: 135,
    diariasInternacionalRate: 230,
    updatedAt: '2026-06-26'
  };

  if (!client) {
    const saved = localStorage.getItem('supabase_quarta_versao');
    return saved ? JSON.parse(saved) : defaultVal;
  }

  try {
    const { data, error } = await client
      .from('quarta_versao_config')
      .select('*')
      .order('id', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error || !data) {
      return defaultVal;
    }

    return {
      versionCode: data.versao_codigo || 'v4.0.0',
      description: data.descricao || 'Ativo via Supabase',
      diariasNacionalRate: Number(data.taxa_nacional) || 135,
      diariasInternacionalRate: Number(data.taxa_internacional) || 230,
      updatedAt: data.atualizado_em || 'Hoje'
    };
  } catch (e) {
    console.error('Erro ao ler quarta_versao_config:', e);
    return defaultVal;
  }
}

// Fetch real flights from Supabase table 'escala_voos'
export async function fetchFlightsFromSupabase(): Promise<Flight[] | null> {
  const client = getSupabaseClient();
  if (!client) return null;

  try {
    const { data, error } = await client
      .from('escala_voos')
      .select('*')
      .order('date', { ascending: true });

    if (error) {
      console.error('Erro ao ler escala_voos:', error);
      return null;
    }

    return data.map((item: any) => ({
      id: item.id_voo || item.id,
      routeFrom: item.origem || '',
      routeTo: item.destino || '',
      presentationTime: item.apresentacao || '',
      departureTime: item.partida || '',
      arrivalTime: item.chegada || '',
      date: item.data || '',
      restTime: item.repouso || '—',
      hoursDuty: item.horas_jornada || '00:00',
      hoursFlight: item.horas_voo || '00:00',
      status: item.status || 'scheduled'
    }));
  } catch (e) {
    console.error('Falha na chamada fetchFlightsFromSupabase:', e);
    return null;
  }
}

// Push flights to Supabase for easy syncing/seeding
export async function saveFlightsToSupabase(flights: Flight[]): Promise<boolean> {
  const client = getSupabaseClient();
  if (!client) return false;

  try {
    // Delete existing rows first for clean sync
    await client.from('escala_voos').delete().neq('id_voo', 'xxx');

    const payload = flights.map(f => ({
      id_voo: f.id,
      origem: f.routeFrom,
      destino: f.routeTo,
      apresentacao: f.presentationTime,
      partida: f.departureTime,
      chegada: f.arrivalTime,
      data: f.date,
      repouso: f.restTime,
      horas_jornada: f.hoursDuty,
      horas_voo: f.hoursFlight,
      status: f.status
    }));

    const { error } = await client.from('escala_voos').insert(payload);
    if (error) {
      console.error('Erro ao salvar voos no Supabase:', error);
      return false;
    }
    return true;
    return true;
  } catch (e) {
    console.error('Falha ao salvar voos:', e);
    return false;
  }
}

// --- NEW DATA LOGISTICS & LOGINS ---

export interface PilotProfile {
  nomeCompleto: string;
  cma: string;
  cht: string;
  passaporte: string;
  matricula: string;
  email: string;
}

export interface AuthResult {
  isAuthenticated: boolean;
  isPaid: boolean;
  profile?: PilotProfile;
  error?: string;
}

/**
 * Autentica o piloto usando Matrícula/RE, usuário e senha, verificando também o status do pagamento.
 */
export async function authenticatePilot(re: string, usuario: string, senha: string): Promise<AuthResult> {
  const client = getSupabaseClient();
  
  // MOCK FLOW IF SUPABASE IS NOT CONFIGURED
  if (!client) {
    if (re.toLowerCase() === 'atrasado') {
      return {
        isAuthenticated: true,
        isPaid: false,
        profile: {
          nomeCompleto: 'RICARDO LAZZARINI (MOCK ATRASADO)',
          cma: 'CMA-99221',
          cht: 'CHT-88442',
          passaporte: 'BR-A112233',
          matricula: 'atrasado',
          email: 'atrasado@avops.com'
        }
      };
    }
    
    return {
      isAuthenticated: true,
      isPaid: true,
      profile: {
        nomeCompleto: 'RICARDO LAZZARINI (MOCK DEMO)',
        cma: 'CMA-1234567',
        cht: 'CHT-9876543',
        passaporte: 'BR-FD12345',
        matricula: re || '12345',
        email: usuario || 'rilazza@gmail.com'
      }
    };
  }

  try {
    // 1. Busca perfil do piloto pela matricula (registro_empresa no banco de dados real)
    const { data: profile, error: profileErr } = await client
      .from('profiles')
      .select('*')
      .eq('registro_empresa', re)
      .maybeSingle();

    if (profileErr) {
      console.warn('Erro ao consultar tabela profiles:', profileErr.message);
    }

    if (!profile) {
      return {
        isAuthenticated: false,
        isPaid: false,
        error: `Matrícula ou perfil não encontrado no sistema. Por favor, verifique se a matrícula '${re}' existe no banco.`
      };
    }

    // 2. Verifica a mensalidade no campo paid_until
    let isPaid = true;
    if (profile.paid_until) {
      try {
        const limitDate = new Date(profile.paid_until);
        const today = new Date();
        if (limitDate.getTime() < today.getTime()) {
          isPaid = false; // Vencido
        }
      } catch (e) {
        console.warn('Erro ao analisar data paid_until:', e);
      }
    }

    const formatDate = (dateStr: string) => {
      if (!dateStr) return '—';
      const parts = dateStr.substring(0, 10).split('-');
      if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
      }
      return dateStr;
    };

    return {
      isAuthenticated: true,
      isPaid: isPaid,
      profile: {
        nomeCompleto: profile.nome_completo || 'PILOTO REAL',
        cma: formatDate(profile.cma_vencimento),
        cht: formatDate(profile.cht_validade),
        passaporte: formatDate(profile.passaporte_vencimento),
        matricula: profile.registro_empresa || re,
        email: usuario || '—'
      }
    };
  } catch (err: any) {
    console.error('Erro na autenticação via Supabase:', err);
    return {
      isAuthenticated: false,
      isPaid: false,
      error: `Exceção na chamada de banco: ${err.message || String(err)}`
    };
  }
}

/**
 * Faz download dos arquivos de diárias e escala da pasta do RE no bucket 'relatorios' do Supabase Storage.
 */
export async function fetchReportsFromStorage(re: string): Promise<{ scaleCsv: string; diariasCsv: string }> {
  const client = getSupabaseClient();
  if (!client) {
    // Retorna dados fictícios mockados em caso de falta de Supabase
    throw new Error('Supabase não configurado localmente. Configure a URL e a KEY no painel de configurações.');
  }

  // 1. Listar arquivos na pasta correspondente à matrícula
  const { data: files, error: listErr } = await client.storage.from('relatorios').list(re);
  if (listErr) {
    throw new Error(`Erro ao acessar a pasta '${re}' no bucket 'relatorios': ${listErr.message}`);
  }

  if (!files || files.length === 0) {
    throw new Error(`A pasta '${re}' está vazia ou não existe no bucket 'relatorios'. Certifique-se de que a automação fez o upload dos arquivos.`);
  }

  // 2. Encontrar o CSV de Escala (QUARTA_VERSAO ou PASSO_4) e o CSV de Diárias
  const scaleFile = files.find(f => f.name.toUpperCase().includes('QUARTA_VERSAO') || f.name.toUpperCase().includes('PASSO_4'));
  const diariasFile = files.find(f => f.name.toUpperCase().includes('DIARIAS') || f.name.toUpperCase().includes('RELATORIO_DIARIAS'));

  if (!scaleFile) {
    throw new Error(`Arquivo de Escala contendo 'QUARTA_VERSAO' não foi localizado na pasta '${re}' do storage.`);
  }
  if (!diariasFile) {
    throw new Error(`Arquivo de Diárias contendo 'DIARIAS' não foi localizado na pasta '${re}' do storage.`);
  }

  // 3. Efetuar download do CSV de escala
  const { data: scaleBlob, error: scaleDlErr } = await client.storage.from('relatorios').download(`${re}/${scaleFile.name}`);
  if (scaleDlErr || !scaleBlob) {
    throw new Error(`Erro no download do arquivo '${scaleFile.name}': ${scaleDlErr?.message || 'Arquivo vazio'}`);
  }

  // 4. Efetuar download do CSV de diárias
  const { data: diariasBlob, error: diariasDlErr } = await client.storage.from('relatorios').download(`${re}/${diariasFile.name}`);
  if (diariasDlErr || !diariasBlob) {
    throw new Error(`Erro no download do arquivo '${diariasFile.name}': ${diariasDlErr?.message || 'Arquivo vazio'}`);
  }

  const scaleCsv = await scaleBlob.text();
  const diariasCsv = await diariasBlob.text();

  return { scaleCsv, diariasCsv };
}

/**
 * Parseador genérico e flexível de CSV para converter os dados dos arquivos baixados em objetos estruturados.
 */
export function parseCSV(text: string): any[] {
  if (!text) return [];
  const lines = text.split(/\r?\n/);
  if (lines.length === 0) return [];

  const firstLine = lines[0];
  const separator = firstLine.includes(';') ? ';' : ',';

  const headers = firstLine.split(separator).map(h => h.trim().replace(/^["']|["']$/g, ''));
  const results: any[] = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const row: string[] = [];
    let insideQuotes = false;
    let currentCell = '';

    for (let charIdx = 0; charIdx < line.length; charIdx++) {
      const char = line[charIdx];
      if (char === '"') {
        insideQuotes = !insideQuotes;
      } else if (char === separator && !insideQuotes) {
        row.push(currentCell.trim().replace(/^["']|["']$/g, ''));
        currentCell = '';
      } else {
        currentCell += char;
      }
    }
    row.push(currentCell.trim().replace(/^["']|["']$/g, ''));

    if (row.length >= headers.length) {
      const obj: any = {};
      headers.forEach((header, index) => {
        if (header) {
          obj[header] = row[index] || '';
        }
      });
      results.push(obj);
    }
  }
  return results;
}


// Generator for Supabase SQL schema so the user can easily copy and paste
export function getSupabaseSQLScript(): string {
  return `-- SCRIPT DE CRIAÇÃO DE TABELAS PARA O COCKPIT AV-OPS (SUPABASE)
-- Copie e execute este script no SQL Editor do seu projeto Supabase

-- 1. Tabela de controle de assinaturas e acessos dos pilotos
CREATE TABLE IF NOT EXISTS usuarios_assinaturas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    nome_usuario VARCHAR(255) NOT NULL,
    chave_acesso VARCHAR(50) UNIQUE,
    pago BOOLEAN DEFAULT TRUE,
    tipo_assinatura VARCHAR(20) DEFAULT 'mensal', -- 'mensal', 'anual'
    valido_ate DATE DEFAULT (CURRENT_DATE + INTERVAL '1 year'),
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Tabela de configuração global (QUARTA_VERSAO e taxas de diárias)
CREATE TABLE IF NOT EXISTS quarta_versao_config (
    id SERIAL PRIMARY KEY,
    versao_codigo VARCHAR(20) DEFAULT 'v4.0.2',
    descricao TEXT DEFAULT 'Painel AV-OPS Ativo v4',
    taxa_nacional NUMERIC(10, 2) DEFAULT 135.00,
    taxa_internacional NUMERIC(10, 2) DEFAULT 230.00,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Tabela de escalas de voos dos pilotos
CREATE TABLE IF NOT EXISTS escala_voos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    id_voo VARCHAR(50) UNIQUE NOT NULL, -- e.g., AD4372
    origem VARCHAR(10) NOT NULL,
    destino VARCHAR(10) NOT NULL,
    apresentacao VARCHAR(10),
    partida VARCHAR(10),
    chegada VARCHAR(10),
    data VARCHAR(20),
    repouso VARCHAR(15) DEFAULT '—',
    horas_jornada VARCHAR(10),
    horas_voo VARCHAR(10),
    status VARCHAR(20) DEFAULT 'scheduled', -- 'scheduled', 'completed', 'active'
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- INSERÇÃO DE DADOS DE TESTE INICIAIS
INSERT INTO usuarios_assinaturas (email, nome_usuario, chave_acesso, pago, tipo_assinatura, valido_ate)
VALUES 
('rilazza@gmail.com', 'RICARDO LAZZARINI', 'AV-OPS-2026-OK', TRUE, 'anual', '2027-12-31'),
('atrasado@avops.com', 'RICARDO LAZZARINI (BLOQUEADO)', 'AV-OPS-BLOCKED', FALSE, 'mensal', '2026-06-01')
ON CONFLICT (email) DO NOTHING;

INSERT INTO quarta_versao_config (versao_codigo, descricao, taxa_nacional, taxa_internacional)
VALUES ('v4.0.2', 'Quarta Versão Integrada Supabase', 135.00, 230.00);

INSERT INTO escala_voos (id_voo, origem, destino, apresentacao, partida, chegada, data, repouso, horas_jornada, horas_voo, status)
VALUES 
('AD4372', 'VCP', 'SSA', '22:40', '23:40', '02:00', '29/08/2021', '—', '07:05', '04:45', 'completed'),
('AD4027', 'SSA', 'VCP', '22:40', '02:50', '05:15', '30/08/2021', '12:45', '07:05', '04:45', 'completed'),
('AD2291', 'VCP', 'GIG', '08:15', '09:20', '10:30', '31/08/2021', '—', '03:15', '01:10', 'scheduled')
ON CONFLICT (id_voo) DO NOTHING;
`;
}
