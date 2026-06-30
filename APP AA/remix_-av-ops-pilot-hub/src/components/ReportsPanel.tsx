import React, { useState, useMemo } from 'react';
import { FileText, Printer, Check, Download, AlertCircle, RefreshCw } from 'lucide-react';

interface ReportsPanelProps {
  initialNationalRate?: number;
  initialInternationalRate?: number;
  versionCode?: string;
  versionDescription?: string;
}

export default function ReportsPanel({
  initialNationalRate = 125,
  initialInternationalRate = 210,
  versionCode = "v3.5",
  versionDescription = "Local Offline"
}: ReportsPanelProps) {
  // Report Form Inputs for reactive math
  const [nationalCount, setNationalCount] = useState(0);
  const [nationalRate, setNationalRate] = useState(initialNationalRate);
  const [internationalCount, setInternationalCount] = useState(0);
  const [internationalRate, setInternationalRate] = useState(initialInternationalRate);
  const [reimbursement, setReimbursement] = useState(0);
  const [flightCount, setFlightCount] = useState(0);
  const [flightHours, setFlightHours] = useState('00:00');

  // Sync with prop updates from Supabase
  React.useEffect(() => {
    setNationalRate(initialNationalRate);
  }, [initialNationalRate]);

  React.useEffect(() => {
    setInternationalRate(initialInternationalRate);
  }, [initialInternationalRate]);

  const [pilotName, setPilotName] = useState('RICARDO LAZZARINI');
  const [reNumber, setReNumber] = useState('3394');
  const [baseOps, setBaseOps] = useState('SBGR / SÃO PAULO');
  const [period, setPeriod] = useState('01/08/2021 - 31/08/2021');
  const [diarias, setDiarias] = useState<any[]>([]);

  // Load real diaries and pilot info from storage
  React.useEffect(() => {
    const savedPilot = localStorage.getItem('av_ops_pilot');
    if (savedPilot) {
      try {
        const pilot = JSON.parse(savedPilot);
        setPilotName(pilot.name || 'RICARDO LAZZARINI');
        setReNumber(pilot.idCode || '3394');
      } catch (e) {}
    }

    const savedFlights = localStorage.getItem('av_ops_flights');
    if (savedFlights) {
      try {
        const fls: any[] = JSON.parse(savedFlights);
        setFlightCount(fls.length);
        
        let totalMins = 0;
        fls.forEach(f => {
          const parts = (f.hoursFlight || '00:00').split(':');
          if (parts.length === 2) {
            totalMins += parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
          }
        });
        const hrs = Math.floor(totalMins / 60).toString().padStart(2, '0');
        const mins = (totalMins % 60).toString().padStart(2, '0');
        setFlightHours(`${hrs}:${mins}`);
      } catch (e) {}
    }

    const savedDiarias = localStorage.getItem('av_ops_diarias_real');
    if (savedDiarias) {
      try {
        const parsed: any[] = JSON.parse(savedDiarias);
        setDiarias(parsed);
        // Filtra refeições com valor > 0 usando a lista parsed
        const nacionais = parsed.filter(d => (d.Regiao === 'Nacional' || d.Moeda === 'R$') && parseFloat((d.Valor || '0').toString().replace(',', '.')) > 0);
        const internacionais = parsed.filter(d => (d.Regiao !== 'Nacional' && d.Moeda !== 'R$') && parseFloat((d.Valor || '0').toString().replace(',', '.')) > 0);
        
        setNationalCount(nacionais.length);
        setInternationalCount(internacionais.length);
        
        if (nacionais.length > 0) {
          const val = parseFloat((nacionais[0].Valor || '0').toString().replace(',', '.'));
          if (!isNaN(val) && val > 0) setNationalRate(val);
        }
        if (internacionais.length > 0) {
          const val = parseFloat((internacionais[0].Valor || '0').toString().replace(',', '.'));
          if (!isNaN(val) && val > 0) setInternationalRate(val);
        }

        // Tenta extrair período
        if (parsed.length > 0) {
          const sorted = [...parsed].sort((a, b) => {
            const parseDate = (dStr: string) => {
              const p = dStr.split('/');
              return new Date(parseInt(p[2]), parseInt(p[1]) - 1, parseInt(p[0])).getTime();
            };
            return parseDate(a.Data || a.date) - parseDate(b.Data || b.date);
          });
          const inicio = sorted[0].Data || sorted[0].date;
          const fim = sorted[sorted.length - 1].Data || sorted[sorted.length - 1].date;
          if (inicio && fim) {
            setPeriod(`${inicio} - ${fim}`);
          }
        }
      } catch (err) {
        console.warn('Erro ao ler diárias:', err);
      }
    }
  }, []);

  // Interactive print/download simulation states
  const [isSimulatingPrint, setIsSimulatingPrint] = useState(false);
  const [isSimulatingDownload, setIsSimulatingDownload] = useState(false);

  // Reactive calculations
  const totalNational = useMemo(() => {
    let sum = 0;
    diarias.forEach(d => {
      if (d.Regiao === 'Nacional' || d.Moeda === 'R$') {
        const val = parseFloat((d.Valor || '0').toString().replace(',', '.'));
        if (!isNaN(val)) sum += val;
      }
    });
    return sum;
  }, [diarias]);

  const totalInternational = useMemo(() => {
    let sum = 0;
    diarias.forEach(d => {
      if (d.Regiao && d.Regiao !== 'Nacional' && d.Moeda !== 'R$') {
        const val = parseFloat((d.Valor || '0').toString().replace(',', '.'));
        if (!isNaN(val)) sum += val;
      }
    });
    return sum;
  }, [diarias]);

  const totalToReceive = useMemo(() => {
    return totalNational + totalInternational + reimbursement;
  }, [totalNational, totalInternational, reimbursement]);

  // Format currencies
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(val);
  };

  const handlePrint = () => {
    setIsSimulatingPrint(true);
    setTimeout(() => {
      setIsSimulatingPrint(false);
      alert('Relatório enviado para a fila de impressão do tablet operacional!');
    }, 1500);
  };

  const handleDownload = () => {
    setIsSimulatingDownload(true);
    setTimeout(() => {
      setIsSimulatingDownload(false);
      // Create a mock download trigger
      const reportText = `
        RELATÓRIO DE DIÁRIAS A RECEBER
        =============================
        Tripulante: ${pilotName}
        RE: ${reNumber}
        Base: ${baseOps}
        Período: ${period}

        RESUMO DE VALORES
        -----------------
        Nacionais (${nationalCount}): ${formatCurrency(totalNational)}
        Internacionais (${internationalCount}): ${formatCurrency(totalInternational)}
        Adicionais: ${formatCurrency(reimbursement)}
        
        TOTAL LÍQUIDO A RECEBER: ${formatCurrency(totalToReceive)}
      `;
      const blob = new Blob([reportText], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `AVOPS_DIARIAS_${reNumber}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }, 1200);
  };

  return (
    <div className="space-y-lg">
      {/* Title & Description Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h2 className="font-sans text-xl sm:text-2xl font-black text-text-bright leading-none uppercase">
            Reports
          </h2>
          <p className="font-sans text-xs text-text-muted mt-1">
            Relatórios operacionais e analíticos para faturamento e reembolso de diárias.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-center bg-surface-container border border-outline-tactical rounded px-2.5 py-1 text-[10px] font-mono text-primary font-bold">
          <span className="w-1.5 h-1.5 bg-valid-green rounded-full animate-pulse" />
          <span>FONTE: SUPABASE ({versionCode})</span>
        </div>
      </div>

      {/* Visão Geral Grid cards */}
      <section className="space-y-sm">
        <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-widest font-bold">
          VISÃO GERAL
        </h3>
        <div className="grid grid-cols-3 gap-sm">
          <div className="bg-surface-card border border-outline-tactical p-md rounded flex flex-col gap-1 transition-all hover:border-primary/30">
            <span className="font-mono text-[9px] text-text-muted uppercase tracking-tight">VOOS</span>
            <span className="font-mono text-xl sm:text-2xl text-primary font-black leading-none">{flightCount}</span>
          </div>
          <div className="bg-surface-card border border-outline-tactical p-md rounded flex flex-col gap-1 transition-all hover:border-primary/30">
            <span className="font-mono text-[9px] text-text-muted uppercase tracking-tight">HORAS</span>
            <span className="font-mono text-xl sm:text-2xl text-primary font-black leading-none">{flightHours}</span>
          </div>
          <div className="bg-surface-card border border-outline-tactical p-md rounded flex flex-col gap-1 transition-all hover:border-primary/30 overflow-hidden">
            <span className="font-mono text-[9px] text-text-muted uppercase tracking-tight">DIÁRIAS</span>
            <span className="font-mono text-base sm:text-xl text-primary font-black leading-none truncate">
              {formatCurrency(totalToReceive).replace(',00', '')}
            </span>
          </div>
        </div>
      </section>

      {/* Relatórios Disponíveis Cards list */}
      <section className="space-y-sm">
        <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-widest font-bold">
          RELATÓRIOS DISPONÍVEIS
        </h3>
        <div className="bg-surface-card border border-outline-tactical rounded-lg p-md flex flex-col gap-md hover:border-primary/40 transition-all">
          <div className="flex items-start gap-md">
            <div className="bg-primary/10 p-sm rounded-lg border border-outline-gold/20 text-primary">
              <FileText size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="font-mono font-bold text-text-bright text-xs uppercase tracking-wider">
                SUMÁRIO DE DIÁRIAS COMPLETO
              </h4>
              <p className="font-mono text-text-muted text-[10px] truncate mt-1">
                AVOPS_{reNumber}_SUMARIO_HORAS_DIARIAS_OUT23.pdf
              </p>
            </div>
          </div>
          <div className="flex justify-between items-center border-t border-outline-tactical/30 pt-md">
            <div className="flex flex-col">
              <span className="font-mono text-[9px] text-text-muted uppercase">TOTAL A RECEBER</span>
              <span className="font-mono text-md text-primary font-extrabold">
                {formatCurrency(totalToReceive)}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Listagem Digital de Diárias Reais */}
      <section className="space-y-sm">
        <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-widest font-bold">
          DETALHAMENTO DE DIÁRIAS DO PERÍODO
        </h3>
        
        {diarias.length === 0 ? (
          <div className="bg-surface-card border border-outline-tactical p-lg rounded-lg text-center space-y-2">
            <AlertCircle className="text-text-muted mx-auto" size={24} />
            <p className="font-mono text-xs text-text-muted">Nenhuma diária real encontrada no Storage para este período.</p>
          </div>
        ) : (
          <div className="bg-surface-card border border-outline-tactical rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse font-mono text-xs">
                <thead>
                  <tr className="border-b border-outline-tactical/50 bg-surface-low text-left text-text-muted">
                    <th className="py-3 px-4 font-bold uppercase tracking-wider">DATA</th>
                    <th className="py-3 px-4 font-bold uppercase tracking-wider">ATIVIDADE / REFEIÇÃO</th>
                    <th className="py-3 px-4 font-bold uppercase tracking-wider">LOCALIDADE</th>
                    <th className="py-3 px-4 font-bold uppercase tracking-wider">REGIÃO</th>
                    <th className="py-3 px-4 font-bold uppercase tracking-wider text-right">VALOR</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-tactical/20">
                  {diarias.map((d, index) => {
                    const valorNum = parseFloat(d.Valor || '0');
                    const moeda = d.Moeda || 'R$';
                    return (
                      <tr key={index} className="hover:bg-surface-container/30 transition-colors">
                        <td className="py-3 px-4 text-text-bright font-bold">
                          {d.Data || d.date || d.data || '—'}
                        </td>
                        <td className="py-3 px-4 text-primary">
                          {d.Refeicao || d.Atividade || 'Diária'}
                        </td>
                        <td className="py-3 px-4 text-text-bright">
                          {d.Localidade || '—'}
                        </td>
                        <td className="py-3 px-4 text-text-muted">
                          {d.Regiao || 'Nacional'}
                        </td>
                        <td className="py-3 px-4 text-right font-bold text-text-bright">
                          {moeda} {valorNum.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
