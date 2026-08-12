import React, { useMemo, useState } from 'react';
import { MessageSquare, Search, Trash2 } from 'lucide-react';
import type { Subject, Thread } from '../types';

interface Props {
  threads: Thread[];
  subjects: Subject[];
  onSelectThread: (id: string) => void;
  onDeleteThread: (id: string) => void;
  onNewThread: () => void;
}

export const ThreadBrowser: React.FC<Props> = ({ threads, subjects, onSelectThread, onDeleteThread, onNewThread }) => {
  const [query, setQuery] = useState('');
  const [subjectFilter, setSubjectFilter] = useState('all');

  const filteredThreads = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return threads.filter((thread) => {
      const matchesSubject = subjectFilter === 'all' || (subjectFilter === 'unassigned' ? !thread.subject_id : thread.subject_id === subjectFilter);
      const searchText = `${thread.title || ''} ${thread.subject_name || ''} ${thread.thread_id}`.toLowerCase();
      return matchesSubject && (!normalized || searchText.includes(normalized));
    });
  }, [query, subjectFilter, threads]);

  return <section className="mt-8">
    <div className="flex flex-col gap-4 border-b border-border-dark pb-5 lg:flex-row lg:items-end lg:justify-between">
      <div><h2 className="text-lg font-semibold text-slate-100">Research threads</h2><p className="mt-1 text-xs text-slate-500">Browse conversations by subject and resume where you left off.</p></div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="flex min-h-11 items-center gap-2 border border-border-dark bg-panel-dark px-3 text-slate-500 focus-within:border-accent-blue/70 sm:w-72"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search threads" className="w-full bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-600" /></label>
        <select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)} className="min-h-11 border border-border-dark bg-panel-dark px-3 text-xs text-slate-300 outline-none focus:border-accent-blue/70 sm:w-56"><option value="all">All subjects</option><option value="unassigned">Unassigned threads</option>{subjects.map((subject) => <option key={subject.subject_id} value={subject.subject_id}>{subject.name}</option>)}</select>
        <button onClick={onNewThread} className="min-h-11 bg-accent-blue px-3 text-xs font-bold text-slate-950">New thread</button>
      </div>
    </div>

    <div className="mt-4 flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-slate-500"><span>{filteredThreads.length} of {threads.length} threads</span><span>Sorted by recent activity</span></div>
    <div className="mt-3 overflow-hidden border border-border-dark bg-panel-dark">
      {filteredThreads.length === 0 ? <div className="px-6 py-16 text-center"><MessageSquare size={24} className="mx-auto text-slate-600" /><p className="mt-4 text-sm font-semibold text-slate-300">No matching threads</p><p className="mt-2 text-xs text-slate-500">Try a different subject or search term.</p></div> : <div className="divide-y divide-border-dark">
        {filteredThreads.map((thread) => {
          const isEmpty = thread.message_count === 0;
          return <div key={thread.thread_id} className="group flex items-center gap-4 px-4 py-4 transition-colors hover:bg-slate-900/60 sm:px-5">
            <button onClick={() => onSelectThread(thread.thread_id)} className="flex min-w-0 flex-1 items-start gap-3 text-left">
              <MessageSquare size={16} className="mt-0.5 shrink-0 text-accent-blue" />
              <span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-200">{thread.title || 'Untitled thread'}</span><span className="mt-1 block truncate font-mono text-[10px] text-slate-600">{thread.thread_id}</span></span>
            </button>
            <div className="hidden min-w-44 text-xs text-slate-500 sm:block">{thread.subject_name || 'Unassigned'}</div>
            <div className="hidden w-24 text-right text-xs text-slate-500 md:block">{thread.message_count} messages</div>
            <span className={`w-16 text-right text-[10px] font-bold uppercase tracking-wider ${isEmpty ? 'text-slate-600' : 'text-emerald-400'}`}>{isEmpty ? 'Empty' : 'Active'}</span>
            <button onClick={() => onDeleteThread(thread.thread_id)} className="p-2 text-slate-600 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100" title="Delete thread"><Trash2 size={14} /></button>
          </div>;
        })}
      </div>}
    </div>
  </section>;
};
