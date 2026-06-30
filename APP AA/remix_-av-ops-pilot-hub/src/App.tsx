import React, { useState, useEffect } from 'react';
import {
  TabType,
  Flight,
  Document,
  CrewMember,
  LodgingInfo,
  OperationLog
} from './types';
import {
  INITIAL_FLIGHTS,
  INITIAL_DOCUMENTS,
  INITIAL_CREW,
  INITIAL_LODGING,
  INITIAL_OPERATION_LOGS
} from './data';
import IdentityCard from './components/IdentityCard';
import DocumentList from './components/DocumentList';
import FlightSchedule from './components/FlightSchedule';
import FlightDetails from './components/FlightDetails';
import ReportsPanel from './components/ReportsPanel';
import {
  Plane,
  Calendar,
  FileText,
  User,
  Bell,
  CheckCircle2,
  Settings,
  Shield,
  Clock,
  Briefcase,
  HelpCircle,
  RefreshCw,
  Lock,
  Unlock,
  AlertTriangle,
  Database,
  Terminal,
  Key,
  LogOut,
  Copy,
  Check
} from 'lucide-react';
import {
  getSupabaseConfig,
  saveDynamicSupabaseConfig,
  clearDynamicSupabaseConfig,
  checkUserSubscription,
  fetchQuartaVersaoConfig,
  fetchFlightsFromSupabase,
  saveFlightsToSupabase,
  getSupabaseSQLScript,
  SubscriptionStatus,
  QuartaVersaoConfig
} from './lib/supabase';

