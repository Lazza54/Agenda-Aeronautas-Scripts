import { Flight, Document, CrewMember, LodgingInfo, OperationLog } from './types';

export const INITIAL_FLIGHTS: Flight[] = [
  {
    id: 'AD4372',
    routeFrom: 'VCP',
    routeTo: 'SSA',
    presentationTime: '22:40',
    departureTime: '23:40',
    arrivalTime: '02:00',
    date: '29/08/2021',
    restTime: '—',
    hoursDuty: '07:05',
    hoursFlight: '04:45',
    status: 'completed',
  },
  {
    id: 'AD4027',
    routeFrom: 'SSA',
    routeTo: 'VCP',
    presentationTime: '22:40',
    departureTime: '02:50',
    arrivalTime: '05:15',
    date: '30/08/2021',
    restTime: '12:45',
    hoursDuty: '07:05',
    hoursFlight: '04:45',
    status: 'completed',
  },
  {
    id: 'AD2291',
    routeFrom: 'VCP',
    routeTo: 'GIG',
    presentationTime: '08:15',
    departureTime: '09:20',
    arrivalTime: '10:30',
    date: '31/08/2021',
    restTime: '—',
    hoursDuty: '03:15',
    hoursFlight: '01:10',
    status: 'scheduled',
  },
  {
    id: 'AD1092',
    routeFrom: 'GRU',
    routeTo: 'GIG',
    presentationTime: '13:20',
    departureTime: '14:20',
    arrivalTime: '16:05',
    date: '29/08/2021',
    restTime: '—',
    hoursDuty: '02:45',
    hoursFlight: '01:45',
    status: 'active',
  },
  {
    id: 'AD1093',
    routeFrom: 'GIG',
    routeTo: 'BSB',
    presentationTime: '17:30',
    departureTime: '18:30',
    arrivalTime: '20:15',
    date: '29/08/2021',
    restTime: '—',
    hoursDuty: '02:45',
    hoursFlight: '01:45',
    status: 'active',
  }
];

export const INITIAL_DOCUMENTS: Document[] = [
  {
    id: 'DOC1',
    name: 'Class 1 Medical',
    status: 'VALID',
    code: 'MED-99382-A',
    expiryDate: '15/12/2026',
  },
  {
    id: 'DOC2',
    name: 'ATPL License',
    status: 'VALID',
    code: 'LIC-44810-X',
    expiryDate: '30/09/2028',
  },
  {
    id: 'DOC3',
    name: 'I-94 Visa (USA)',
    status: 'EXPIRING',
    code: 'VISA-I94-USA',
    expiryDate: '12/08/2026',
  }
];

export const INITIAL_CREW: CrewMember[] = [
  { id: 'C1', name: 'Cap. Carlos Mendes', role: 'COMANDANTE' },
  { id: 'C2', name: 'F.O. Juliana Silva', role: 'PRIMEIRO OFICIAL' }
];

export const INITIAL_LODGING: LodgingInfo = {
  hotelName: 'Hilton Rio de Janeiro Copacabana',
  address: 'Av. Atlântica, 1020 - Copacabana, RJ',
  checkIn: '17:30',
  reservationCode: '#AERO-9211'
};

export const INITIAL_OPERATION_LOGS: OperationLog[] = [
  {
    id: 'AV-1092-B',
    saidaHotel: '--:--',
    chegadaAeroporto: '--:--',
    saidaAeroporto: '--:--',
    chegadaHotel: '--:--',
    confirmed: false
  }
];
