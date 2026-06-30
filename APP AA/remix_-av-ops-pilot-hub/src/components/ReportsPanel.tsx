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
  const [nationalCount, setNationalCount] = useState(10);
  const [nationalRate, setNationalRate] = useState(initialNationalRate);
  const [internationalCount, setInternationalCount] = useState(4);
  const [internationalRate, setInternationalRate] = useState(initialInternationalRate);
  const [reimbursement, setReimbursement] = useState(328.91);

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
  const [period, setPeriod] = useState('01/10/2023 - 31/10/2023');

  // Interactive print/download simulation states
  const [isSimulatingPrint, setIsSimulatingPrint] = useState(false);
  const [isSimulatingDownload, setIsSimulatingDownload] = useState(false);

  // Reactive calculations
  const totalNational = useMemo(() => {
    return nationalCount * nationalRate;
  }, [nationalCount, nationalRate]);

  const totalInternational = useMemo(() => {
    return internationalCount * internationalRate;
  }, [internationalCount, internationalRate]);

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
            <span className="font-mono text-xl sm:text-2xl text-primary font-black leading-none">14</span>
          </div>
          <div className="bg-surface-card border border-outline-tactical p-md rounded flex flex-col gap-1 transition-all hover:border-primary/30">
            <span className="font-mono text-[9px] text-text-muted uppercase tracking-tight">HORAS</span>
            <span className="font-mono text-xl sm:text-2xl text-primary font-black leading-none">39:30</span>
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
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handlePrint}
                disabled={isSimulatingPrint}
                className="p-2 bg-surface-low hover:bg-zinc-800 border border-outline-tactical rounded text-primary hover:text-primary-hover active:scale-95 transition-all"
                title="Imprimir PDF"
              >
                {isSimulatingPrint ? <RefreshCw size={14} className="animate-spin" /> : <Printer size={14} />}
              </button>
              <button
                type="button"
                onClick={handleDownload}
                disabled={isSimulatingDownload}
                className="p-2 bg-primary text-on-primary rounded hover:bg-primary-hover active:scale-95 transition-all font-bold"
                title="Download CSV/TXT"
              >
                {isSimulatingDownload ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Interactive PDF Document Preview Paper in White! */}
      <section className="space-y-sm">
        <div className="flex justify-between items-center">
          <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-widest font-bold">
            PRÉ-VISUALIZAÇÃO DO DOCUMENTO
          </h3>
          <span className="font-mono text-[10px] text-primary bg-primary/10 px-2 py-0.5 border border-primary/20 rounded uppercase font-bold">
            Editável
          </span>
        </div>

        {/* Paper Container (White #FFFFFF, Text #000000) */}
        <div className="bg-white text-zinc-900 rounded-lg p-md sm:p-lg shadow-xl overflow-hidden font-sans border-4 border-zinc-200">
          
          {/* Document Print Header */}
          <div className="border-b-2 border-zinc-950 pb-sm mb-md text-center">
            <h1 className="text-md sm:text-lg font-black uppercase tracking-tight text-zinc-950">
              Relatório de Diárias a Receber
            </h1>
          </div>

          {/* Info Edit Grid */}
          <div className="grid grid-cols-2 gap-x-md gap-y-sm mb-lg text-[11px] border-b border-zinc-200 pb-sm">
            <div className="flex flex-col">
              <span className="uppercase text-[9px] text-zinc-500 font-bold tracking-tight">NOME DO TRIPULANTE</span>
              <input
                type="text"
                value={pilotName}
                onChange={(e) => setPilotName(e.target.value.toUpperCase())}
                className="font-bold text-zinc-900 bg-zinc-100 hover:bg-zinc-200 focus:bg-white rounded px-1.5 py-0.5 border-b border-transparent focus:border-zinc-900 focus:outline-none transition-all text-xs"
              />
            </div>
            <div className="flex flex-col">
              <span className="uppercase text-[9px] text-zinc-500 font-bold tracking-tight">REGISTRO (RE)</span>
              <input
                type="text"
                value={reNumber}
                onChange={(e) => setReNumber(e.target.value)}
                className="font-bold text-zinc-900 bg-zinc-100 hover:bg-zinc-200 focus:bg-white rounded px-1.5 py-0.5 border-b border-transparent focus:border-zinc-900 focus:outline-none transition-all text-xs"
              />
            </div>
            <div className="flex flex-col">
              <span className="uppercase text-[9px] text-zinc-500 font-bold tracking-tight">BASE OPERACIONAL</span>
              <input
                type="text"
                value={baseOps}
                onChange={(e) => setBaseOps(e.target.value.toUpperCase())}
                className="font-bold text-zinc-900 bg-zinc-100 hover:bg-zinc-200 focus:bg-white rounded px-1.5 py-0.5 border-b border-transparent focus:border-zinc-900 focus:outline-none transition-all text-xs"
              />
            </div>
            <div className="flex flex-col">
              <span className="uppercase text-[9px] text-zinc-500 font-bold tracking-tight">PERÍODO DE REFERÊNCIA</span>
              <input
                type="text"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="font-bold text-zinc-900 bg-zinc-100 hover:bg-zinc-200 focus:bg-white rounded px-1.5 py-0.5 border-b border-transparent focus:border-zinc-900 focus:outline-none transition-all text-xs"
              />
            </div>
          </div>

          {/* Value Calculation Table */}
          <div className="mt-4">
            <h5 className="text-[11px] font-black uppercase text-zinc-800 border-b border-zinc-950 pb-1 mb-sm tracking-wide">
              RESUMO DE VALORES
            </h5>
            
            <table className="w-full text-[11px] border-collapse">
              <tbody>
                {/* National rate */}
                <tr className="border-b border-zinc-100">
                  <td className="py-2 text-zinc-600 flex flex-wrap gap-1 items-center">
                    Total Diárias Nacionais
                    <span className="flex items-center text-[10px] text-zinc-500 bg-zinc-100 rounded px-1 gap-1">
                      (
                      <input
                        type="number"
                        min="0"
                        value={nationalCount}
                        onChange={(e) => setNationalCount(Math.max(0, parseInt(e.target.value) || 0))}
                        className="w-8 text-center bg-transparent focus:outline-none border-b border-zinc-300 focus:border-zinc-950 font-bold text-zinc-900"
                      />
                      ) x R$ 
                      <input
                        type="number"
                        min="0"
                        value={nationalRate}
                        onChange={(e) => setNationalRate(Math.max(0, parseInt(e.target.value) || 0))}
                        className="w-10 text-center bg-transparent focus:outline-none border-b border-zinc-300 focus:border-zinc-950 font-bold text-zinc-900"
                      />
                    </span>
                  </td>
                  <td className="py-2 text-right font-bold text-zinc-900">{formatCurrency(totalNational)}</td>
                </tr>

                {/* International rate */}
                <tr className="border-b border-zinc-100">
                  <td className="py-2 text-zinc-600 flex flex-wrap gap-1 items-center">
                    Total Diárias Internacionais
                    <span className="flex items-center text-[10px] text-zinc-500 bg-zinc-100 rounded px-1 gap-1">
                      (
                      <input
                        type="number"
                        min="0"
                        value={internationalCount}
                        onChange={(e) => setInternationalCount(Math.max(0, parseInt(e.target.value) || 0))}
                        className="w-8 text-center bg-transparent focus:outline-none border-b border-zinc-300 focus:border-zinc-950 font-bold text-zinc-900"
                      />
                      ) x R$ 
                      <input
                        type="number"
                        min="0"
                        value={internationalRate}
                        onChange={(e) => setInternationalRate(Math.max(0, parseInt(e.target.value) || 0))}
                        className="w-10 text-center bg-transparent focus:outline-none border-b border-zinc-300 focus:border-zinc-950 font-bold text-zinc-900"
                      />
                    </span>
                  </td>
                  <td className="py-2 text-right font-bold text-zinc-900">{formatCurrency(totalInternational)}</td>
                </tr>

                {/* Reimbursements */}
                <tr className="border-b border-zinc-100">
                  <td className="py-2 text-zinc-600 flex items-center gap-1">
                    Adicionais / Reembolsos (R$)
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={reimbursement}
                      onChange={(e) => setReimbursement(Math.max(0, parseFloat(e.target.value) || 0))}
                      className="w-16 bg-zinc-100 focus:bg-white border-b border-zinc-300 focus:border-zinc-950 focus:outline-none rounded px-1 py-0.5 text-zinc-900 text-center font-bold font-mono text-[10px]"
                    />
                  </td>
                  <td className="py-2 text-right font-bold text-zinc-900">{formatCurrency(reimbursement)}</td>
                </tr>

                {/* Net Receive */}
                <tr className="border-t-2 border-zinc-950 font-black bg-zinc-50 text-xs text-zinc-950">
                  <td className="py-3 px-1 uppercase tracking-tight">Líquido a Receber</td>
                  <td className="py-3 px-1 text-right">{formatCurrency(totalToReceive)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Disclaimer warning */}
          <div className="mt-4 flex gap-1.5 items-start p-2 bg-amber-50 rounded text-[9px] text-amber-800 leading-normal border border-amber-200">
            <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
            <p>O preenchimento inexato ou fraudulento deste formulário sujeita o tripulante às sanções estatutárias vigentes bem como aos regulamentos disciplinares da AV-OPS.</p>
          </div>

          {/* Signature Line block */}
          <div className="mt-10 pt-6 border-t border-dashed border-zinc-300 flex flex-col items-center text-center">
            <div className="w-48 border-b border-zinc-950 mb-2"></div>
            <span className="text-[9px] font-bold uppercase text-zinc-500 tracking-wider">
              Assinatura do Departamento de Operações
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
