export interface Flight {
  id: string; // e.g., AD4372
  routeFrom: string; // e.g., VCP
  routeTo: string; // e.g., SSA
  presentationTime: string; // e.g., 22:40
  departureTime: string; // e.g., 23:40
  arrivalTime: string; // e.g., 02:00
  date: string; // e.g., 29/08/2021
  restTime: string; // e.g., 12:45 or "—"
  hoursDuty: string; // e.g., "07:05"
  hoursFlight: string; // e.g., "04:45"
  status: 'scheduled' | 'completed' | 'active';
}

export interface Document {
  id: string;
  name: string;
  status: 'VALID' | 'EXPIRING' | 'EXPIRED';
  code?: string;
  expiryDate: string;
}

export interface CrewMember {
  id: string;
  name: string;
  role: string; // COMANDANTE, PRIMEIRO OFICIAL, COMISSÁRIO
}

export interface LodgingInfo {
  hotelName: string;
  address: string;
  checkIn: string;
  reservationCode: string;
}

export interface OperationLog {
  id: string; // match Flight id
  saidaHotel: string; // e.g., "13:15"
  chegadaAeroporto: string; // e.g., "14:00"
  saidaAeroporto: string;
  chegadaHotel: string;
  confirmed: boolean;
  confirmedAt?: string;
}

export type TabType = 'flights' | 'details' | 'reports' | 'profile';
