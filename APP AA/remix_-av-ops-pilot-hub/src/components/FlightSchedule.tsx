import React, { useState, useMemo } from 'react';
import { Flight } from '../types';
import { Plane, Search, Clock, ArrowRight, Plus, Eye, CheckCircle2, AlertCircle } from 'lucide-react';

interface FlightScheduleProps {
  flights: Flight[];
  onSelectFlight: (flight: Flight) => void;
  onAddFlight: (flight: Flight) => void;
}

export default function FlightSchedule({
  flights,
  onSelectFlight,
  onAddFlight
}: FlightScheduleProps) {
  const [filterType, setFilterType] = useState<'ALL' | 'CURRENT'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDay, setSelectedDay] = useState<string | null>('29'); // "29" matches screenshot default selection

  // Days list matching DOM 01 to TER 31
  const daysOfWeek = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB'];
  const dates = useMemo(() => {
    const list = [];
    // Generating dates for August/September 2021 (e.g. 1st to 31st)
    for (let i = 1; i <= 31; i++) {
      const dayStr = i.toString().padStart(2, '0');
      // Just some fixed week matching for August 2021 where 1st is Sunday (DOM)
      const weekIndex = (i - 1) % 7;
      list.push({
        dayNum: dayStr,
        dayName: daysOfWeek[weekIndex]
      });
    }
    return list;
  }, []);

  // Filter flights
  const filteredFlights = useMemo(() => {
    return flights.filter((flight) => {
      // 1. Filter by ALL vs CURRENT
      if (filterType === 'CURRENT' && flight.status !== 'active') {
        return false;
      }
      
      // 2. Filter by search query
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesQuery =
          flight.id.toLowerCase().includes(query) ||
          flight.routeFrom.toLowerCase().includes(query) ||
          flight.routeTo.toLowerCase().includes(query) ||
          flight.date.toLowerCase().includes(query);
        if (!matchesQuery) return false;
      }

      // 3. Filter by selected day on horizontal timeline (if selected)
      if (selectedDay) {
        // e.g., flight.date is "29/08/2021", extract the first 2 chars
        const flightDay = flight.date.split('/')[0];
        if (flightDay !== selectedDay) return false;
      }

      return true;
    });
  }, [flights, filterType, searchQuery, selectedDay]);

  // Form state to add quick flight
  const [showAddModal, setShowAddModal] = useState(false);
  const [newId, setNewId] = useState('');
  const [newFrom, setNewFrom] = useState('');
  const [newTo, setNewTo] = useState('');
  const [newPres, setNewPres] = useState('');
  const [newDep, setNewDep] = useState('');
  const [newArr, setNewArr] = useState('');
  const [newDate, setNewDate] = useState('29/08/2021');

  const handleCreateFlight = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newId || !newFrom || !newTo) return;

    onAddFlight({
      id: newId.toUpperCase(),
      routeFrom: newFrom.toUpperCase(),
      routeTo: newTo.toUpperCase(),
      presentationTime: newPres || '12:00',
      departureTime: newDep || '13:00',
      arrivalTime: newArr || '15:00',
      date: newDate,
      restTime: '—',
      hoursDuty: '06:00',
      hoursFlight: '02:00',
      status: 'scheduled'
    });

    setNewId('');
    setNewFrom('');
    setNewTo('');
    setNewPres('');
    setNewDep('');
    setNewArr('');
    setShowAddModal(false);
  };

  // Quick preset navigators (FIRST, LAST, NEXT, END)
  const handleTimelineNav = (type: 'FIRST' | 'LAST' | 'NEXT' | 'END') => {
    if (type === 'FIRST') {
      setSelectedDay('01');
    } else if (type === 'LAST') {
      setSelectedDay('31');
    } else if (type === 'NEXT') {
      if (selectedDay) {
        const num = parseInt(selectedDay, 10);
        if (num < 31) {
          setSelectedDay((num + 1).toString().padStart(2, '0'));
        }
      } else {
        setSelectedDay('01');
      }
    } else if (type === 'END') {
      setSelectedDay('31');
    }
  };

  // Calculate duty/flight hours dynamically for the filtered view
  const { totalDuty, totalFlight } = useMemo(() => {
    let dutyMins = 0;
    let flightMins = 0;

    filteredFlights.forEach((f) => {
      const [dh, dm] = f.hoursDuty.split(':').map(Number);
      const [fh, fm] = f.hoursFlight.split(':').map(Number);
      if (!isNaN(dh) && !isNaN(dm)) dutyMins += dh * 60 + dm;
      if (!isNaN(fh) && !isNaN(fm)) flightMins += fh * 60 + fm;
    });

    const formatTime = (totalMinutes: number) => {
      const h = Math.floor(totalMinutes / 60).toString().padStart(2, '0');
      const m = (totalMinutes % 60).toString().padStart(2, '0');
      return `${h}:${m}`;
    };

    return {
      totalDuty: formatTime(dutyMins),
      totalFlight: formatTime(flightMins)
    };
  }, [filteredFlights]);

  return (
    <div className="space-y-4">
      {/* Search & Selection Controls Card */}
      <div className="bg-surface-card/60 backdrop-blur-md rounded border border-outline-tactical/30 p-md space-y-md">
        
        {/* Toggle and Add Flight Buttons */}
        <div className="flex justify-between items-center">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3 py-1 bg-primary text-on-primary font-mono text-[11px] font-bold tracking-wider hover:bg-primary-hover active:scale-95 transition-all rounded uppercase"
          >
            <Plus size={12} /> NOVO VOO
          </button>

          <div className="flex bg-surface-low border border-outline-tactical rounded p-0.5 gap-1">
            <button
              onClick={() => {
                setFilterType('ALL');
                setSelectedDay(null); // Show all days
              }}
              className={`px-3 py-1 rounded font-mono text-[10px] transition-all font-bold ${
                filterType === 'ALL' && selectedDay === null
                  ? 'bg-primary text-on-primary'
                  : 'text-text-muted hover:text-primary'
              }`}
            >
              TODOS
            </button>
            <button
              onClick={() => {
                setFilterType('CURRENT');
                setSelectedDay(null);
              }}
              className={`px-3 py-1 rounded font-mono text-[10px] transition-all font-bold ${
                filterType === 'CURRENT'
                  ? 'bg-primary text-on-primary'
                  : 'text-text-muted hover:text-primary'
              }`}
            >
              ATIVOS
            </button>
          </div>
        </div>

        {/* Search Bar Input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" size={16} />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-low border border-outline-tactical/60 rounded py-2 pl-10 pr-4 font-mono text-xs text-primary focus:border-primary focus:outline-none transition-all placeholder:text-text-muted/40"
            placeholder="Search flights (e.g. VCP, SSA, AD4372)..."
            type="text"
          />
        </div>

        {/* Horizontal Calendar Timeline */}
        <div className="space-y-2">
          <div className="flex justify-between items-center text-[10px] font-mono text-text-muted">
            <span>SELECIONAR DATA</span>
            {selectedDay ? (
              <button onClick={() => setSelectedDay(null)} className="text-primary hover:underline">
                [LIMPAR DATA]
              </button>
            ) : (
              <span>TODAS AS DATAS</span>
            )}
          </div>
          
          <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar">
            {dates.map((date) => {
              const isSelected = selectedDay === date.dayNum;
              return (
                <button
                  key={date.dayNum}
                  onClick={() => setSelectedDay(date.dayNum)}
                  className={`flex-shrink-0 w-11 h-11 rounded border flex flex-col items-center justify-center transition-all active:scale-95 cursor-pointer ${
                    isSelected
                      ? 'border-primary bg-primary/15 glow-gold'
                      : 'border-outline-tactical/30 bg-surface-low hover:border-primary/40 hover:bg-surface-container/50'
                  }`}
                >
                  <span className={`text-[9px] font-mono leading-none ${isSelected ? 'text-primary' : 'text-text-muted'}`}>
                    {date.dayName}
                  </span>
                  <span className={`text-sm font-bold mt-0.5 ${isSelected ? 'text-primary' : 'text-text-bright'}`}>
                    {date.dayNum}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Quick Nav Button bar */}
          <div className="grid grid-cols-4 gap-1 pt-1">
            <button
              onClick={() => handleTimelineNav('FIRST')}
              className="bg-surface-low border border-outline-tactical/30 py-2 font-mono text-[9px] text-text-muted hover:text-primary hover:border-primary/40 active:scale-95 transition-all uppercase"
            >
              « FIRST
            </button>
            <button
              onClick={() => handleTimelineNav('LAST')}
              className="bg-surface-low border border-outline-tactical/30 py-2 font-mono text-[9px] text-text-muted hover:text-primary hover:border-primary/40 active:scale-95 transition-all uppercase"
            >
              &lt; LAST
            </button>
            <button
              onClick={() => handleTimelineNav('NEXT')}
              className="bg-surface-low border border-outline-tactical/30 py-2 font-mono text-[9px] text-text-muted hover:text-primary hover:border-primary/40 active:scale-95 transition-all uppercase"
            >
              NEXT &gt;
            </button>
            <button
              onClick={() => handleTimelineNav('END')}
              className="bg-surface-low border border-outline-tactical/30 py-2 font-mono text-[9px] text-text-muted hover:text-primary hover:border-primary/40 active:scale-95 transition-all uppercase"
            >
              END »
            </button>
          </div>
        </div>

        {/* Current Date Key Banner */}
        <div className="flex items-center justify-between bg-surface-low border border-outline-tactical/40 p-2 rounded">
          <span className="font-mono text-[11px] text-primary tracking-wider uppercase">
            CHAVE {selectedDay || '01'}/31 — {selectedDay || '01'}/08/2021 → {selectedDay ? (parseInt(selectedDay) + 1).toString().padStart(2, '0') : '31'}/08/2021
          </span>
        </div>
      </div>

      {/* Quick Add Flight Dialog Box */}
      {showAddModal && (
        <form onSubmit={handleCreateFlight} className="bg-surface-card border border-primary/40 p-md rounded-lg space-y-md glow-gold-active">
          <div className="border-b border-outline-tactical/60 pb-2">
            <h3 className="font-mono text-xs font-bold text-primary uppercase">CADASTRAR ETAPA DE VOO</h3>
          </div>
          <div className="grid grid-cols-2 gap-sm">
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">CÓDIGO VOO</label>
              <input
                type="text"
                placeholder="AD4372"
                required
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">DATA</label>
              <input
                type="text"
                placeholder="29/08/2021"
                required
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">ORIGEM</label>
              <input
                type="text"
                placeholder="VCP"
                required
                value={newFrom}
                onChange={(e) => setNewFrom(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">DESTINO</label>
              <input
                type="text"
                placeholder="SSA"
                required
                value={newTo}
                onChange={(e) => setNewTo(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">APRESENTAÇÃO</label>
              <input
                type="text"
                placeholder="22:40"
                value={newPres}
                onChange={(e) => setNewPres(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">DECOLAGEM</label>
              <input
                type="text"
                placeholder="23:40"
                value={newDep}
                onChange={(e) => setNewDep(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-[10px] font-mono text-text-muted mb-1">POUSO / CHEGADA</label>
              <input
                type="text"
                placeholder="02:00"
                value={newArr}
                onChange={(e) => setNewArr(e.target.value)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-outline-tactical/30">
            <button
              type="button"
              onClick={() => setShowAddModal(false)}
              className="text-[11px] font-mono px-3 py-1.5 bg-surface-low hover:bg-zinc-800 text-text-muted border border-outline-tactical rounded"
            >
              CANCELAR
            </button>
            <button
              type="submit"
              className="text-[11px] font-mono px-3 py-1.5 bg-primary text-on-primary hover:bg-primary-hover font-bold rounded"
            >
              SALVAR VOO
            </button>
          </div>
        </form>
      )}

      {/* Flight Schedule List/Table */}
      <div className="bg-surface-card border border-outline-tactical/40 rounded overflow-hidden">
        {/* Desktop Table View */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-outline-tactical/50 bg-surface-low text-left">
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4">ATIVIDADE</th>
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4">ROTA</th>
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4">APRESENTAÇÃO</th>
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4">HORÁRIO</th>
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4">DATA</th>
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4">REPOUSO</th>
                <th className="font-mono text-[10px] text-text-muted tracking-wider py-3 px-4 text-right">AÇÕES</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-tactical/20 font-mono text-sm">
              {filteredFlights.map((flight) => (
                <tr
                  key={flight.id}
                  onClick={() => onSelectFlight(flight)}
                  className="hover:bg-surface-container/50 transition-colors active:bg-surface-container cursor-pointer group"
                >
                  <td className="py-4 px-4 text-primary font-bold">{flight.id}</td>
                  <td className="py-4 px-4 text-text-bright">
                    {flight.routeFrom} <span className="text-primary/60">→</span> {flight.routeTo}
                  </td>
                  <td className="py-4 px-4 text-text-bright">{flight.presentationTime}</td>
                  <td className="py-4 px-4 text-text-bright">
                    <div className="flex items-center gap-1.5">
                      <Plane size={13} className="text-primary/70 rotate-45" />
                      {flight.departureTime} - {flight.arrivalTime}
                    </div>
                  </td>
                  <td className="py-4 px-4 text-text-muted">{flight.date}</td>
                  <td className={`py-4 px-4 ${flight.restTime !== '—' ? 'text-primary font-bold' : 'text-primary/40'}`}>
                    {flight.restTime}
                  </td>
                  <td className="py-4 px-4 text-right">
                    <button className="p-1 rounded hover:bg-primary/20 text-text-muted group-hover:text-primary transition-colors">
                      <Eye size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile Tactile List View */}
        <div className="block md:hidden divide-y divide-outline-tactical/30">
          {filteredFlights.map((flight) => (
            <div
              key={flight.id}
              onClick={() => onSelectFlight(flight)}
              className="p-4 hover:bg-surface-container/30 active:bg-surface-container transition-colors cursor-pointer space-y-2 relative"
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-sm font-bold text-primary">{flight.id}</span>
                <span className="font-mono text-xs text-text-muted">{flight.date}</span>
              </div>
              
              <div className="flex justify-between items-center">
                <div className="font-mono text-md text-text-bright font-bold flex items-center gap-2">
                  <span>{flight.routeFrom}</span>
                  <ArrowRight size={14} className="text-primary/70" />
                  <span>{flight.routeTo}</span>
                </div>
                <div className="font-mono text-xs text-text-bright flex items-center gap-1">
                  <Clock size={12} className="text-primary" />
                  <span>Apres: {flight.presentationTime}</span>
                </div>
              </div>

              <div className="flex justify-between items-center pt-1 border-t border-outline-tactical/10">
                <div className="font-mono text-xs text-text-muted flex items-center gap-1">
                  <Plane size={12} className="text-primary rotate-45" />
                  <span>Dec-Pouso: {flight.departureTime} - {flight.arrivalTime}</span>
                </div>
                {flight.restTime !== '—' && (
                  <div className="font-mono text-[11px] text-primary">
                    Repouso: <span className="font-bold">{flight.restTime}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Empty State */}
        {filteredFlights.length === 0 && (
          <div className="text-center py-10 space-y-2">
            <AlertCircle size={24} className="text-text-muted mx-auto" />
            <p className="font-mono text-xs text-text-muted">Nenhuma etapa encontrada para os filtros aplicados.</p>
          </div>
        )}
      </div>

      {/* Footer Summary stats card */}
      <div className="bg-surface-low border border-outline-tactical/40 px-md py-4 rounded-lg">
        <div className="flex flex-wrap gap-x-8 gap-y-2">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-text-muted tracking-wider uppercase">Horas de Jornada:</span>
            <span className="font-mono text-lg text-primary font-bold">{totalDuty}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-text-muted tracking-wider uppercase">Horas de Voo:</span>
            <span className="font-mono text-lg text-primary font-bold">{totalFlight}</span>
          </div>
        </div>
        <p className="font-mono text-[9px] text-text-muted/40 mt-4 leading-relaxed break-all uppercase tracking-tight">
          FONTE: ESCALA_E_RICARDO_LAZZARINI_VCP__3394___AZUL_CMTE_SIMPL_01082021_31082021_QUARTA_VERSAO_22062026_170855.CSV
        </p>
      </div>
    </div>
  );
}
