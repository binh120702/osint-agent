import React, { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowRight, Check, CheckCircle2, CircleDot, Clock3, ExternalLink, Plus, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import type { Subject, SubjectEvidence } from '../types';
import type { Thread } from '../types';
import { ThreadBrowser } from './ThreadBrowser';

interface SubjectProgress {
  confirmed: number;
  pending: number;
  rejected: number;
  total: number;
}

interface Props {
  subjects: Subject[];
  onCreateSubject: () => void;
  onStartThread: (subject: Subject) => void;
  onToggleStatus: (subject: Subject) => void;
  onRefresh: () => void;
  loading?: boolean;
  activeTab: 'subjects' | 'threads';
  onTabChange: (tab: 'subjects' | 'threads') => void;
  threads: Thread[];
  onSelectThread: (id: string) => void;
  onDeleteThread: (id: string) => void;
  onNewThread: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  person: 'Person',
  company: 'Company',
  organization: 'Organization',
  domain: 'Domain',
  account: 'Account',
  location: 'Location',
  event: 'Event',
  other: 'Other',
};

const formatDate = (value: string) => new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value));
const formatProposedValue = (value?: string) => {
  if (!value) return '';
  try {
    const parsed = JSON.parse(value);
    return typeof parsed === 'string' ? parsed : JSON.stringify(parsed);
  } catch {
    return value;
  }
};

