import { useState, useEffect } from 'react';
import { ThreadSidebar } from './components/ThreadSidebar';
import { ToolConfig } from './components/ToolConfig';
import { ChatPanel } from './components/ChatPanel';
import { KBViewer } from './components/KBViewer';
import type { Thread, Message } from './types';

function App() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [activeTool, setActiveTool] = useState<{ name: string; args: any; result?: string } | null>(null);
  const [kbRefreshTrigger, setKbRefreshTrigger] = useState(0);
  const [toolsRefreshTrigger] = useState(0);
  const [selectedProvider, setSelectedProvider] = useState<string>('openai');
  const [selectedModel, setSelectedModel] = useState<string>('gpt-4o');

  const fetchThreads = async () => {
    try {
      const res = await fetch('/api/threads');
      const data = await res.json();
      setThreads(data);
    } catch (e) {
      console.error('Failed to load threads', e);
    }
  };

  useEffect(() => {
    fetchThreads();
  }, []);

  const handleSelectThread = async (id: string) => {
    setCurrentThreadId(id);
    setMessages([]);
    setActiveTool(null);
    try {
      const res = await fetch(`/api/threads/${id}/messages`);
      const msgs = await res.json();
      setMessages(
        msgs.map((m: any) => ({
          role: m.role,
          content: m.content,
          isToolCall: m.role === 'tool',
          toolName: m.role === 'tool' ? (m.name || 'tool') : undefined,
          toolResult: m.role === 'tool' ? m.content : undefined,
        }))
      );
      // Trigger KB refresh for the new thread
      setKbRefreshTrigger((prev) => prev + 1);
    } catch (e) {
      console.error('Failed to fetch thread messages', e);
    }
  };

  const handleNewThread = () => {
    setCurrentThreadId(null);
    setMessages([]);
    setActiveTool(null);
  };

  const handleDeleteThread = async (id: string) => {
    try {
      await fetch(`/api/threads/${id}`, { method: 'DELETE' });
      if (currentThreadId === id) {
        handleNewThread();
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

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-dark text-slate-100">
      {/* Sidebar */}
      <ThreadSidebar
        threads={threads}
        currentThreadId={currentThreadId}
        onSelectThread={handleSelectThread}
        onNewThread={handleNewThread}
        onDeleteThread={handleDeleteThread}
        showTools={showTools}
        setShowTools={setShowTools}
        selectedProvider={selectedProvider}
        selectedModel={selectedModel}
        onModelChange={(p, m) => {
          setSelectedProvider(p);
          setSelectedModel(m);
        }}
      />

      {/* Main Panel */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {showTools && <ToolConfig onRefreshToolsTrigger={toolsRefreshTrigger} />}
        <ChatPanel
          messages={messages}
          inputValue={inputValue}
          setInputValue={setInputValue}
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          activeTool={activeTool}
        />
      </div>

      {/* Right KB Panel */}
      <KBViewer threadId={currentThreadId} refreshTrigger={kbRefreshTrigger} />
    </div>
  );
}

export default App;
