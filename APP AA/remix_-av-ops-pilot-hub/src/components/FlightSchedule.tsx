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

  // 1. Extrai todos os dias únicos ordenados que possuem atividades/voos na escala
  const activeDays = useMemo(() => {
    if (!flights || flights.length === 0) return [];
    const daysSet = new Set<string>();
    flights.forEach((f) => {
      if (f.date && f.date.includes('/')) {
        const day = f.date.split('/')[0];
        daysSet.add(day);
      }
    });
    return Array.from(daysSet).sort((a, b) => parseInt(a, 10) - parseInt(b, 10));
  }, [flights]);

  // Define o dia selecionado por padrão como o primeiro dia ativo
  const [selectedDayState, setSelectedDayState] = useState<string | null>(null);
  
  const selectedDay = useMemo(() => {
    if (selectedDayState) return selectedDayState;
    if (activeDays.length > 0) return activeDays[0];
    return null;
  }, [selectedDayState, activeDays]);

  const setSelectedDay = (day: string | null) => {
    setSelectedDayState(day);
  };

  // Days list matching DOM 01 to TER 31
  const dates = useMemo(() => {
    const list = [];
    const daysOfWeek = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB'];
    
    activeDays.forEach((dayStr) => {
      const flight = flights.find((f) => f.date && f.date.split('/')[0] === dayStr);
      let dayName = '---';
      if (flight && flight.date) {
        try {
          const p = flight.date.split('/');
          const dateObj = new Date(parseInt(p[2]), parseInt(p[1]) - 1, parseInt(p[0]));
          dayName = daysOfWeek[dateObj.getDay()];
        } catch (e) {}
      }
      list.push({
        dayNum: dayStr,
        dayName: dayName
      });
    });
    return list;
  }, [activeDays, flights]);

  // Filter flights
  const filteredFlights = useMemo(() => {
    return flights.filter((flight) => {
      // 1. Filter by search query
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesQuery =
          flight.id.toLowerCase().includes(query) ||
          flight.routeFrom.toLowerCase().includes(query) ||
          flight.routeTo.toLowerCase().includes(query) ||
          flight.date.toLowerCase().includes(query);
        if (!matchesQuery) return false;
      }

      // 2. Se filterType for ALL, mostra todos os voos (ignora o dia selecionado)
      if (filterType === 'ALL') {
        return true;
      }

      // 3. Se filterType for CURRENT, filtra pelo selectedDay
      if (filterType === 'CURRENT' && selectedDay) {
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

  // Quick preset navigators (PRIMEIRO, ANTERIOR, PRÓXIMO, ÚLTIMO)
  const handleTimelineNav = (type: 'FIRST' | 'PREV' | 'NEXT' | 'LAST') => {
    if (activeDays.length === 0) return;
    const currentIndex = selectedDay ? activeDays.indexOf(selectedDay) : -1;

    if (type === 'FIRST') {
      setSelectedDay(activeDays[0]);
    } else if (type === 'LAST') {
      setSelectedDay(activeDays[activeDays.length - 1]);
    } else if (type === 'PREV') {
      if (currentIndex > 0) {
        setSelectedDay(activeDays[currentIndex - 1]);
      } else {
        setSelectedDay(activeDays[0]);
      }
    } else if (type === 'NEXT') {
      if (currentIndex >= 0 && currentIndex < activeDays.length - 1) {
        setSelectedDay(activeDays[currentIndex + 1]);
      } else {
        setSelectedDay(activeDays[activeDays.length - 1]);
      }
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
      {/* Toggle Buttons (TODOS vs CHAVES DE VOO) */}
      <div className="flex justify-end items-center">
        <div className="flex bg-surface-low border border-outline-tactical rounded p-0.5 gap-1 shadow-md">
          <button
            onClick={() => {
              setFilterType('ALL');
            }}
            className={`px-3 py-1 rounded font-mono text-[10px] transition-all font-bold cursor-pointer uppercase ${
              filterType === 'ALL'
                ? 'bg-primary text-on-primary shadow-sm'
                : 'text-text-muted hover:text-primary'
            }`}
          >
            TODOS
          </button>
          <button
            onClick={() => {
              setFilterType('CURRENT');
              if (activeDays.length > 0) {
                setSelectedDay(activeDays[0]);
              }
            }}
            className={`px-3 py-1 rounded font-mono text-[10px] transition-all font-bold cursor-pointer uppercase ${
              filterType === 'CURRENT'
                ? 'bg-primary text-on-primary shadow-sm'
                : 'text-text-muted hover:text-primary'
            }`}
          >
            CHAVES DE VOO
          </button>
        </div>
      </div>

      {/* Flight Schedule List/Table */}
      <div className="bg-surface-card border border-outline-tactical/40 rounded overflow-hidden shadow-lg">
        
        {/* Painel de Navegação de Chaves de Voo integrado ao quadro */}
        {filterType === 'CURRENT' && selectedDay && (
          <div className="p-md bg-surface-low border-b border-outline-tactical/50 flex flex-col sm:flex-row justify-between items-center gap-md">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-primary rounded-full animate-pulse" />
              <span className="font-mono text-xs text-text-bright font-bold uppercase tracking-wider">
                CHAVE DE VOO ATIVA — DIA {selectedDay}
              </span>
            </div>
            
            {/* Botões rápidos integrados */}
            <div className="flex bg-surface-card border border-outline-tactical rounded p-0.5 gap-1 font-mono text-[9px] font-bold">
              <button
                onClick={() => handleTimelineNav('FIRST')}
                className="px-2.5 py-1 text-text-muted hover:text-primary transition-colors cursor-pointer uppercase"
              >
                PRIMEIRO
              </button>
              <button
                onClick={() => handleTimelineNav('PREV')}
                className="px-2.5 py-1 text-text-muted hover:text-primary transition-colors border-l border-outline-tactical/40 cursor-pointer uppercase"
              >
                ANTERIOR
              </button>
              <button
                onClick={() => handleTimelineNav('NEXT')}
                className="px-2.5 py-1 text-text-muted hover:text-primary transition-colors border-l border-outline-tactical/40 cursor-pointer uppercase"
              >
                PRÓXIMO
              </button>
              <button
                onClick={() => handleTimelineNav('LAST')}
                className="px-2.5 py-1 text-text-muted hover:text-primary transition-colors border-l border-outline-tactical/40 cursor-pointer uppercase"
              >
                ÚLTIMO
              </button>
            </div>
          </div>
        )}
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
