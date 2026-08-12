import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { Subject } from '../types';

interface Props {
  onClose: () => void;
  onCreated: (subject: Subject) => void;
  threadId?: string | null;
  provider?: string;
  model?: string;
}

const TYPES = ['person', 'company', 'organization', 'domain', 'account', 'location', 'event', 'other'];

export const CreateSubjectModal: React.FC<Props> = ({ onClose, onCreated, threadId, provider, model }) => {
  const [form, setForm] = useState({ name: '', subject_type: 'person', canonical_identifier: '', aliases: '', identifiers: '', description: '', investigation_goals: '' });
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(Boolean(threadId));
  const [error, setError] = useState('');

  useEffect(() => {
    if (!threadId) return;
    let cancelled = false;
    const generateDraft = async () => {
      setGenerating(true);
      setError('');
      try {
        const response = await fetch(`/api/threads/${threadId}/subject-draft`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider, model_name: model }),
        });
        const draft = await response.json();
        if (!response.ok) throw new Error(draft.detail || 'Unable to generate subject draft');
        if (!cancelled) {
          setForm({
            name: draft.name || '',
            subject_type: draft.subject_type || 'other',
            canonical_identifier: draft.canonical_identifier || '',
            aliases: (draft.aliases || []).join(', '),
            identifiers: (draft.identifiers || []).join(', '),
            description: draft.description || '',
            investigation_goals: draft.investigation_goals || '',
          });
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Unable to generate subject draft');
      } finally {
        if (!cancelled) setGenerating(false);
      }
    };
    generateDraft();
    return () => { cancelled = true; };
  }, [threadId, provider, model]);

  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const response = await fetch(threadId ? `/api/threads/${threadId}/subject` : '/api/subjects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, aliases: form.aliases.split(',').map((value) => value.trim()).filter(Boolean), identifiers: form.identifiers.split(',').map((value) => value.trim()).filter(Boolean) }),
      });
      if (!response.ok) throw new Error('Unable to create subject');
      onCreated(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create subject');
    } finally {
      setSaving(false);
    }
  };

  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="create-subject-title">
    <form onSubmit={create} className="w-full max-w-xl border border-border-dark bg-panel-dark p-6 shadow-2xl">
      <div className="flex items-start justify-between border-b border-border-dark pb-4"><div><div className="text-[10px] font-bold uppercase tracking-widest text-accent-blue">Subject intake</div><h2 id="create-subject-title" className="mt-2 text-lg font-semibold text-slate-100">New investigation subject</h2></div><button type="button" onClick={onClose} className="p-2 text-slate-500 hover:text-slate-200" title="Close"><X size={17} /></button></div>
      {threadId && <div className="mt-4 border border-accent-blue/20 bg-accent-blue/5 px-3 py-2 text-xs text-slate-400">{generating ? 'Reading the conversation to prepare a subject draft...' : 'Draft generated from this thread. Review the fields before creating the subject.'}</div>}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="sm:col-span-2"><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Name</span><input required disabled={generating} value={form.name} onChange={(event) => update('name', event.target.value)} className="min-h-11 w-full border border-border-dark bg-slate-950 px-3 text-sm text-slate-200 outline-none focus:border-accent-blue disabled:opacity-50" autoFocus /></label>
        <label><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Type</span><select value={form.subject_type} onChange={(event) => update('subject_type', event.target.value)} className="min-h-11 w-full border border-border-dark bg-slate-950 px-3 text-sm text-slate-200 outline-none focus:border-accent-blue">{TYPES.map((type) => <option key={type}>{type}</option>)}</select></label>
        <label><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Canonical identifier</span><input value={form.canonical_identifier} onChange={(event) => update('canonical_identifier', event.target.value)} placeholder="Primary URL, handle, or ID" className="min-h-11 w-full border border-border-dark bg-slate-950 px-3 text-sm text-slate-200 outline-none focus:border-accent-blue placeholder:text-slate-700" /></label>
        <label><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Aliases</span><input value={form.aliases} onChange={(event) => update('aliases', event.target.value)} placeholder="Comma-separated" className="min-h-11 w-full border border-border-dark bg-slate-950 px-3 text-sm text-slate-200 outline-none focus:border-accent-blue placeholder:text-slate-700" /></label>
        <label><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Other identifiers</span><input value={form.identifiers} onChange={(event) => update('identifiers', event.target.value)} placeholder="Comma-separated" className="min-h-11 w-full border border-border-dark bg-slate-950 px-3 text-sm text-slate-200 outline-none focus:border-accent-blue placeholder:text-slate-700" /></label>
        <label className="sm:col-span-2"><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Description</span><textarea value={form.description} onChange={(event) => update('description', event.target.value)} rows={3} className="w-full resize-y border border-border-dark bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-accent-blue" /></label>
        <label className="sm:col-span-2"><span className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Investigation goals</span><textarea value={form.investigation_goals} onChange={(event) => update('investigation_goals', event.target.value)} rows={3} className="w-full resize-y border border-border-dark bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-accent-blue" /></label>
      </div>
      {error && <p className="mt-4 text-xs text-red-400">{error}</p>}
      <div className="mt-6 flex justify-end gap-2 border-t border-border-dark pt-4"><button type="button" onClick={onClose} className="min-h-11 px-4 text-xs font-semibold text-slate-500 hover:text-slate-200">Cancel</button><button disabled={saving || generating || !form.name.trim()} className="min-h-11 bg-accent-blue px-5 text-xs font-bold text-slate-950 disabled:opacity-50">{generating ? 'Preparing draft...' : saving ? 'Creating...' : 'Create subject'}</button></div>
    </form>
  </div>;
};
