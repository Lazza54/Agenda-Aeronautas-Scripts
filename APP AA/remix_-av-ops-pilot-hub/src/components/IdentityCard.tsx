import React, { useState } from 'react';
import { Clock, User } from 'lucide-react';

interface IdentityCardProps {
  pilotName: string;
  rank: string;
  idCode: string;
  dutyHours: string;
  isActive: boolean;
  onUpdateEscala?: () => void;
}

export default function IdentityCard({
  pilotName = 'CAPTAIN J. MILLER',
  rank = 'CDR',
  idCode = '8824-H6-LX',
  dutyHours = '12,450.5 FT',
  isActive = true,
  onUpdateEscala
}: IdentityCardProps) {
  const [imageError, setImageError] = useState(false);
  const portraitUrl = 'https://lh3.googleusercontent.com/aida-public/AB6AXuAkCSWfCLwRlOSaw5X1-KNdlANpD9Hlf9Odtk6GCnOYHFxOdZ4cpdsI_NLGKR4t7RM0YV4qhS-fKocfFKwCkoaHeKRxulHtoO-fQzRVQ6B_6lNRF36M4Oqbp6mMJKUK54985LQgAWtZbYG5k6b4aSKsndDb4Wp_4YWuzvMZhzexeqmXejBZKOeyZYrIW3_TTPwd7qWOzP_WQK3WqNXjAeIWlOqJ26mKe8pYoc9IdcbCJiJFrL063pnvvZzgHyA_Iu_ENGDaim-JWgU';

  return (
    <section id="identity-card" className="bg-surface-card border border-outline-tactical p-md rounded-lg glow-gold relative overflow-hidden transition-all hover:border-primary/40 duration-300">
      <div className="absolute top-0 left-0 w-1 h-full bg-primary" />
      <div className="flex gap-md items-center sm:items-start">
        {/* Pilot Portrait */}
        <div className="w-24 h-24 sm:w-28 sm:h-28 bg-surface-container border border-outline-tactical flex-shrink-0 relative overflow-hidden rounded">
          {!imageError ? (
            <img
              className="w-full h-full object-cover grayscale brightness-90 contrast-125"
              src={portraitUrl}
              alt="Captain J. Miller Pilot Portrait"
              referrerPolicy="no-referrer"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center bg-zinc-900 text-primary">
              <User size={40} className="stroke-[1.5]" />
              <span className="text-[9px] font-mono mt-1">PILOT</span>
            </div>
          )}
          
          {isActive && (
            <div className="absolute bottom-0 right-0 bg-primary text-on-primary px-1 text-[10px] font-bold font-mono tracking-tighter">
              ACTV
            </div>
          )}
        </div>

        {/* Info Column */}
        <div className="flex flex-col justify-between py-1 flex-grow">
          <div>
            <p className="font-mono text-[11px] text-primary uppercase tracking-widest font-bold">
              RANK: {rank}
            </p>
            <h1 className="font-sans text-lg sm:text-2xl font-extrabold text-text-bright leading-none mt-1 uppercase tracking-tight">
              {pilotName}
            </h1>
          </div>
          
          <div className="space-y-1 mt-3">
            <p className="font-mono text-xs text-text-muted">
              ID: {idCode}
            </p>
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-primary" />
              <p className="font-mono text-sm text-primary font-bold">
                {dutyHours}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