export default function App() {
  // --- Supabase & Subscription / Login State ---
  const [sessionUser, setSessionUser] = useState<SubscriptionStatus | null>(() => {
    const saved = localStorage.getItem('av_ops_session_user');
    return saved ? JSON.parse(saved) : null;
  });
  
  const [loginEmail, setLoginEmail] = useState('rilazza@gmail.com');
  const [loginToken, setLoginToken] = useState('AV-OPS-2026-OK');
  const [isCheckingSub, setIsCheckingSub] = useState(false);
  const [loginError, setLoginError] = useState('');
  
  const [quartaVersao, setQuartaVersao] = useState<QuartaVersaoConfig>({
    versionCode: 'v4.0.2',
    description: 'Cockpit Quarta Versão - Escala & Diárias Sincronizadas',
    diariasNacionalRate: 135,
    diariasInternacionalRate: 230,
    updatedAt: '2026-06-26'
  });

  const [supabaseConfig, setSupabaseConfig] = useState(getSupabaseConfig());
  const [supabaseSyncing, setSupabaseSyncing] = useState(false);
  const [supabaseSyncMessage, setSupabaseSyncMessage] = useState('');
  const [copiedSql, setCopiedSql] = useState(false);

  // Dynamic credentials input states
  const [inputUrl, setInputUrl] = useState(supabaseConfig.url);
  const [inputKey, setInputKey] = useState(supabaseConfig.key);

  // --- Persistent State Configuration ---
  const [activeTab, setActiveTab] = useState<TabType>('profile');
  
  const [flights, setFlights] = useState<Flight[]>(() => {
    const saved = localStorage.getItem('av_ops_flights');
    return saved ? JSON.parse(saved) : INITIAL_FLIGHTS;
  });

  const [documents, setDocuments] = useState<Document[]>(() => {
    const saved = localStorage.getItem('av_ops_documents');
    return saved ? JSON.parse(saved) : INITIAL_DOCUMENTS;
  });

  const [crew, setCrew] = useState<CrewMember[]>(() => {
    const saved = localStorage.getItem('av_ops_crew');
    return saved ? JSON.parse(saved) : INITIAL_CREW;
  });

  const [lodging, setLodging] = useState<LodgingInfo>(() => {
    const saved = localStorage.getItem('av_ops_lodging');
    return saved ? JSON.parse(saved) : INITIAL_LODGING;
  });

  const [operationLog, setOperationLog] = useState<OperationLog>(() => {
    const saved = localStorage.getItem('av_ops_operation_log');
    return saved ? JSON.parse(saved) : INITIAL_OPERATION_LOGS[0];
  });

  const [pilotDetails, setPilotDetails] = useState(() => {
    const saved = localStorage.getItem('av_ops_pilot');
    return saved ? JSON.parse(saved) : {
      name: 'CAPTAIN J. MILLER',
      rank: 'CDR',
      idCode: '8824-H6-LX',
      dutyHours: '12,450.5 FT',
      isActive: true
    };
  });

  const [selectedFlight, setSelectedFlight] = useState<Flight | null>(null);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState([
    { id: 1, text: 'I-94 Visa expira em 45 dias. Renove em breve.', date: 'Hoje', unread: true },
    { id: 2, text: 'Escala atualizada pelo dpto. de operações.', date: 'Ontem', unread: false },
    { id: 3, text: 'Seu Class 1 Medical foi homologado pela ANAC.', date: '3 dias atrás', unread: false }
  ]);

  // Sync with Supabase on session validation or config changes
  const loadSupabaseData = async () => {
    try {
      const configData = await fetchQuartaVersaoConfig();
      setQuartaVersao(configData);

      const dbFlights = await fetchFlightsFromSupabase();
      if (dbFlights && dbFlights.length > 0) {
        setFlights(dbFlights);
        setSupabaseSyncMessage('Escala de voos sincronizada ao vivo com o Supabase!');
      }
    } catch (e) {
      console.warn('Erro ao carregar dados do Supabase:', e);
    }
  };

  useEffect(() => {
    if (sessionUser) {
      loadSupabaseData();
    }
  }, [sessionUser, supabaseConfig.isConfigured]);

  // Sync to local storage
  useEffect(() => {
    localStorage.setItem('av_ops_flights', JSON.stringify(flights));
  }, [flights]);

  useEffect(() => {
    localStorage.setItem('av_ops_documents', JSON.stringify(documents));
  }, [documents]);

  useEffect(() => {
    localStorage.setItem('av_ops_crew', JSON.stringify(crew));
  }, [crew]);

  useEffect(() => {
    localStorage.setItem('av_ops_lodging', JSON.stringify(lodging));
  }, [lodging]);

  useEffect(() => {
    localStorage.setItem('av_ops_operation_log', JSON.stringify(operationLog));
  }, [operationLog]);

  useEffect(() => {
    localStorage.setItem('av_ops_pilot', JSON.stringify(pilotDetails));
  }, [pilotDetails]);

  // --- Handlers ---
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail && !loginToken) {
      setLoginError('Por favor, informe seu E-mail ou Chave de Acesso do Webapp.');
      return;
    }
    
    setIsCheckingSub(true);
    setLoginError('');
    
    try {
      const status = await checkUserSubscription(loginEmail, loginToken);
      
      if (!status.isPaid) {
        setLoginError('MENSALIDADE/ANUIDADE EM ATRASO: O acesso ao painel GL-COCKPIT v3.5 está bloqueado até a regularização do plano no Webapp principal.');
        setIsCheckingSub(false);
        return;
      }
      
      // Update pilot name and status based on webapp info
      setPilotDetails(prev => ({
        ...prev,
        name: status.userName || prev.name,
        isActive: true
      }));
      
      setSessionUser(status);
      localStorage.setItem('av_ops_session_user', JSON.stringify(status));
      setLoginError('');
    } catch (err) {
      setLoginError('Falha de conexão com o Webapp/Supabase. Verifique os dados ou tente novamente.');
    } finally {
      setIsCheckingSub(false);
    }
  };

  const handleLogout = () => {
    setSessionUser(null);
    localStorage.removeItem('av_ops_session_user');
  };

  const handleToggleMockPayment = () => {
    // We can simulate an active paid user for the tester
    const mockUser: SubscriptionStatus = {
      isPaid: true,
      type: 'demo',
      validUntil: '31/12/2026',
      userName: 'RICARDO LAZZARINI (LIBERADO)',
      email: loginEmail || 'rilazza@gmail.com'
    };
    setPilotDetails(prev => ({
      ...prev,
      name: 'RICARDO LAZZARINI (LIBERADO)',
      isActive: true
    }));
    setSessionUser(mockUser);
    localStorage.setItem('av_ops_session_user', JSON.stringify(mockUser));
    setLoginError('');
  };

  const handleUpdateConfig = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputUrl || !inputKey) {
      clearDynamicSupabaseConfig();
      setSupabaseConfig(getSupabaseConfig());
      setSupabaseSyncMessage('Credenciais redefinidas para o padrão do ambiente.');
    } else {
      saveDynamicSupabaseConfig(inputUrl, inputKey);
      setSupabaseConfig(getSupabaseConfig());
      setSupabaseSyncMessage('Novas credenciais do Supabase configuradas com sucesso!');
    }
    setTimeout(() => setSupabaseSyncMessage(''), 4000);
  };

  const handleSeedSupabase = async () => {
    setSupabaseSyncing(true);
    setSupabaseSyncMessage('Semeando escala inicial no Supabase...');
    try {
      const success = await saveFlightsToSupabase(flights);
      if (success) {
        setSupabaseSyncMessage('DADOS ENVIADOS: Escala gravada com sucesso nas tabelas do Supabase!');
      } else {
        setSupabaseSyncMessage('ERRO: Não foi possível gravar na tabela. Verifique se as tabelas foram criadas com o script SQL.');
      }
    } catch (e) {
      setSupabaseSyncMessage('Falha ao conectar: ' + String(e));
    } finally {
      setSupabaseSyncing(false);
      setTimeout(() => setSupabaseSyncMessage(''), 5000);
    }
  };

  const handleFetchSupabase = async () => {
    setSupabaseSyncing(true);
    setSupabaseSyncMessage('Buscando escala do Supabase...');
    try {
      const dbFlights = await fetchFlightsFromSupabase();
      if (dbFlights && dbFlights.length > 0) {
        setFlights(dbFlights);
        setSupabaseSyncMessage('SUCESSO: Escala de voos importada diretamente do Supabase!');
      } else {
        setSupabaseSyncMessage('ERRO: Nenhuma escala encontrada. Use o botão "Semear" ou crie registros na tabela escala_voos.');
      }
    } catch (e) {
      setSupabaseSyncMessage('Erro na importação: ' + String(e));
    } finally {
      setSupabaseSyncing(false);
      setTimeout(() => setSupabaseSyncMessage(''), 5000);
    }
  };

  const handleCopySQL = () => {
    navigator.clipboard.writeText(getSupabaseSQLScript());
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  };

  const handleSelectFlight = (flight: Flight) => {
    setSelectedFlight(flight);
    setActiveTab('details');
  };

  const handleAddFlight = (newFlight: Flight) => {
    setFlights([newFlight, ...flights]);
  };

  const handleUpdateDocument = (updatedDoc: Document) => {
    setDocuments(documents.map(d => d.id === updatedDoc.id ? updatedDoc : d));
  };

  const handleAddDocument = (newDoc: Document) => {
    setDocuments([...documents, newDoc]);
  };

  const handleDeleteDocument = (id: string) => {
    setDocuments(documents.filter(d => d.id !== id));
  };

  const handleConfirmOperation = () => {
    const now = new Date();
    const timeString = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

    setOperationLog({
      ...operationLog,
      confirmed: true,
      confirmedAt: timeString
    });

    // Mark current selected flight as completed if one is active
    if (selectedFlight) {
      setFlights(flights.map(f => f.id === selectedFlight.id ? { ...f, status: 'completed' } : f));
    }

    // Add a success notification
    setNotifications([
      {
        id: Date.now(),
        text: `Voo ${selectedFlight?.id || 'AV-1092-B'} confirmado com sucesso às ${timeString}!`,
        date: 'Agora',
        unread: true
      },
      ...notifications
    ]);
  };

  const handleResetData = () => {
    if (confirm('Deseja redefinir os dados operacionais para os padrões iniciais?')) {
      localStorage.clear();
      setFlights(INITIAL_FLIGHTS);
      setDocuments(INITIAL_DOCUMENTS);
      setCrew(INITIAL_CREW);
      setLodging(INITIAL_LODGING);
      setOperationLog(INITIAL_OPERATION_LOGS[0]);
      setPilotDetails({
        name: 'CAPTAIN J. MILLER',
        rank: 'CDR',
        idCode: '8824-H6-LX',
        dutyHours: '12,450.5 FT',
        isActive: true
      });
      setSelectedFlight(null);
      alert('Dados restaurados com sucesso!');
    }
  };

  const unreadCount = notifications.filter(n => n.unread).length;

  return (
    <div className="min-h-screen relative overflow-hidden flex flex-col bg-bg-dark terminal-grid text-text-bright">
      {/* Phosphor Scanline Glow overlay */}
      <div className="scanline" />

      {/* ---------------------------------- */}
      {/* 1. GATED ACCESS / TERMINAL LOGIN AREA */}
      {/* ---------------------------------- */}
      {!sessionUser ? (
        <div className="flex-grow flex items-center justify-center p-4 min-h-screen relative z-10">
          <div className="max-w-md w-full bg-surface-card border border-outline-tactical rounded-xl p-md sm:p-lg shadow-2xl relative glow-gold overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary to-amber-500" />
            
            <div className="text-center space-y-sm mb-md">
              <div className="inline-flex items-center justify-center p-3 bg-primary/10 rounded-full border border-primary/20 text-primary mb-2">
                <Lock size={28} className="stroke-[2]" />
              </div>
              <h1 className="font-sans text-xl sm:text-2xl font-black tracking-tight text-primary uppercase">
                AV-OPS COCKPIT
              </h1>
              <p className="font-mono text-[10px] text-text-muted uppercase tracking-widest">
                SINAL DE ENTRADA REQUERIDO // GL-COCKPIT v3.5
              </p>
            </div>

            {/* Error Message Box */}
            {loginError && (
              <div className="p-sm bg-red-950/40 border border-expiring-red/40 rounded text-expiring-red font-mono text-[11px] leading-relaxed flex gap-2 items-start mb-4">
                <AlertTriangle size={16} className="flex-shrink-0 mt-0.5 text-expiring-red" />
                <div>
                  <strong className="block uppercase text-[10px]">Acesso Recusado</strong>
                  {loginError}
                </div>
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-sm font-mono text-xs">
              <div className="space-y-1">
                <label className="text-text-muted font-bold block uppercase tracking-wide">E-MAIL DO PILOTO (WEBAPP)</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-text-muted pointer-events-none">
                    @
                  </span>
                  <input
                    type="email"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="piloto@exemplo.com"
                    className="w-full bg-surface-low border border-outline-tactical rounded pl-8 pr-3 py-2 text-text-bright focus:outline-none focus:border-primary font-bold transition-all"
                  />
                </div>
                <p className="text-[10px] text-text-muted">Use <strong className="text-primary font-normal">rilazza@gmail.com</strong> para testes com assinatura ativa.</p>
              </div>

              <div className="space-y-1">
                <label className="text-text-muted font-bold block uppercase tracking-wide">CHAVE DE ACESSO / TOKEN</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-text-muted pointer-events-none">
                    <Key size={12} />
                  </span>
                  <input
                    type="text"
                    value={loginToken}
                    onChange={(e) => setLoginToken(e.target.value)}
                    placeholder="AV-OPS-XXXX-XX"
                    className="w-full bg-surface-low border border-outline-tactical rounded pl-8 pr-3 py-2 text-text-bright focus:outline-none focus:border-primary font-bold transition-all uppercase"
                  />
                </div>
                <p className="text-[10px] text-text-muted">Use <strong className="text-primary font-normal">AV-OPS-BLOCKED</strong> para simular uma assinatura inativa / atrasada.</p>
              </div>

              <button
                type="submit"
                disabled={isCheckingSub}
                className="w-full bg-primary text-on-primary font-black py-2.5 rounded hover:bg-primary-hover active:scale-[0.98] transition-all uppercase tracking-widest mt-4 cursor-pointer text-center"
              >
                {isCheckingSub ? 'Verificando Assinatura...' : 'AUTENTICAR COCKPIT'}
              </button>
            </form>

            <div className="mt-md pt-md border-t border-outline-tactical/40 text-center space-y-sm">
              <p className="font-mono text-[10px] text-text-muted uppercase">
                Área de Avaliação de Testes (Acesso Rápido)
              </p>
              <div className="flex gap-2 justify-center">
                <button
                  onClick={handleToggleMockPayment}
                  className="bg-surface-low hover:bg-zinc-800 text-primary border border-outline-gold/30 font-mono text-[10px] font-bold px-3 py-1.5 rounded uppercase tracking-wider flex items-center gap-1 active:scale-95 transition-all cursor-pointer"
                >
                  <Unlock size={10} />
                  LIBERAR ACESSO IMEDIATO
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* ---------------------------------- */
        /* 2. MAIN ACTIVE COCKPIT VIEW        */
        /* ---------------------------------- */
        <>
          {/* Top Navigation Bar */}
          <header className="fixed top-0 w-full z-50 bg-surface-card border-b border-outline-tactical/50 flex justify-between items-center px-4 h-16 shadow-md select-none">
            <div className="flex items-center gap-2">
              <Plane className="text-primary rotate-45 stroke-[2.5]" size={20} />
              <div className="flex flex-col">
                <span className="font-sans text-lg font-black tracking-tighter text-primary leading-none">
                  AV-OPS
                </span>
                <span className="font-mono text-[8px] text-text-muted mt-0.5 tracking-wide">
                  {quartaVersao.versionCode} INTEGRADO
                </span>
              </div>
              <span className="hidden sm:inline font-mono text-[9px] text-text-muted border border-outline-tactical px-1.5 py-0.5 rounded ml-2 uppercase">
                GL-COCKPIT v3.5
              </span>
            </div>

            <div className="flex items-center gap-4 relative">
              {/* Notifications Trigger */}
              <button
                onClick={() => setShowNotifications(!showNotifications)}
                className="hover:bg-surface-container text-text-muted hover:text-primary transition-all p-2 rounded-full relative active:scale-95 duration-100 cursor-pointer"
                title="Alertas do Painel"
              >
                <Bell size={18} />
                {unreadCount > 0 && (
                  <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-expiring-red rounded-full border border-bg-dark animate-pulse" />
                )}
              </button>

              {/* Quick Stats Banner (Duty Hours) */}
              <div className="hidden md:flex items-center gap-1 bg-surface-low border border-outline-tactical rounded px-2 py-1 text-[11px] font-mono text-primary font-bold">
                <Clock size={12} />
                <span>{pilotDetails.dutyHours}</span>
              </div>

              {/* Quick logout action */}
              <button
                onClick={handleLogout}
                className="p-2 hover:bg-surface-container rounded-full text-text-muted hover:text-expiring-red active:scale-95 transition-all cursor-pointer"
                title="Sair do Cockpit"
              >
                <LogOut size={15} />
              </button>
            </div>

            {/* Notifications Popover */}
            {showNotifications && (
              <div className="absolute right-4 top-16 w-80 bg-surface-card border border-outline-tactical p-md rounded-lg shadow-xl z-50 glow-gold-active font-mono text-xs">
                <div className="flex justify-between items-center border-b border-outline-tactical/50 pb-sm mb-sm text-[10px] text-text-muted font-bold">
                  <span>ALERTAS DE OPERAÇÃO</span>
                  <button
                    onClick={() => setNotifications(notifications.map(n => ({ ...n, unread: false })))}
                    className="text-primary hover:underline"
                  >
                    MARCAR LIDOS
                  </button>
                </div>
                <div className="space-y-sm max-h-60 overflow-y-auto">
                  {notifications.map(n => (
                    <div key={n.id} className={`p-sm rounded text-[11px] leading-relaxed border ${n.unread ? 'bg-primary/5 border-outline-gold' : 'bg-surface-low border-outline-tactical/30'}`}>
                      <p className={n.unread ? 'text-primary font-bold' : 'text-text-bright'}>{n.text}</p>
                      <p className="text-[9px] text-text-muted mt-1">{n.date}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </header>

          {/* Main Content Area */}
          <main className="flex-grow pt-20 pb-28 px-4 max-w-4xl w-full mx-auto space-y-md">
            
            {/* Sync Notifications Banner */}
            {supabaseSyncMessage && (
              <div className="p-sm bg-primary/10 border border-outline-gold rounded text-primary text-xs font-mono text-center flex items-center justify-center gap-2 animate-pulse">
                <Database size={14} />
                <span>{supabaseSyncMessage}</span>
              </div>
            )}

            {/* Profile/Identity Card remains visible at the top when relevant */}
            {activeTab === 'profile' && (
              <div className="space-y-lg animate-fade-in duration-300">
                {/* Identity display */}
                <IdentityCard
                  pilotName={pilotDetails.name}
                  rank={pilotDetails.rank}
                  idCode={pilotDetails.idCode}
                  dutyHours={pilotDetails.dutyHours}
                  isActive={pilotDetails.isActive}
                />

                {/* ---------------------------------- */}
                {/* SUPABASE & WEBAPP INTEGRATION CARD */}
                {/* ---------------------------------- */}
                <section className="bg-surface-card border border-outline-tactical p-md rounded-lg space-y-md">
                  <div className="flex items-center gap-2 border-b border-outline-tactical/40 pb-2">
                    <Database size={16} className="text-primary" />
                    <h3 className="font-mono text-xs font-bold text-text-bright tracking-widest uppercase">
                      Integração Webapp & Banco Supabase
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-md text-xs font-mono">
                    
                    {/* Column 1: Connection Setup & Status */}
                    <div className="space-y-sm">
                      <div className="bg-surface-low p-sm rounded border border-outline-tactical/60 space-y-2">
                        <div>
                          <span className="text-[9px] text-text-muted uppercase block font-mono">Sessão Autenticada</span>
                          <div className="text-primary font-bold truncate text-[11px]">{sessionUser.userName}</div>
                          <div className="text-[10px] text-text-muted truncate">{sessionUser.email}</div>
                        </div>

                        {sessionUser.isRealDb ? (
                          <div className="text-[10px] text-valid-green flex items-center gap-1.5 font-bold bg-green-500/10 p-2 rounded border border-green-500/20 uppercase tracking-wide">
                            <CheckCircle2 size={12} />
                            <span>Supabase: Escala Real Ativa</span>
                          </div>
                        ) : (
                          <div className="text-[10px] text-amber-400 flex flex-col gap-1 bg-amber-500/5 p-2 rounded border border-amber-500/20 uppercase tracking-wide">
                            <div className="flex items-center gap-1.5 font-bold">
                              <AlertTriangle size={12} />
                              <span>Acesso via Demonstração Local</span>
                            </div>
                            {sessionUser.dbError && (
                              <p className="text-[9px] text-text-muted font-mono lowercase normal-case leading-relaxed">
                                motivo: {sessionUser.dbError}
                              </p>
                            )}
                          </div>
                        )}

                        <div className="text-[10px] text-valid-green flex items-center gap-1 mt-1 font-bold">
                          <CheckCircle2 size={12} />
                          Assinatura Ativa ({sessionUser.type.toUpperCase()})
                        </div>
                      </div>

                      <form onSubmit={handleUpdateConfig} className="space-y-sm">
                        <span className="text-[9px] text-primary uppercase block font-bold tracking-wider mt-2">Configurar Conexão Direta</span>
                        <div>
                          <label className="text-text-muted text-[10px] block mb-0.5">SUPABASE PROJECT URL</label>
                          <input
                            type="text"
                            value={inputUrl}
                            onChange={(e) => setInputUrl(e.target.value)}
                            placeholder="https://yourproject.supabase.co"
                            className="w-full bg-surface-low border border-outline-tactical rounded p-2 font-bold text-text-bright focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="text-text-muted text-[10px] block mb-0.5">SUPABASE ANON PUBLIC KEY</label>
                          <input
                            type="password"
                            value={inputKey}
                            onChange={(e) => setInputKey(e.target.value)}
                            placeholder="your-anon-key..."
                            className="w-full bg-surface-low border border-outline-tactical rounded p-2 font-bold text-text-bright focus:outline-none"
                          />
                        </div>
                        <div className="flex gap-2 justify-end">
                          <button
                            type="submit"
                            className="bg-surface-container hover:bg-zinc-800 border border-outline-tactical text-[10px] py-1.5 px-3 rounded uppercase font-bold text-primary cursor-pointer active:scale-95 transition-transform"
                          >
                            Salvar Chaves
                          </button>
                        </div>
                      </form>

                      {/* Sync triggers */}
                      <div className="pt-2 border-t border-outline-tactical/30 space-y-sm">
                        <span className="text-[9px] text-text-muted uppercase block font-bold">Sincronização de Voos</span>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            type="button"
                            onClick={handleFetchSupabase}
                            disabled={supabaseSyncing}
                            className="bg-primary/10 border border-outline-gold text-primary hover:bg-primary/20 text-[10px] font-bold py-2 rounded uppercase cursor-pointer text-center"
                          >
                            Baixar Escala
                          </button>
                          <button
                            type="button"
                            onClick={handleSeedSupabase}
                            disabled={supabaseSyncing}
                            className="bg-zinc-900 border border-outline-tactical text-text-bright hover:bg-zinc-800 text-[10px] font-bold py-2 rounded uppercase cursor-pointer text-center"
                          >
                            Semear Supabase
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Column 2: SQL Scripts & How-To */}
                    <div className="space-y-sm flex flex-col justify-between">
                      <div className="bg-surface-low p-sm rounded border border-outline-tactical/60 flex-grow flex flex-col justify-between">
                        <div>
                          <span className="text-[9px] text-text-muted uppercase block font-bold mb-1">Como integrar com seu banco</span>
                          <p className="text-[10px] text-text-muted leading-relaxed">
                            Para carregar a <strong className="text-primary font-normal">escala de voos real</strong>, as taxas do sumário e as assinaturas diretamente do seu Supabase, crie as tabelas executando o script SQL gerado abaixo no painel do Supabase.
                          </p>
                        </div>

                        <div className="mt-3">
                          <button
                            type="button"
                            onClick={handleCopySQL}
                            className="w-full bg-primary text-on-primary font-bold text-[10px] py-1.5 px-3 rounded uppercase flex items-center justify-center gap-1 cursor-pointer active:scale-95 transition-all"
                          >
                            {copiedSql ? <Check size={12} /> : <Copy size={12} />}
                            {copiedSql ? 'COPIADO COM SUCESSO!' : 'COPIAR SCRIPT SQL TABELAS'}
                          </button>
                        </div>
                      </div>

                      <div className="bg-primary/5 p-2 rounded border border-outline-gold/20 text-[10px] text-primary space-y-1">
                        <div className="font-bold uppercase tracking-wider text-[9px]">DIÁRIAS & RATES (QUARTA_VERSAO)</div>
                        <p className="leading-normal">
                          Configurações lidas: <strong className="text-text-bright font-normal">{quartaVersao.versionCode}</strong> - {quartaVersao.description}
                        </p>
                        <p className="leading-normal">
                          Nacional: <strong className="text-text-bright font-normal">R$ {quartaVersao.diariasNacionalRate}</strong> / Internac.: <strong className="text-text-bright font-normal">R$ {quartaVersao.diariasInternacionalRate}</strong>
                        </p>
                      </div>

                    </div>

                  </div>
                </section>

                {/* Profile Config Form to edit pilot */}
                <section className="bg-surface-card border border-outline-tactical p-md rounded-lg">
                  <h3 className="font-mono text-xs font-bold text-text-muted tracking-widest border-b border-outline-tactical/40 pb-1 mb-md uppercase">
                    Tripulante - Cadastro Ativo
                  </h3>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-sm text-xs font-mono">
                    <div>
                      <label className="block text-text-muted mb-1">NOME DO COMANDANTE</label>
                      <input
                        type="text"
                        value={pilotDetails.name}
                        onChange={(e) => setPilotDetails({ ...pilotDetails, name: e.target.value.toUpperCase() })}
                        className="w-full bg-surface-low border border-outline-tactical rounded p-2 text-primary font-bold focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-text-muted mb-1">REGISTRO (ID / ANAC)</label>
                      <input
                        type="text"
                        value={pilotDetails.idCode}
                        onChange={(e) => setPilotDetails({ ...pilotDetails, idCode: e.target.value })}
                        className="w-full bg-surface-low border border-outline-tactical rounded p-2 text-text-bright focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-text-muted mb-1">PATENTE / RANK</label>
                      <select
                        value={pilotDetails.rank}
                        onChange={(e) => setPilotDetails({ ...pilotDetails, rank: e.target.value })}
                        className="w-full bg-surface-low border border-outline-tactical rounded p-2 text-text-bright focus:outline-none"
                      >
                        <option value="CDR">COMANDANTE (CDR)</option>
                        <option value="CAPT">CAPTAIN (CAPT)</option>
                        <option value="F.O.">FIRST OFFICER (F.O.)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-text-muted mb-1">TOTAL HORAS DE VOO (FT)</label>
                      <input
                        type="text"
                        value={pilotDetails.dutyHours}
                        onChange={(e) => setPilotDetails({ ...pilotDetails, dutyHours: e.target.value })}
                        className="w-full bg-surface-low border border-outline-tactical rounded p-2 text-text-bright focus:outline-none"
                      />
                    </div>
                  </div>

                  {/* Action buttons on Profile */}
                  <div className="mt-md pt-md border-t border-outline-tactical/30 flex justify-end">
                    <button
                      onClick={() => {
                        setActiveTab('flights');
                      }}
                      className="bg-primary text-on-primary font-mono text-xs font-black tracking-widest py-2 px-md hover:bg-primary-hover active:scale-95 transition-transform rounded uppercase"
                    >
                      UPDATE ESCALA
                    </button>
                  </div>
                </section>

                {/* Document validation list */}
                <DocumentList
                  documents={documents}
                  onUpdateDocument={handleUpdateDocument}
                  onAddDocument={handleAddDocument}
                  onDeleteDocument={handleDeleteDocument}
                />
              </div>
            )}

            {/* Flight Schedule Tab */}
            {activeTab === 'flights' && (
              <div className="space-y-md">
                {/* Quick mini info block */}
                <div className="flex justify-between items-center bg-surface-card p-sm border border-outline-tactical rounded">
                  <span className="font-mono text-xs text-text-muted uppercase">Escala atual de: <strong className="text-primary font-bold">{pilotDetails.name}</strong></span>
                  <span className="font-mono text-[10px] text-valid-green bg-green-500/10 px-2 py-0.5 rounded border border-green-500/20 font-bold uppercase tracking-wide">STATUS: SINCRONIZADA</span>
                </div>
                
                <FlightSchedule
                  flights={flights}
                  onSelectFlight={handleSelectFlight}
                  onAddFlight={handleAddFlight}
                />
              </div>
            )}

            {/* Flight Details Log Tab */}
            {activeTab === 'details' && (
              <FlightDetails
                selectedFlight={selectedFlight}
                crew={crew}
                lodging={lodging}
                operationLog={operationLog}
                onUpdateCrew={setCrew}
                onUpdateLodging={setLodging}
                onUpdateOperationLog={setOperationLog}
                onConfirmOperation={handleConfirmOperation}
              />
            )}

            {/* Reports panel tab */}
            {activeTab === 'reports' && (
              <ReportsPanel
                initialNationalRate={quartaVersao.diariasNacionalRate}
                initialInternationalRate={quartaVersao.diariasInternacionalRate}
                versionCode={quartaVersao.versionCode}
                versionDescription={quartaVersao.description}
              />
            )}

          </main>

          {/* Persistent Bottom Nav Bar (High Contrast HUD styling) */}
          <nav className="fixed bottom-0 w-full z-50 h-20 bg-surface-card border-t border-outline-tactical flex justify-around items-center px-4 shadow-lg select-none">
            
            {/* Flights Tab Trigger */}
            <button
              onClick={() => {
                setActiveTab('flights');
                setSelectedFlight(null); // Back to schedule mode
              }}
              className={`flex flex-col items-center justify-center transition-all cursor-pointer ${
                activeTab === 'flights' ? 'text-primary scale-110 font-bold' : 'text-text-muted hover:text-text-bright'
              }`}
            >
              <Calendar size={18} className={activeTab === 'flights' ? 'stroke-[2.5]' : ''} />
              <span className="font-mono text-[10px] mt-1 tracking-widest uppercase">
                Voos
              </span>
            </button>

            {/* Details Tab Trigger (Enabled or has active flight) */}
            <button
              onClick={() => {
                setActiveTab('details');
              }}
              className={`flex flex-col items-center justify-center transition-all cursor-pointer ${
                activeTab === 'details' ? 'text-primary scale-110 font-bold' : 'text-text-muted hover:text-text-bright'
              }`}
            >
              <Plane size={18} className={activeTab === 'details' ? 'stroke-[2.5]' : ''} />
              <span className="font-mono text-[10px] mt-1 tracking-widest uppercase">
                Detalhes
              </span>
            </button>

            {/* Reports Tab Trigger */}
            <button
              onClick={() => {
                setActiveTab('reports');
              }}
              className={`flex flex-col items-center justify-center transition-all cursor-pointer ${
                activeTab === 'reports' ? 'text-primary scale-110 font-bold' : 'text-text-muted hover:text-text-bright'
              }`}
            >
              <FileText size={18} className={activeTab === 'reports' ? 'stroke-[2.5]' : ''} />
              <span className="font-mono text-[10px] mt-1 tracking-widest uppercase">
                Relatórios
              </span>
            </button>

            {/* Profile Tab Trigger */}
            <button
              onClick={() => {
                setActiveTab('profile');
              }}
              className={`flex flex-col items-center justify-center transition-all cursor-pointer ${
                activeTab === 'profile' ? 'text-primary scale-110 font-bold' : 'text-text-muted hover:text-text-bright'
              }`}
            >
              <User size={18} className={activeTab === 'profile' ? 'stroke-[2.5]' : ''} />
              <span className="font-mono text-[10px] mt-1 tracking-widest uppercase">
                Perfil
              </span>
            </button>

          </nav>
        </>
      )}
    </div>
  );
}