export const InvestigationHome: React.FC<Props> = ({ subjects, onCreateSubject, onStartThread, onToggleStatus, onRefresh, loading, activeTab, onTabChange, threads, onSelectThread, onDeleteThread, onNewThread }) => {
  const [progress, setProgress] = useState<Record<string, SubjectProgress>>({});
  const [progressLoading, setProgressLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [evidenceSubject, setEvidenceSubject] = useState<Subject | null>(null);
  const [evidence, setEvidence] = useState<SubjectEvidence[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceFilter, setEvidenceFilter] = useState<'all' | SubjectEvidence['status']>('all');
  const [evidenceRefresh, setEvidenceRefresh] = useState(0);

  const activeSubjects = useMemo(() => subjects.filter((subject) => subject.status !== 'done'), [subjects]);
  const completedSubjects = useMemo(() => subjects.filter((subject) => subject.status === 'done'), [subjects]);
  const visibleActive = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return activeSubjects;
    return activeSubjects.filter((subject) => `${subject.name} ${subject.subject_type} ${subject.canonical_identifier || ''}`.toLowerCase().includes(normalized));
  }, [activeSubjects, query]);

  useEffect(() => {
    let cancelled = false;
    const loadProgress = async () => {
      if (activeSubjects.length === 0) {
        setProgress({});
        return;
      }
      setProgressLoading(true);
      const entries = await Promise.all(activeSubjects.map(async (subject) => {
        try {
          const response = await fetch(`/api/subjects/${subject.subject_id}/evidence`);
          const evidence: SubjectEvidence[] = response.ok ? await response.json() : [];
          return [subject.subject_id, {
            confirmed: evidence.filter((item) => item.status === 'confirmed').length,
            pending: evidence.filter((item) => item.status === 'pending').length,
            rejected: evidence.filter((item) => item.status === 'rejected').length,
            total: evidence.length,
          }] as const;
        } catch {
          return [subject.subject_id, { confirmed: 0, pending: 0, rejected: 0, total: 0 }] as const;
        }
      }));
      if (!cancelled) {
        setProgress(Object.fromEntries(entries));
        setProgressLoading(false);
      }
    };
    loadProgress();
    return () => { cancelled = true; };
  }, [activeSubjects, evidenceRefresh]);

  useEffect(() => {
    let cancelled = false;
    if (!evidenceSubject) {
      setEvidence([]);
      return;
    }
    setEvidenceLoading(true);
    fetch(`/api/subjects/${evidenceSubject.subject_id}/evidence`)
      .then((response) => response.ok ? response.json() : [])
      .then((data) => { if (!cancelled) setEvidence(Array.isArray(data) ? data : []); })
      .catch(() => { if (!cancelled) setEvidence([]); })
      .finally(() => { if (!cancelled) setEvidenceLoading(false); });
    return () => { cancelled = true; };
  }, [evidenceSubject, evidenceRefresh]);

  const openEvidence = (subject: Subject) => {
    setEvidenceSubject(subject);
    setEvidenceFilter('all');
  };

  const reviewEvidence = async (item: SubjectEvidence, status: SubjectEvidence['status']) => {
    if (!evidenceSubject) return;
    const response = await fetch(`/api/subjects/${evidenceSubject.subject_id}/evidence/${item.evidence_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) return;
    setEvidence((items) => items.map((value) => value.evidence_id === item.evidence_id ? { ...value, status } : value));
    setEvidenceRefresh((value) => value + 1);
  };

  const visibleEvidence = evidenceFilter === 'all' ? evidence : evidence.filter((item) => item.status === evidenceFilter);

  const totals = activeSubjects.reduce((summary, subject) => {
    const item = progress[subject.subject_id] || { confirmed: 0, pending: 0, rejected: 0, total: 0 };
    summary.threads += subject.thread_ids.length;
    summary.confirmed += item.confirmed;
    summary.pending += item.pending;
    return summary;
  }, { threads: 0, confirmed: 0, pending: 0 });

  return (
    <main className="h-screen overflow-y-auto bg-bg-dark text-slate-100">
      <div className="mx-auto max-w-[1440px] px-5 py-6 sm:px-8 lg:px-12 lg:py-10">
        <header className="flex flex-col gap-6 border-b border-border-dark pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-4 flex items-center gap-3 text-[11px] font-bold uppercase tracking-[0.2em] text-accent-blue">
              <span className="h-2 w-2 bg-accent-blue" />
              OSINT Agent / Workspace
            </div>
            <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">Investigation subjects</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Choose a subject to continue an investigation or open a fresh research thread.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onRefresh} className="flex min-h-11 items-center gap-2 border border-border-dark px-3 text-xs font-semibold text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200" title="Refresh subjects">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
            <button onClick={onCreateSubject} className="flex min-h-11 items-center gap-2 bg-accent-blue px-4 text-xs font-bold text-slate-950 transition-colors hover:bg-emerald-300">
              <Plus size={15} /> New subject
            </button>
          </div>
        </header>

        <nav className="mt-6 flex gap-1 border-b border-border-dark" aria-label="Workspace sections">
          <button onClick={() => onTabChange('subjects')} className={`min-h-11 border-b-2 px-4 text-xs font-bold transition-colors ${activeTab === 'subjects' ? 'border-accent-blue text-accent-blue' : 'border-transparent text-slate-500 hover:text-slate-200'}`}>Subjects <span className="ml-1 text-[10px] opacity-60">{subjects.length}</span></button>
          <button onClick={() => onTabChange('threads')} className={`min-h-11 border-b-2 px-4 text-xs font-bold transition-colors ${activeTab === 'threads' ? 'border-accent-blue text-accent-blue' : 'border-transparent text-slate-500 hover:text-slate-200'}`}>Threads <span className="ml-1 text-[10px] opacity-60">{threads.length}</span></button>
        </nav>

        {activeTab === 'threads' ? <ThreadBrowser threads={threads} subjects={subjects} onSelectThread={onSelectThread} onDeleteThread={onDeleteThread} onNewThread={onNewThread} /> : <>

        <section className="grid gap-px border-x border-b border-border-dark bg-border-dark sm:grid-cols-3" aria-label="Active investigation summary">
          <div className="bg-panel-dark px-5 py-4"><div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Active subjects</div><div className="mt-2 text-2xl font-semibold text-slate-100">{activeSubjects.length}</div></div>
          <div className="bg-panel-dark px-5 py-4"><div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Research threads</div><div className="mt-2 text-2xl font-semibold text-slate-100">{totals.threads}</div></div>
          <div className="bg-panel-dark px-5 py-4"><div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Confirmed findings</div><div className="mt-2 text-2xl font-semibold text-emerald-400">{totals.confirmed}<span className="ml-2 text-xs font-normal text-slate-500">+ {totals.pending} pending</span></div></div>
        </section>

        <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div><div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><Activity size={16} className="text-accent-blue" /> Active investigations</div><div className="mt-1 text-xs text-slate-500">{activeSubjects.length ? 'Progress is based on linked threads and reviewed evidence.' : 'Create your first subject to begin.'}</div></div>
          <label className="flex min-h-11 items-center gap-2 border border-border-dark bg-panel-dark px-3 text-slate-500 focus-within:border-accent-blue/70 sm:w-72"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter subjects" className="w-full bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-600" /></label>
        </div>

        {visibleActive.length === 0 ? (
          <div className="mt-5 border border-dashed border-border-dark bg-panel-dark/60 px-6 py-14 text-center"><CircleDot size={24} className="mx-auto text-slate-600" /><h2 className="mt-4 text-sm font-semibold text-slate-300">{activeSubjects.length ? 'No subjects match this filter' : 'No active subjects yet'}</h2><p className="mt-2 text-xs text-slate-500">{activeSubjects.length ? 'Try a different name or identifier.' : 'Add an investigation subject to create your first thread.'}</p>{!activeSubjects.length && <button onClick={onCreateSubject} className="mt-5 inline-flex min-h-11 items-center gap-2 bg-accent-blue px-4 text-xs font-bold text-slate-950"><Plus size={14} /> Create subject</button>}</div>
        ) : (
          <div className="mt-5 grid gap-3 xl:grid-cols-2">
            {visibleActive.map((subject) => {
              const item = progress[subject.subject_id] || { confirmed: 0, pending: 0, rejected: 0, total: 0 };
              const completion = item.total ? Math.round((item.confirmed / item.total) * 100) : 0;
              return <article key={subject.subject_id} className="group border border-border-dark bg-panel-dark p-5 transition-colors hover:border-slate-600">
                <div className="flex items-start justify-between gap-4"><div><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-accent-blue"><span className="h-1.5 w-1.5 bg-accent-blue" /> {TYPE_LABELS[subject.subject_type] || subject.subject_type}</div><h2 className="mt-2 text-xl font-semibold text-slate-100">{subject.name}</h2>{subject.canonical_identifier && <div className="mt-1 font-mono text-[11px] text-slate-500">{subject.canonical_identifier}</div>}</div><span className="border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-400">Active</span></div>
                {subject.description && <p className="mt-5 line-clamp-2 text-xs leading-5 text-slate-400">{subject.description}</p>}
                <div className="mt-6 border-t border-border-dark pt-4"><div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-500"><span>Evidence reviewed</span><span className="text-slate-300">{progressLoading ? 'Loading' : `${completion}%`}</span></div><div className="mt-2 h-1.5 bg-slate-900"><div className="h-full bg-accent-blue transition-all" style={{ width: `${completion}%` }} /></div><div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-slate-500"><span className="flex items-center gap-1.5 text-emerald-400"><ShieldCheck size={13} /> {item.confirmed} confirmed</span><span className="flex items-center gap-1.5"><Clock3 size={13} /> {item.pending} pending</span><span>{subject.thread_ids.length} {subject.thread_ids.length === 1 ? 'thread' : 'threads'}</span></div></div>
                <div className="mt-5 flex items-center justify-between gap-3"><div className="flex items-center gap-1"><button onClick={() => openEvidence(subject)} className="flex min-h-10 items-center gap-1.5 border border-border-dark px-2 text-[11px] font-semibold text-slate-400 hover:border-slate-500 hover:text-slate-100"><ShieldCheck size={13} /> Review evidence</button><button onClick={() => onToggleStatus(subject)} className="min-h-10 px-2 text-[11px] font-semibold text-slate-500 hover:text-emerald-400">Mark done</button></div><button onClick={() => onStartThread(subject)} className="flex min-h-10 items-center gap-2 bg-slate-100 px-4 text-xs font-bold text-slate-950 transition-colors hover:bg-white">New thread <ArrowRight size={14} /></button></div>
              </article>;
            })}
          </div>
        )}

        {completedSubjects.length > 0 && <section className="mt-12 border-t border-border-dark pt-6"><div className="flex items-center gap-2 text-sm font-semibold text-slate-300"><CheckCircle2 size={16} className="text-slate-500" /> Completed subjects <span className="text-xs font-normal text-slate-600">{completedSubjects.length}</span></div><div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{completedSubjects.map((subject) => <div key={subject.subject_id} className="flex items-center justify-between gap-3 border border-border-dark/70 bg-panel-dark/50 px-4 py-3"><div><div className="text-sm font-semibold text-slate-400">{subject.name}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-slate-600">Completed {formatDate(subject.updated_at)}</div></div><div className="flex items-center gap-1"><button onClick={() => openEvidence(subject)} className="flex min-h-9 items-center gap-1.5 px-2 text-[11px] font-semibold text-slate-500 hover:text-slate-200"><ShieldCheck size={13} /> Evidence</button><button onClick={() => onToggleStatus(subject)} className="min-h-9 px-2 text-[11px] font-semibold text-slate-500 hover:text-accent-blue">Reopen</button></div></div>)}</div></section>}
        </>}
      </div>
      {evidenceSubject && <div className="fixed inset-0 z-30 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-8" role="dialog" aria-modal="true" aria-label={`Evidence for ${evidenceSubject.name}`}>
        <section className="w-full max-w-3xl border border-border-dark bg-panel-dark shadow-2xl">
          <header className="flex items-start justify-between gap-4 border-b border-border-dark px-5 py-4"><div><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-accent-blue"><ShieldCheck size={14} /> Subject evidence</div><h2 className="mt-2 text-lg font-semibold text-slate-100">{evidenceSubject.name}</h2><p className="mt-1 text-xs text-slate-500">Review findings from all threads linked to this subject.</p></div><button onClick={() => setEvidenceSubject(null)} className="p-1 text-slate-500 hover:text-slate-100" title="Close evidence"><X size={18} /></button></header>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-dark px-5 py-3"><div className="flex gap-1" role="tablist" aria-label="Evidence status"><button onClick={() => setEvidenceFilter('all')} className={`px-2 py-1.5 text-[11px] font-semibold ${evidenceFilter === 'all' ? 'bg-slate-100 text-slate-950' : 'text-slate-500 hover:text-slate-200'}`}>All {evidence.length}</button>{(['pending', 'confirmed', 'rejected'] as const).map((status) => <button key={status} onClick={() => setEvidenceFilter(status)} className={`px-2 py-1.5 text-[11px] font-semibold capitalize ${evidenceFilter === status ? 'bg-slate-100 text-slate-950' : 'text-slate-500 hover:text-slate-200'}`}>{status} {evidence.filter((item) => item.status === status).length}</button>)}</div><button onClick={() => setEvidenceRefresh((value) => value + 1)} className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 hover:text-slate-200" title="Refresh evidence"><RefreshCw size={13} className={evidenceLoading ? 'animate-spin' : ''} /> Refresh</button></div>
          <div className="max-h-[65vh] overflow-y-auto p-5">{evidenceLoading ? <div className="py-12 text-center text-xs text-slate-500">Loading evidence...</div> : visibleEvidence.length === 0 ? <div className="border border-dashed border-border-dark px-5 py-12 text-center"><ShieldCheck size={22} className="mx-auto text-slate-600" /><p className="mt-3 text-xs text-slate-400">{evidence.length ? 'No evidence matches this filter.' : 'No evidence has been extracted yet.'}</p></div> : <div className="space-y-2">{visibleEvidence.map((item) => <article key={item.evidence_id} className="border border-border-dark/70 bg-bg-dark/40 p-4"><div className="flex items-start justify-between gap-4"><div className="min-w-0 flex-1">{item.kind === 'entity_metadata' && <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-accent-blue">Metadata proposal · {item.entity_type}:{item.entity_value}</div>}<p className="text-sm leading-6 text-slate-300">{item.kind === 'entity_metadata' && item.metadata_key ? <><span className="text-slate-500">{item.metadata_key.replaceAll('_', ' ')}:</span> {formatProposedValue(item.proposed_value)}</> : item.claim}</p></div><span className={`shrink-0 px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${item.status === 'confirmed' ? 'bg-emerald-500/10 text-emerald-400' : item.status === 'rejected' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'}`}>{item.status}</span></div><div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-slate-500">{item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer" className="flex max-w-full items-center gap-1 truncate text-accent-indigo hover:text-cyan-300"><ExternalLink size={11} /> {item.source_title || item.source_url}</a> : <span>{item.source_title || 'No source recorded'}</span>}{item.thread_id && <span>Extracted from thread {item.thread_id.slice(0, 8)}</span>}{typeof item.confidence === 'number' && <span>Confidence {Math.round(item.confidence * 100)}%</span>}</div>{item.status === 'pending' && <div className="mt-4 flex gap-2"><button onClick={() => void reviewEvidence(item, 'confirmed')} className="flex items-center gap-1.5 bg-emerald-500/10 px-3 py-2 text-[11px] font-bold text-emerald-400 hover:bg-emerald-500/20"><Check size={13} /> Confirm</button><button onClick={() => void reviewEvidence(item, 'rejected')} className="flex items-center gap-1.5 bg-red-500/10 px-3 py-2 text-[11px] font-bold text-red-400 hover:bg-red-500/20"><X size={13} /> Reject</button></div>}</article>)}</div>}</div>
        </section>
      </div>}
    </main>
  );
};
