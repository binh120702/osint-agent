import React, { useEffect, useState } from 'react';
import { Check, Link, Plus, RefreshCw, ShieldCheck, Sparkles, X } from 'lucide-react';
import type { Subject, SubjectEvidence } from '../types';

interface Props {
  subjects: Subject[];
  selectedSubjectId: string | null;
  onSelect: (id: string | null) => void;
  onCreated: (subject: Subject) => void;
  onEvidenceChanged: () => void;
  currentThreadId?: string | null;
  onCreateSubjectFromThread?: () => void;
  onAttachSubjectToThread?: (subjectId: string) => Promise<void>;
}

const TYPES = ['person', 'company', 'organization', 'domain', 'account', 'location', 'event', 'other'];

export const SubjectBar: React.FC<Props> = ({ subjects, selectedSubjectId, onSelect, onCreated, onEvidenceChanged, currentThreadId, onCreateSubjectFromThread, onAttachSubjectToThread }) => {
  const [showCreate, setShowCreate] = useState(false);
  const [showAttach, setShowAttach] = useState(false);
  const [attachId, setAttachId] = useState('');
  const [attaching, setAttaching] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [evidence, setEvidence] = useState<SubjectEvidence[]>([]);
  const [form, setForm] = useState({ name: '', subject_type: 'person', canonical_identifier: '', aliases: '', identifiers: '', description: '', investigation_goals: '' });
  const selected = subjects.find((s) => s.subject_id === selectedSubjectId);

  useEffect(() => {
    if (!selectedSubjectId || !showEvidence) return;
    fetch(`/api/subjects/${selectedSubjectId}/evidence`).then((r) => r.json()).then((data) => setEvidence(Array.isArray(data) ? data : [])).catch(console.error);
  }, [selectedSubjectId, showEvidence]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    const response = await fetch('/api/subjects', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, aliases: form.aliases.split(',').map((v) => v.trim()).filter(Boolean), identifiers: form.identifiers.split(',').map((v) => v.trim()).filter(Boolean) }),
    });
    if (!response.ok) return;
    const subject = await response.json();
    onCreated(subject); onSelect(subject.subject_id); setShowCreate(false);
    setForm({ name: '', subject_type: 'person', canonical_identifier: '', aliases: '', identifiers: '', description: '', investigation_goals: '' });
  };

  const review = async (item: SubjectEvidence, status: SubjectEvidence['status']) => {
    await fetch(`/api/subjects/${selectedSubjectId}/evidence/${item.evidence_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
    });
    setEvidence((items) => items.map((v) => v.evidence_id === item.evidence_id ? { ...v, status } : v));
    onEvidenceChanged();
  };

  const attach = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!attachId || !onAttachSubjectToThread) return;
    setAttaching(true);
    try {
      await onAttachSubjectToThread(attachId);
      setShowAttach(false);
      setAttachId('');
    } finally {
      setAttaching(false);
    }
  };

  return <>
    <div className="border-b border-border-dark bg-panel-dark px-4 py-2 flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Subject</span>
      <select value={selectedSubjectId || ''} onChange={(e) => onSelect(e.target.value || null)} className="flex-1 max-w-md bg-slate-950 border border-border-dark text-slate-300 text-xs px-2 py-1.5">
        <option value="">Choose an investigation subject...</option>
        {subjects.map((s) => <option key={s.subject_id} value={s.subject_id}>{s.name} · {s.subject_type}</option>)}
      </select>
      <button onClick={() => setShowCreate(true)} className="p-1.5 border border-border-dark text-slate-400 hover:text-white" title="Create subject"><Plus size={14} /></button>
      {!selected && currentThreadId && onAttachSubjectToThread && <button onClick={() => setShowAttach(true)} className="flex items-center gap-1.5 border border-border-dark px-2 py-1.5 text-xs font-semibold text-slate-400 hover:border-slate-500 hover:text-slate-200" title="Attach this thread to an existing subject"><Link size={13} /> Add to subject</button>}
      {selected && currentThreadId && onAttachSubjectToThread && <button onClick={() => void onAttachSubjectToThread(selected.subject_id)} className="flex items-center gap-1.5 border border-border-dark px-2 py-1.5 text-xs font-semibold text-slate-400 hover:border-slate-500 hover:text-slate-200" title="Import findings from this thread into the subject"><RefreshCw size={13} /> Sync findings</button>}
      {!selected && currentThreadId && onCreateSubjectFromThread && <button onClick={onCreateSubjectFromThread} className="flex items-center gap-1.5 border border-accent-blue/40 bg-accent-blue/10 px-2 py-1.5 text-xs font-semibold text-accent-blue" title="Generate a subject from this thread"><Sparkles size={13} /> Create subject from thread</button>}
      {selected && <button onClick={() => setShowEvidence(!showEvidence)} className="px-2 py-1.5 border border-border-dark text-xs text-slate-400 hover:text-white flex items-center gap-1"><ShieldCheck size={13} /> Evidence</button>}
    </div>
    {showEvidence && selected && <div className="absolute z-20 right-80 top-12 w-[420px] max-h-[70vh] overflow-y-auto bg-panel-dark border border-border-dark shadow-xl p-3">
      <div className="flex justify-between items-center mb-2"><h3 className="text-xs font-bold text-slate-200">Evidence inbox · {selected.name}</h3><button onClick={() => setShowEvidence(false)}><X size={14} /></button></div>
      {evidence.length === 0 ? <p className="text-xs text-slate-500">No evidence has been extracted yet.</p> : evidence.map((item) => <div key={item.evidence_id} className="border border-border-dark/60 p-2 mb-2 text-xs">
        <p className="text-slate-300">{item.claim}</p><p className="text-[10px] text-slate-500 mt-1">{item.source_url || item.source_title || 'No source recorded'} · {item.status}</p>
        {item.status === 'pending' && <div className="flex gap-1 mt-2"><button onClick={() => review(item, 'confirmed')} className="px-2 py-1 bg-emerald-500/10 text-emerald-400 flex items-center gap-1"><Check size={12} /> Confirm</button><button onClick={() => review(item, 'rejected')} className="px-2 py-1 bg-red-500/10 text-red-400"><X size={12} /> Reject</button></div>}
      </div>)}
    </div>}
    {showAttach && <div className="fixed inset-0 z-30 bg-black/60 flex items-center justify-center p-4"><form onSubmit={attach} className="w-full max-w-sm bg-panel-dark border border-border-dark p-5 space-y-4">
      <div className="flex justify-between items-center"><div><h2 className="text-sm font-bold text-slate-100">Add thread to subject</h2><p className="mt-1 text-xs text-slate-500">Continue this thread under an existing investigation.</p></div><button type="button" onClick={() => setShowAttach(false)} title="Close"><X size={16} /></button></div>
      <select required value={attachId} onChange={(e) => setAttachId(e.target.value)} className="w-full bg-slate-950 border border-border-dark px-3 py-2 text-xs text-slate-200"><option value="">Choose a subject...</option>{subjects.map((subject) => <option key={subject.subject_id} value={subject.subject_id}>{subject.name} · {subject.subject_type}</option>)}</select>
      <div className="flex justify-end gap-2"><button type="button" onClick={() => setShowAttach(false)} className="px-3 py-2 text-xs text-slate-400">Cancel</button><button disabled={attaching} className="flex items-center gap-1.5 bg-accent-blue px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"><Link size={13} /> {attaching ? 'Adding...' : 'Add subject'}</button></div>
    </form></div>}
    {showCreate && <div className="fixed inset-0 z-30 bg-black/60 flex items-center justify-center p-4"><form onSubmit={create} className="w-full max-w-lg bg-panel-dark border border-border-dark p-5 space-y-3">
      <div className="flex justify-between"><h2 className="text-sm font-bold text-slate-100">New Investigation Subject</h2><button type="button" onClick={() => setShowCreate(false)}><X size={16} /></button></div>
      {([['name', 'Name'], ['canonical_identifier', 'Canonical identifier'], ['aliases', 'Aliases (comma-separated)'], ['identifiers', 'Other identifiers (comma-separated)'], ['description', 'Description'], ['investigation_goals', 'Investigation goals']] as const).map(([key, label]) => <input key={key} required={key === 'name'} value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} placeholder={label} className="w-full bg-slate-950 border border-border-dark px-3 py-2 text-xs text-slate-200" />)}
      <select value={form.subject_type} onChange={(e) => setForm({ ...form, subject_type: e.target.value })} className="w-full bg-slate-950 border border-border-dark px-3 py-2 text-xs text-slate-200">{TYPES.map((type) => <option key={type}>{type}</option>)}</select>
      <div className="flex justify-end gap-2"><button type="button" onClick={() => setShowCreate(false)} className="px-3 py-2 text-xs text-slate-400">Cancel</button><button className="px-3 py-2 bg-accent-blue text-white text-xs">Create subject</button></div>
    </form></div>}
  </>;
};
