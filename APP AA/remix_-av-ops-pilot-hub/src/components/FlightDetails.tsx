import React, { useState } from 'react';
import { Flight, CrewMember, LodgingInfo, OperationLog } from '../types';
import {
  Car,
  Hotel,
  Plus,
  Users,
  MapPin,
  Calendar,
  Camera,
  CheckCircle2,
  Bell,
  Trash2,
  Clock,
  MoreVertical,
  HelpCircle,
  FileCheck
} from 'lucide-react';

interface FlightDetailsProps {
  selectedFlight: Flight | null;
  crew: CrewMember[];
  lodging: LodgingInfo;
  operationLog: OperationLog;
  onUpdateCrew: (newCrew: CrewMember[]) => void;
  onUpdateLodging: (newLodging: LodgingInfo) => void;
  onUpdateOperationLog: (log: OperationLog) => void;
  onConfirmOperation: () => void;
}

export default function FlightDetails({
  selectedFlight,
  crew,
  lodging,
  operationLog,
  onUpdateCrew,
  onUpdateLodging,
  onUpdateOperationLog,
  onConfirmOperation
}: FlightDetailsProps) {
  // Local state for forms
  const [showAddCrewForm, setShowAddCrewForm] = useState(false);
  const [newCrewName, setNewCrewName] = useState('');
  const [newCrewRole, setNewCrewRole] = useState('COMISSÁRIO');

  const [showEditLodgingForm, setShowEditLodgingForm] = useState(false);
  const [hotelName, setHotelName] = useState(lodging.hotelName);
  const [hotelAddress, setHotelAddress] = useState(lodging.address);
  const [hotelCheckIn, setHotelCheckIn] = useState(lodging.checkIn);
  const [hotelReservation, setHotelReservation] = useState(lodging.reservationCode);

  // Attachment upload simulation
  const [planoUploadName, setPlanoUploadName] = useState<string | null>(null);
  const [realizadoUploadName, setRealizadoUploadName] = useState<string | null>(null);

  // Capture timestamp helper
  const handleLogTime = (field: 'saidaHotel' | 'chegadaAeroporto' | 'saidaAeroporto' | 'chegadaHotel') => {
    const now = new Date();
    const timeString = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    
    onUpdateOperationLog({
      ...operationLog,
      [field]: timeString
    });
  };

  const handleManualTimeChange = (field: 'saidaHotel' | 'chegadaAeroporto' | 'saidaAeroporto' | 'chegadaHotel', val: string) => {
    onUpdateOperationLog({
      ...operationLog,
      [field]: val
    });
  };

  // Crew helpers
  const handleAddCrew = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCrewName.trim()) return;

    const newMember: CrewMember = {
      id: 'CREW_' + Date.now(),
      name: newCrewName,
      role: newCrewRole
    };

    onUpdateCrew([...crew, newMember]);
    setNewCrewName('');
    setShowAddCrewForm(false);
  };

  const handleRemoveCrew = (id: string) => {
    onUpdateCrew(crew.filter((member) => member.id !== id));
  };

  // Lodging helpers
  const handleSaveLodging = (e: React.FormEvent) => {
    e.preventDefault();
    onUpdateLodging({
      hotelName,
      address: hotelAddress,
      checkIn: hotelCheckIn,
      reservationCode: hotelReservation
    });
    setShowEditLodgingForm(false);
  };

  // Simulation of document snap
  const triggerCameraMock = (type: 'plano' | 'realizado') => {
    const randId = Math.floor(Math.random() * 9000) + 1000;
    const mockFilename = type === 'plano' 
      ? `PLANO_VOO_AV_${randId}_SIGNED.PNG` 
      : `LOG_REALIZADO_AV_${randId}_FINAL.PNG`;
    
    if (type === 'plano') {
      setPlanoUploadName(mockFilename);
    } else {
      setRealizadoUploadName(mockFilename);
    }
  };

  // Safe leg list fallback if no flight is active
  const defaultLegs = [
    { from: 'GRU', fromTime: '14:20', to: 'GIG', toTime: '16:05' },
    { from: 'GIG', fromTime: '18:30', to: 'BSB', toTime: '20:15' }
  ];

  const currentLegs = selectedFlight 
    ? [{ from: selectedFlight.routeFrom, fromTime: selectedFlight.departureTime, to: selectedFlight.routeTo, toTime: selectedFlight.arrivalTime }]
    : defaultLegs;

  const currentFlightId = selectedFlight ? `AV-${selectedFlight.id}-B` : 'AV-1092-B';

  return (
    <div className="space-y-gutter relative pb-8">
      {/* Top Breadcrumb and Header */}
      <div className="flex flex-col gap-1">
        <span className="font-mono text-[10px] text-primary tracking-widest uppercase font-bold">
          Operações de Voo
        </span>
        <div className="flex justify-between items-end gap-sm">
          <h2 className="font-sans text-xl sm:text-2xl font-black tracking-tight text-text-bright">
            Detalhes do Voo
          </h2>
          <span className="font-mono text-xs text-text-muted bg-surface-container border border-outline-tactical px-2 py-1 select-none rounded">
            ID: {currentFlightId}
          </span>
        </div>
      </div>

      {/* Confirmation Notification Banner */}
      {operationLog.confirmed && (
        <div className="p-md bg-green-500/10 border border-green-500/30 rounded flex items-center gap-3 text-valid-green font-mono text-xs glow-gold">
          <CheckCircle2 size={18} className="flex-shrink-0" />
          <div>
            <p className="font-bold uppercase tracking-wider">OPERAÇÃO CONFIRMADA COM SUCESSO</p>
            <p className="text-[10px] text-text-muted mt-0.5">Enviado para o Departamento de Operações às {operationLog.confirmedAt || '--:--'}</p>
          </div>
        </div>
      )}

      {/* Primary Flight Info Card Segment */}
      <div className="space-y-4">
        
        {/* Trajeto Inicial Card */}
        <div className="bg-surface-card border border-outline-tactical p-md rounded-lg relative overflow-hidden glow-gold">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary" />
          <div className="flex justify-between items-center mb-md">
            <span className="font-mono text-xs font-bold text-primary uppercase tracking-widest flex items-center gap-2">
              <Car size={14} /> INÍCIO TRAJETO HOTEL
            </span>
            <span className="font-mono text-[10px] text-text-muted">[TOUCH TO LOG]</span>
          </div>

          <div className="grid grid-cols-2 gap-md">
            {/* Saída Hotel */}
            <div className="p-sm bg-surface-low border border-outline-tactical rounded relative group">
              <p className="font-mono text-[9px] text-text-muted uppercase mb-1">Saída Hotel</p>
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleLogTime('saidaHotel')}
                  className="font-mono text-sm text-primary font-bold cursor-pointer hover:opacity-80 active:scale-95 transition-all text-left flex items-center gap-1.5"
                >
                  {operationLog.saidaHotel}
                  <Clock size={11} className="opacity-50" />
                </button>
                <input
                  type="text"
                  value={operationLog.saidaHotel}
                  onChange={(e) => handleManualTimeChange('saidaHotel', e.target.value)}
                  className="w-12 bg-transparent border-b border-outline-tactical text-xs text-right text-text-bright focus:outline-none focus:border-primary font-mono"
                />
              </div>
            </div>

            {/* Chegada Aeroporto */}
            <div className="p-sm bg-surface-low border border-outline-tactical rounded relative">
              <p className="font-mono text-[9px] text-text-muted uppercase mb-1">Chegada Aeroporto</p>
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleLogTime('chegadaAeroporto')}
                  className="font-mono text-sm text-text-bright font-bold cursor-pointer hover:opacity-80 active:scale-95 transition-all text-left flex items-center gap-1.5"
                >
                  {operationLog.chegadaAeroporto}
                  <Clock size={11} className="opacity-50" />
                </button>
                <input
                  type="text"
                  value={operationLog.chegadaAeroporto}
                  onChange={(e) => handleManualTimeChange('chegadaAeroporto', e.target.value)}
                  className="w-12 bg-transparent border-b border-outline-tactical text-xs text-right text-text-bright focus:outline-none focus:border-primary font-mono"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Etapas do Dia Card */}
        <div className="bg-surface-card border border-outline-tactical p-md rounded-lg relative overflow-hidden">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-text-muted/40" />
          <h3 className="font-mono text-xs font-bold text-text-muted mb-md uppercase tracking-widest">
            Etapas do Dia
          </h3>
          
          <div className="space-y-md">
            {currentLegs.map((leg, index) => (
              <div
                key={index}
                className="flex items-center justify-between border-b border-outline-tactical/30 pb-sm last:border-0 last:pb-0"
              >
                <div className="flex-1">
                  <p className="font-mono text-[10px] text-text-muted">ORIGEM</p>
                  <p className="font-mono text-sm font-bold text-text-bright">{leg.from}</p>
                  <p className="font-mono text-xs text-primary font-bold">{leg.fromTime}</p>
                </div>
                
                <div className="flex flex-col items-center px-md text-text-muted">
                  <Clock size={11} className="mb-0.5 text-primary/60" />
                  <div className="h-[1px] w-12 bg-outline-tactical relative">
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-primary" />
                  </div>
                  <span className="text-[8px] font-mono mt-1 uppercase">ESTIMADO</span>
                </div>
                
                <div className="flex-1 text-right">
                  <p className="font-mono text-[10px] text-text-muted">DESTINO</p>
                  <p className="font-mono text-sm font-bold text-text-bright">{leg.to}</p>
                  <p className="font-mono text-xs text-primary font-bold">{leg.toTime}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Trajeto Final Card */}
        <div className="bg-surface-card border border-outline-tactical p-md rounded-lg relative overflow-hidden glow-gold">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary" />
          <div className="flex justify-between items-center mb-md">
            <span className="font-mono text-xs font-bold text-primary uppercase tracking-widest flex items-center gap-2">
              <Hotel size={14} /> FINAL TRAJETO AEROPORTO
            </span>
            <span className="font-mono text-[10px] text-text-muted">[TOUCH TO LOG]</span>
          </div>

          <div className="grid grid-cols-2 gap-md">
            {/* Saída Aeroporto */}
            <div className="p-sm bg-surface-low border border-outline-tactical rounded relative">
              <p className="font-mono text-[9px] text-text-muted uppercase mb-1">Saída Aeroporto</p>
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleLogTime('saidaAeroporto')}
                  className="font-mono text-sm text-primary font-bold cursor-pointer hover:opacity-80 active:scale-95 transition-all text-left flex items-center gap-1.5"
                >
                  {operationLog.saidaAeroporto}
                  <Clock size={11} className="opacity-50" />
                </button>
                <input
                  type="text"
                  value={operationLog.saidaAeroporto}
                  onChange={(e) => handleManualTimeChange('saidaAeroporto', e.target.value)}
                  className="w-12 bg-transparent border-b border-outline-tactical text-xs text-right text-text-bright focus:outline-none focus:border-primary font-mono"
                />
              </div>
            </div>

            {/* Chegada Hotel */}
            <div className="p-sm bg-surface-low border border-outline-tactical rounded relative">
              <p className="font-mono text-[9px] text-text-muted uppercase mb-1">Chegada Hotel</p>
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleLogTime('chegadaHotel')}
                  className="font-mono text-sm text-text-bright font-bold cursor-pointer hover:opacity-80 active:scale-95 transition-all text-left flex items-center gap-1.5"
                >
                  {operationLog.chegadaHotel}
                  <Clock size={11} className="opacity-50" />
                </button>
                <input
                  type="text"
                  value={operationLog.chegadaHotel}
                  onChange={(e) => handleManualTimeChange('chegadaHotel', e.target.value)}
                  className="w-12 bg-transparent border-b border-outline-tactical text-xs text-right text-text-bright focus:outline-none focus:border-primary font-mono"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Manual Details Sections (Crew and Lodging) */}
      <div className="space-y-4">
        <h3 className="font-mono text-xs font-bold text-text-muted tracking-widest border-b border-outline-tactical pb-1 mb-md uppercase">
          Detalhes Manuais
        </h3>

        {/* Crew Members Section */}
        <section className="bg-surface-card p-md border border-outline-tactical rounded-lg">
          <div className="flex justify-between items-center mb-md">
            <div className="flex items-center gap-2">
              <Users size={16} className="text-primary" />
              <h4 className="font-sans text-sm font-bold text-text-bright uppercase">Equipagem</h4>
            </div>
            <button
              onClick={() => setShowAddCrewForm(!showAddCrewForm)}
              className="flex items-center gap-1 text-[11px] font-mono text-primary hover:text-primary-hover active:scale-95 transition-transform"
            >
              <Plus size={14} /> ADICIONAR
            </button>
          </div>

          {showAddCrewForm && (
            <form onSubmit={handleAddCrew} className="mb-md p-sm bg-surface-low border border-outline-tactical rounded space-y-sm">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-sm">
                <div>
                  <label className="block text-[10px] font-mono text-text-muted mb-1">NOME DO TRIPULANTE</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Cap. Carlos Mendes"
                    value={newCrewName}
                    onChange={(e) => setNewCrewName(e.target.value)}
                    className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-text-muted mb-1">FUNÇÃO / CARGO</label>
                  <select
                    value={newCrewRole}
                    onChange={(e) => setNewCrewRole(e.target.value)}
                    className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
                  >
                    <option value="COMANDANTE">COMANDANTE</option>
                    <option value="PRIMEIRO OFICIAL">PRIMEIRO OFICIAL</option>
                    <option value="COMISSÁRIO">COMISSÁRIO</option>
                    <option value="MECÂNICO">MECÂNICO DE VOO</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-outline-tactical/20">
                <button
                  type="button"
                  onClick={() => setShowAddCrewForm(false)}
                  className="text-[10px] font-mono px-2 py-1 bg-surface-container hover:bg-zinc-800 text-text-muted rounded"
                >
                  CANCELAR
                </button>
                <button
                  type="submit"
                  className="text-[10px] font-mono px-2 py-1 bg-primary text-on-primary font-bold rounded"
                >
                  GRAVAR
                </button>
              </div>
            </form>
          )}

          <div className="space-y-2">
            {crew.map((member) => (
              <div
                key={member.id}
                className="flex justify-between items-center p-sm bg-surface-low border-l-2 border-primary rounded-r"
              >
                <div>
                  <p className="font-sans text-xs text-text-bright font-bold">{member.name}</p>
                  <p className="font-mono text-[9px] text-text-muted uppercase tracking-wider">{member.role}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleRemoveCrew(member.id)}
                    className="p-1 text-text-muted hover:text-expiring-red hover:bg-red-500/10 rounded transition-colors active:scale-95"
                    title="Remover Tripulante"
                  >
                    <Trash2 size={12} />
                  </button>
                  <MoreVertical size={14} className="text-text-muted" />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Lodging Information Section */}
        <section className="bg-surface-card p-md border border-outline-tactical rounded-lg">
          <div className="flex justify-between items-center mb-md">
            <div className="flex items-center gap-2">
              <Hotel size={16} className="text-primary" />
              <h4 className="font-sans text-sm font-bold text-text-bright uppercase">Hospedagem</h4>
            </div>
            <button
              onClick={() => setShowEditLodgingForm(!showEditLodgingForm)}
              className="flex items-center gap-1 text-[11px] font-mono text-primary hover:text-primary-hover active:scale-95 transition-transform"
            >
              <Plus size={14} /> EDITAR
            </button>
          </div>

          {showEditLodgingForm && (
            <form onSubmit={handleSaveLodging} className="mb-md p-sm bg-surface-low border border-outline-tactical rounded space-y-sm">
              <div className="space-y-sm">
                <div>
                  <label className="block text-[10px] font-mono text-text-muted mb-1">NOME DO HOTEL</label>
                  <input
                    type="text"
                    required
                    value={hotelName}
                    onChange={(e) => setHotelName(e.target.value)}
                    className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-text-muted mb-1">ENDEREÇO</label>
                  <input
                    type="text"
                    required
                    value={hotelAddress}
                    onChange={(e) => setHotelAddress(e.target.value)}
                    className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-sm">
                  <div>
                    <label className="block text-[10px] font-mono text-text-muted mb-1">HORÁRIO CHECK-IN</label>
                    <input
                      type="text"
                      required
                      value={hotelCheckIn}
                      onChange={(e) => setHotelCheckIn(e.target.value)}
                      className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-text-muted mb-1">CÓDIGO RESERVA</label>
                    <input
                      type="text"
                      required
                      value={hotelReservation}
                      onChange={(e) => setHotelReservation(e.target.value)}
                      className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-xs text-text-bright focus:border-primary focus:outline-none"
                    />
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-outline-tactical/20">
                <button
                  type="button"
                  onClick={() => setShowEditLodgingForm(false)}
                  className="text-[10px] font-mono px-2 py-1 bg-surface-container hover:bg-zinc-800 text-text-muted rounded"
                >
                  CANCELAR
                </button>
                <button
                  type="submit"
                  className="text-[10px] font-mono px-2 py-1 bg-primary text-on-primary font-bold rounded"
                >
                  SALVAR
                </button>
              </div>
            </form>
          )}

          <div className="p-sm bg-surface-low border border-outline-tactical space-y-sm rounded">
            <div>
              <p className="font-sans text-xs text-text-bright font-extrabold">{lodging.hotelName}</p>
              <p className="font-mono text-[10px] text-text-muted mt-0.5 flex items-center gap-1">
                <MapPin size={11} className="text-primary/70" /> {lodging.address}
              </p>
            </div>
            
            <div className="flex items-center justify-between border-t border-outline-tactical/30 pt-sm">
              <div>
                <p className="font-mono text-[9px] text-text-muted uppercase">CHECK-IN</p>
                <p className="font-mono text-xs font-bold text-text-bright">{lodging.checkIn}</p>
              </div>
              <div className="text-right">
                <p className="font-mono text-[9px] text-text-muted uppercase">RESERVA</p>
                <p className="font-mono text-xs font-bold text-primary">{lodging.reservationCode}</p>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Upload/Scan triggers */}
      <div className="mt-md flex flex-col gap-sm">
        <button
          type="button"
          onClick={() => triggerCameraMock('plano')}
          className="border border-primary text-primary hover:bg-primary/5 active:scale-95 text-xs font-mono font-bold py-3 flex items-center justify-center gap-2 rounded transition-all uppercase tracking-wider select-none cursor-pointer"
        >
          <Camera size={14} /> DADOS PLANO DO VOO
        </button>
        {planoUploadName && (
          <div className="text-center font-mono text-[10px] text-valid-green bg-green-500/5 p-1 border border-green-500/20 rounded">
            ✓ FILE ATTACHED: {planoUploadName}
          </div>
        )}

        <button
          type="button"
          onClick={() => triggerCameraMock('realizado')}
          className="border border-primary text-primary hover:bg-primary/5 active:scale-95 text-xs font-mono font-bold py-3 flex items-center justify-center gap-2 rounded transition-all uppercase tracking-wider select-none cursor-pointer"
        >
          <Camera size={14} /> DADOS DO VOO REALIZADO
        </button>
        {realizadoUploadName && (
          <div className="text-center font-mono text-[10px] text-valid-green bg-green-500/5 p-1 border border-green-500/20 rounded">
            ✓ FILE ATTACHED: {realizadoUploadName}
          </div>
        )}
      </div>

      {/* Primary CONFIRMAR OPERAÇÃO Trigger */}
      <div className="mt-md">
        <button
          type="button"
          onClick={onConfirmOperation}
          className={`w-full py-4 font-mono font-black text-sm tracking-widest text-on-primary bg-primary hover:bg-primary-hover active:scale-[0.98] transition-all rounded shadow-lg glow-gold uppercase cursor-pointer select-none`}
        >
          CONFIRMAR OPERAÇÃO
        </button>
      </div>
    </div>
  );
}
