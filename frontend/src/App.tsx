import { useState, useEffect } from 'react';
import { ThreadSidebar } from './components/ThreadSidebar';
import { SettingsPage } from './components/SettingsPage';
import { ChatPanel } from './components/ChatPanel';
import { KBViewer } from './components/KBViewer';
import { SubjectBar } from './components/SubjectBar';
import { InvestigationHome } from './components/InvestigationHome';
import { CreateSubjectModal } from './components/CreateSubjectModal';
import type { Thread, Message, Subject } from './types';

function App() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [currentSubjectId, setCurrentSubjectId] = useState<string | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeTool, setActiveTool] = useState<{ name: string; args: any; result?: string } | null>(null);
  const [kbRefreshTrigger, setKbRefreshTrigger] = useState(0);
  const [toolsRefreshTrigger] = useState(0);
  const [selectedProvider, setSelectedProvider] = useState<string>('openai');
  const [selectedModel, setSelectedModel] = useState<string>('gpt-5.4');
  const [view, setView] = useState<'home' | 'chat' | 'settings'>('home');
  const [subjectsLoading, setSubjectsLoading] = useState(false);
  const [showCreateSubject, setShowCreateSubject] = useState(false);
  const [showCreateSubjectForThread, setShowCreateSubjectForThread] = useState(false);
  const [homeTab, setHomeTab] = useState<'subjects' | 'threads'>('subjects');

  const fetchThreads = async () => {
    try {
      const res = await fetch('/api/threads');
      const data = await res.json();
      setThreads(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to load threads', e);
    }
  };

  const fetchSubjects = async () => {
    setSubjectsLoading(true);
    try {
      const res = await fetch('/api/subjects');
      const data = await res.json();
      // Keep the UI usable while an older backend is still running or an API
      // returns an error object instead of the expected collection.
      setSubjects(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to load subjects', e);
    } finally {
      setSubjectsLoading(false);
    }
  };

  const loadThread = async (id: string, subjectId?: string | null) => {
    setView('chat');
    setCurrentThreadId(id);
    setCurrentSubjectId(subjectId ?? (threads.find((thread) => thread.thread_id === id)?.subject_id || null));
    setMessages([]);
    setActiveTool(null);
    try {
      const res = await fetch(`/api/threads/${id}/messages`);
      const msgs = await res.json();
      setMessages(
        msgs.map((m: any) => ({
          role: m.role,
          content: m.content,
          isToolCall: m.isToolCall || m.role === 'tool',
          toolName: m.toolName || (m.role === 'tool' ? (m.name || 'tool') : undefined),
          toolArgs: m.toolArgs,
          toolResult: m.toolResult || (m.role === 'tool' ? m.content : undefined),
        }))
      );
      setKbRefreshTrigger((prev) => prev + 1);
    } catch (e) {
      console.error('Failed to fetch thread messages', e);
    }
  };

  useEffect(() => {
    fetchThreads();
    fetchSubjects();

    const currentState = window.history.state;
    if (currentState?.view === 'settings') {
      setView('settings');
    } else if (currentState?.view === 'chat' && currentState.thread_id) {
      loadThread(currentState.thread_id, currentState.subject_id);
    } else {
      window.history.replaceState({ view: 'home' }, '', '#subjects');
    }

    const handleHistoryChange = (event: PopStateEvent) => {
      const state = event.state;
      if (state?.view === 'settings') {
        setView('settings');
        return;
      }
      if (state?.view === 'chat' && state.thread_id) {
        loadThread(state.thread_id, state.subject_id);
        return;
      }
      setView('home');
      setCurrentThreadId(null);
      setCurrentSubjectId(null);
      setMessages([]);
      setActiveTool(null);
    };

    window.addEventListener('popstate', handleHistoryChange);
    return () => window.removeEventListener('popstate', handleHistoryChange);
  }, []);

  const handleSelectThread = async (id: string) => {
    const selectedThread = threads.find((thread) => thread.thread_id === id);
    window.history.pushState(
      { view: 'chat', thread_id: id, subject_id: selectedThread?.subject_id || null },
      '',
      `#chat/${encodeURIComponent(id)}`
    );
    loadThread(id, selectedThread?.subject_id || null);
  };

  const handleGoHome = () => {
    window.history.pushState({ view: 'home' }, '', '#subjects');
    setView('home');
    setCurrentThreadId(null);
    setCurrentSubjectId(null);
    setMessages([]);
    setActiveTool(null);
  };

  const handleOpenSettings = () => {
    window.history.pushState({ view: 'settings' }, '', '#settings');
    setView('settings');
  };

  const handleBackFromSettings = () => {
    if (window.history.length > 1) {
      window.history.back();
      return;
    }
    handleGoHome();
  };

  const handleNewThread = async () => {
    try {
      const response = await fetch('/api/threads', { method: 'POST' });
      if (!response.ok) throw new Error('Unable to create thread');
      const data = await response.json();
      window.history.pushState(
        { view: 'chat', thread_id: data.thread_id, subject_id: null },
        '',
        `#chat/${encodeURIComponent(data.thread_id)}`
      );
      setView('chat');
      setCurrentThreadId(data.thread_id);
      setCurrentSubjectId(null);
      setMessages([]);
      setActiveTool(null);
      await fetchThreads();
    } catch (e) {
      console.error('Failed to create unassigned thread', e);
    }
  };

  const handleStartThread = async (subject: Subject) => {
    try {
      const response = await fetch(`/api/subjects/${subject.subject_id}/threads`, { method: 'POST' });
      if (!response.ok) throw new Error('Unable to create thread');
      const data = await response.json();
      window.history.pushState(
        { view: 'chat', thread_id: data.thread_id, subject_id: subject.subject_id },
        '',
        `#chat/${encodeURIComponent(data.thread_id)}`
      );
      setCurrentSubjectId(subject.subject_id);
      setCurrentThreadId(data.thread_id);
      setMessages([]);
      setActiveTool(null);
      setView('chat');
      await fetchThreads();
      await fetchSubjects();
    } catch (e) {
      console.error('Failed to create subject thread', e);
    }
  };

  const handleSubjectCreated = (subject: Subject) => {
    setSubjects((prev) => [subject, ...prev]);
    setShowCreateSubject(false);
    handleStartThread(subject);
  };

  const handleSubjectCreatedForThread = async (subject: Subject) => {
    setSubjects((prev) => [subject, ...prev.filter((item) => item.subject_id !== subject.subject_id)]);
    setCurrentSubjectId(subject.subject_id);
    setShowCreateSubjectForThread(false);
    window.history.replaceState(
      { view: 'chat', thread_id: currentThreadId, subject_id: subject.subject_id },
      '',
      currentThreadId ? `#chat/${encodeURIComponent(currentThreadId)}` : '#subjects'
    );
    await fetchThreads();
    await fetchSubjects();
  };

  const handleToggleSubjectStatus = async (subject: Subject) => {
    const status = subject.status === 'done' ? 'active' : 'done';
    try {
      const response = await fetch(`/api/subjects/${subject.subject_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error('Unable to update subject status');
      const updated = await response.json();
      setSubjects((prev) => prev.map((item) => item.subject_id === updated.subject_id ? updated : item));
    } catch (e) {
      console.error('Failed to update subject status', e);
    }
  };

  const handleDeleteSubject = async (subject: Subject) => {
    const response = await fetch(`/api/subjects/${encodeURIComponent(subject.subject_id)}`, { method: 'DELETE' });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || 'Unable to delete subject');
    }
    setSubjects((prev) => prev.filter((item) => item.subject_id !== subject.subject_id));
    await fetchThreads();
    if (currentSubjectId === subject.subject_id) {
      setCurrentSubjectId(null);
      setKbRefreshTrigger((prev) => prev + 1);
    }
  };

  const handleSelectSubject = (subjectId: string | null) => {
    setCurrentSubjectId(subjectId);
    setCurrentThreadId(null);
    setMessages([]);
    setActiveTool(null);
    setKbRefreshTrigger((prev) => prev + 1);
  };

  const handleAttachSubjectToThread = async (subjectId: string) => {
    if (!currentThreadId) return;
    const response = await fetch(`/api/threads/${encodeURIComponent(currentThreadId)}/subjects/${encodeURIComponent(subjectId)}`, { method: 'POST' });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || 'Unable to add subject to thread');
    }
    setCurrentSubjectId(subjectId);
    window.history.replaceState({ view: 'chat', thread_id: currentThreadId, subject_id: subjectId }, '', `#chat/${encodeURIComponent(currentThreadId)}`);
    fetchThreads();
  };

  const handleDeleteThread = async (id: string) => {
    try {
      await fetch(`/api/threads/${id}`, { method: 'DELETE' });
      if (currentThreadId === id) {
        handleGoHome();
      }
      fetchThreads();
    } catch (e) {
      console.error('Failed to delete thread', e);
    }
  };

  const handleSendMessage = async () => {
    const text = inputValue.trim();
    if (!text) return;
    setInputValue('');
    setIsLoading(true);
    setActiveTool(null);

    // Optimistically add user message
    const userMsg: Message = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          thread_id: currentThreadId,
          subject_id: currentSubjectId,
          provider: selectedProvider,
          model_name: selectedModel,
        }),
      });

      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantMsg: Message | null = null;
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          if (!trimmed.startsWith('data: ')) continue;
          let payload;
          try {
            payload = JSON.parse(trimmed.substring(6));
          } catch {
            continue;
          }

          if (payload.type === 'thread_id') {
            setCurrentThreadId(payload.thread_id);
            fetchThreads();
          } else if (payload.type === 'text') {
            if (!assistantMsg) {
              assistantMsg = { role: 'assistant', content: '' };
              setMessages((prev) => [...prev, assistantMsg!]);
            }
            setMessages((prev) => {
              const next = [...prev];
              const idx = next.length - 1;
              if (idx >= 0 && next[idx].role === 'assistant') {
                next[idx] = {
                  ...next[idx],
                  content: next[idx].content + payload.chunk,
                };
              }
              return next;
            });
          } else if (payload.type === 'tool_start') {
            assistantMsg = null;
            setActiveTool({ name: payload.name, args: payload.args });
            setMessages((prev) => [
              ...prev,
              {
                role: 'tool',
                content: '',
                isToolCall: true,
                toolName: payload.name,
                toolArgs: payload.args,
              }
            ]);
          } else if (payload.type === 'tool_end') {
            setActiveTool((prev) => (prev ? { ...prev, result: payload.result } : null));
            setKbRefreshTrigger((prev) => prev + 1);
            setMessages((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].isToolCall && next[i].toolName === payload.name && !next[i].toolResult) {
                  next[i] = {
                    ...next[i],
                    toolResult: payload.result,
                  };
                  break;
                }
              }
              return next;
            });
          } else if (payload.type === 'done') {
            setIsLoading(false);
            setActiveTool(null);
            fetchThreads();
            setKbRefreshTrigger((prev) => prev + 1);
            if (payload.metrics) {
              setMessages((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].role === 'assistant') {
                    next[i] = {
                      ...next[i],
                      metrics: payload.metrics,
                    };
                    break;
                  }
                }
                return next;
              });
            }
          } else if (payload.type === 'error') {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `⚠️ Error: ${payload.message}` },
            ]);
            setIsLoading(false);
            setActiveTool(null);
          }
        }
      }
    } catch (e) {
      console.error(e);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: '⚠️ An unexpected error occurred while communicating with the server.' },
      ]);
      setIsLoading(false);
      setActiveTool(null);
    }
  };

  if (view === 'home') {
    return <>
      <InvestigationHome
        subjects={subjects}
        onCreateSubject={() => setShowCreateSubject(true)}
        onOpenSettings={handleOpenSettings}
        onStartThread={handleStartThread}
        onNewThread={handleNewThread}
        onToggleStatus={handleToggleSubjectStatus}
        onDeleteSubject={handleDeleteSubject}
        onRefresh={() => { fetchThreads(); fetchSubjects(); }}
        loading={subjectsLoading}
        activeTab={homeTab}
        onTabChange={setHomeTab}
        threads={threads}
        onSelectThread={handleSelectThread}
        onDeleteThread={handleDeleteThread}
      />
      {showCreateSubject && <CreateSubjectModal onClose={() => setShowCreateSubject(false)} onCreated={handleSubjectCreated} />}
    </>;
  }

  if (view === 'settings') {
    return <SettingsPage onBack={handleBackFromSettings} selectedProvider={selectedProvider} selectedModel={selectedModel} onModelChange={(provider, model) => { setSelectedProvider(provider); setSelectedModel(model); }} toolsRefreshTrigger={toolsRefreshTrigger} />;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-dark text-slate-100">
      {/* Sidebar */}
      <ThreadSidebar
        threads={threads}
        currentThreadId={currentThreadId}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
        onGoHome={handleGoHome}
        onDeleteThread={handleDeleteThread}
        onOpenSettings={handleOpenSettings}
        selectedProvider={selectedProvider}
        selectedModel={selectedModel}
        onModelChange={(p, m) => {
          setSelectedProvider(p);
          setSelectedModel(m);
        }}
      />

      {/* Main Panel */}
          <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
            <SubjectBar
              subjects={subjects}
              selectedSubjectId={currentSubjectId}
              currentThreadId={currentThreadId}
              onSelect={handleSelectSubject}
              onCreateSubjectFromThread={() => setShowCreateSubjectForThread(true)}
              onAttachSubjectToThread={handleAttachSubjectToThread}
              onCreated={(subject) => setSubjects((prev) => [subject, ...prev])}
              onEvidenceChanged={() => setKbRefreshTrigger((prev) => prev + 1)}
            />
            <ChatPanel
          messages={messages}
          inputValue={inputValue}
          setInputValue={setInputValue}
          onSendMessage={handleSendMessage}
              isLoading={isLoading}
              activeTool={activeTool}
              canSend={view === 'chat'}
            />
      </div>

      {/* Right KB Panel */}
          <KBViewer threadId={currentThreadId} subjectId={currentSubjectId} refreshTrigger={kbRefreshTrigger} />
      {showCreateSubjectForThread && currentThreadId && <CreateSubjectModal
        threadId={currentThreadId}
        provider={selectedProvider}
        model={selectedModel}
        onClose={() => setShowCreateSubjectForThread(false)}
        onCreated={handleSubjectCreatedForThread}
      />}
    </div>
  );
}

export default App;
