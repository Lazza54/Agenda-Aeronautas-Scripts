import React, { useState } from 'react';
import { Document } from '../types';
import { FileText, CheckCircle2, AlertTriangle, XCircle, Calendar, Plus, Trash2, Edit } from 'lucide-react';

interface DocumentListProps {
  documents: Document[];
  onUpdateDocument: (doc: Document) => void;
  onAddDocument: (doc: Document) => void;
  onDeleteDocument: (id: string) => void;
}

export default function DocumentList({
  documents,
  onUpdateDocument,
  onAddDocument,
  onDeleteDocument
}: DocumentListProps) {
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);

  // Form State
  const [name, setName] = useState('');
  const [status, setStatus] = useState<'VALID' | 'EXPIRING' | 'EXPIRED'>('VALID');
  const [code, setCode] = useState('');
  const [expiryDate, setExpiryDate] = useState('');

  // Editing Form State
  const [editName, setEditName] = useState('');
  const [editStatus, setEditStatus] = useState<'VALID' | 'EXPIRING' | 'EXPIRED'>('VALID');
  const [editCode, setEditCode] = useState('');
  const [editExpiryDate, setEditExpiryDate] = useState('');

  const handleStartEdit = (doc: Document) => {
    setEditingDocId(doc.id);
    setEditName(doc.name);
    setEditStatus(doc.status);
    setEditCode(doc.code || '');
    setEditExpiryDate(doc.expiryDate);
  };

  const handleSaveEdit = (id: string) => {
    onUpdateDocument({
      id,
      name: editName,
      status: editStatus,
      code: editCode,
      expiryDate: editExpiryDate
    });
    setEditingDocId(null);
  };

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onAddDocument({
      id: 'DOC_' + Date.now(),
      name,
      status,
      code,
      expiryDate: expiryDate || '—'
    });
    setName('');
    setCode('');
    setExpiryDate('');
    setShowAddForm(false);
  };

  const getStatusBadge = (status: Document['status']) => {
    switch (status) {
      case 'VALID':
        return (
          <span className="font-mono text-[10px] px-2 py-0.5 bg-green-500/10 text-valid-green border border-green-500/30 rounded font-bold uppercase tracking-wider">
            VALID
          </span>
        );
      case 'EXPIRING':
        return (
          <span className="font-mono text-[10px] px-2 py-0.5 bg-orange-500/10 text-warn-orange border border-orange-500/30 rounded font-bold uppercase tracking-wider">
            EXPIRING
          </span>
        );
      case 'EXPIRED':
        return (
          <span className="font-mono text-[10px] px-2 py-0.5 bg-red-500/10 text-expiring-red border border-red-500/30 rounded font-bold uppercase tracking-wider">
            EXPIRED
          </span>
        );
    }
  };

  return (
    <section id="required-documents" className="bg-surface-card border border-outline-tactical p-md rounded-lg glow-gold">
      <div className="flex items-center justify-between mb-md border-b border-outline-tactical/50 pb-sm">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-primary" />
          <h2 className="font-mono text-xs font-bold text-text-muted uppercase tracking-widest">
            REQUIRED DOCUMENTS
          </h2>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1 text-[11px] font-mono font-bold text-primary hover:text-primary-hover active:scale-95 transition-all"
        >
          <Plus size={14} /> ADD NEW
        </button>
      </div>

      {/* Add Document Form */}
      {showAddForm && (
        <form onSubmit={handleCreate} className="mb-md p-sm bg-surface-container border border-outline-tactical rounded space-y-sm">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-sm">
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">DOCUMENT NAME</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Class 1 Medical"
                required
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-sm text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">STATUS</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as any)}
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-sm text-text-bright focus:border-primary focus:outline-none"
              >
                <option value="VALID">VALID</option>
                <option value="EXPIRING">EXPIRING</option>
                <option value="EXPIRED">EXPIRED</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">DOCUMENT CODE / ID</label>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="e.g. MED-882-X"
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-sm text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono text-text-muted mb-1">EXPIRY DATE</label>
              <input
                type="text"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                placeholder="e.g. 15/12/2026"
                className="w-full bg-bg-dark border border-outline-tactical rounded p-2 text-sm text-text-bright focus:border-primary focus:outline-none"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-outline-tactical/30">
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="text-[11px] font-mono px-3 py-1 bg-surface-low hover:bg-zinc-800 text-text-muted border border-outline-tactical rounded"
            >
              CANCEL
            </button>
            <button
              type="submit"
              className="text-[11px] font-mono px-3 py-1 bg-primary text-on-primary hover:bg-primary-hover font-bold rounded"
            >
              SAVE DOCUMENT
            </button>
          </div>
        </form>
      )}

      {/* Documents List */}
      <div className="space-y-sm">
        {documents.map((doc) => {
          const isEditing = editingDocId === doc.id;
          return (
            <div
              key={doc.id}
              className="flex flex-col p-sm border border-outline-tactical/40 hover:border-outline-tactical bg-surface-low rounded transition-all"
            >
              {isEditing ? (
                <div className="space-y-sm">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-sm">
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="bg-bg-dark border border-outline-tactical rounded p-1 text-xs text-text-bright"
                    />
                    <select
                      value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value as any)}
                      className="bg-bg-dark border border-outline-tactical rounded p-1 text-xs text-text-bright"
                    >
                      <option value="VALID">VALID</option>
                      <option value="EXPIRING">EXPIRING</option>
                      <option value="EXPIRED">EXPIRED</option>
                    </select>
                    <input
                      type="text"
                      value={editCode}
                      placeholder="Code"
                      onChange={(e) => setEditCode(e.target.value)}
                      className="bg-bg-dark border border-outline-tactical rounded p-1 text-xs text-text-bright"
                    />
                    <input
                      type="text"
                      value={editExpiryDate}
                      placeholder="Expiry"
                      onChange={(e) => setEditExpiryDate(e.target.value)}
                      className="bg-bg-dark border border-outline-tactical rounded p-1 text-xs text-text-bright"
                    />
                  </div>
                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      onClick={() => setEditingDocId(null)}
                      className="text-[10px] font-mono px-2 py-0.5 bg-zinc-900 text-text-muted rounded"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleSaveEdit(doc.id)}
                      className="text-[10px] font-mono px-2 py-0.5 bg-primary text-on-primary rounded font-bold"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-sm">
                  <div className="flex items-center gap-3">
                    <div className="text-primary bg-primary/5 p-2 rounded-full border border-outline-gold/25">
                      <FileText size={16} />
                    </div>
                    <div>
                      <h3 className="font-mono text-sm text-text-bright font-semibold">
                        {doc.name}
                      </h3>
                      <div className="flex items-center gap-2 mt-0.5 text-[11px] text-text-muted font-mono">
                        {doc.code && <span>ID: {doc.code}</span>}
                        {doc.code && doc.expiryDate && <span>•</span>}
                        {doc.expiryDate && (
                          <span className="flex items-center gap-1">
                            <Calendar size={10} /> Exp: {doc.expiryDate}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-3">
                    {getStatusBadge(doc.status)}
                    <div className="flex gap-1 opacity-0 hover:opacity-100 focus-within:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleStartEdit(doc)}
                        className="p-1 hover:text-primary text-text-muted active:scale-95 transition-transform"
                        title="Edit Document"
                      >
                        <Edit size={12} />
                      </button>
                      <button
                        onClick={() => onDeleteDocument(doc.id)}
                        className="p-1 hover:text-expiring-red text-text-muted active:scale-95 transition-transform"
                        title="Delete Document"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {documents.length === 0 && (
          <div className="text-center py-6 border border-dashed border-outline-tactical/30 rounded text-text-muted font-mono text-xs">
            Nenhum documento cadastrado.
          </div>
        )}
      </div>
    </section>
  );
}
