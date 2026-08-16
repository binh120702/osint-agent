import React from 'react';
import { ArrowLeft, Brain, Settings2 } from 'lucide-react';
import { ToolConfig } from './ToolConfig';

interface SettingsPageProps {
  onBack: () => void;
  selectedProvider: string;
  selectedModel: string;
  onModelChange: (provider: string, model: string) => void;
  toolsRefreshTrigger: number;
}

const MODELS = [
  { provider: 'openai', name: 'gpt-4o', label: 'OpenAI: GPT-4o' },
  { provider: 'openai', name: 'gpt-4o-mini', label: 'OpenAI: GPT-4o-mini' },
  { provider: 'openai', name: 'gpt-5.4', label: 'OpenAI: GPT-5.4 (Experimental)' },
  { provider: 'openai', name: 'gpt-5.6-luna', label: 'OpenAI: GPT-5.6 Luna' },
  { provider: 'gemini', name: 'gemini-2.5-flash', label: 'Gemini: 2.5 Flash' },
  { provider: 'gemini', name: 'gemini-2.5-pro', label: 'Gemini: 2.5 Pro' },
  { provider: 'claude', name: 'claude-sonnet-4-5', label: 'Claude: Sonnet 4.5' },
  { provider: 'claude', name: 'claude-3-5-sonnet-20241022', label: 'Claude: 3.5 Sonnet' },
];

export const SettingsPage: React.FC<SettingsPageProps> = ({ onBack, selectedProvider, selectedModel, onModelChange, toolsRefreshTrigger }) => (
  <main className="h-screen overflow-y-auto bg-bg-dark text-slate-100">
    <div className="mx-auto max-w-[1120px] px-5 py-6 sm:px-8 lg:px-12 lg:py-10">
      <header className="flex flex-col gap-5 border-b border-border-dark pb-8 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-4 flex items-center gap-3 text-[11px] font-bold uppercase tracking-[0.2em] text-accent-blue"><Settings2 size={14} /> OSINT Agent / Settings</div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">Workspace settings</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">Configure the tools and model used by new investigation turns.</p>
        </div>
        <button onClick={onBack} className="flex min-h-11 items-center gap-2 border border-border-dark px-3 text-xs font-semibold text-slate-400 hover:border-slate-600 hover:text-slate-100"><ArrowLeft size={14} /> Back to workspace</button>
      </header>

      <section className="mt-8 border border-border-dark bg-panel-dark/40 p-5">
        <div className="flex items-start gap-3"><Brain size={17} className="mt-0.5 text-accent-blue" /><div><h2 className="text-sm font-semibold text-slate-200">Active brain</h2><p className="mt-1 text-xs text-slate-500">Choose the provider and model for the next message you send.</p></div></div>
        <label className="mt-5 block max-w-xl"><span className="mb-2 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Model</span><select value={`${selectedProvider}/${selectedModel}`} onChange={(event) => { const [provider, ...modelParts] = event.target.value.split('/'); onModelChange(provider, modelParts.join('/')); }} className="w-full bg-slate-950 border border-border-dark px-3 py-3 text-xs text-slate-300 focus:border-accent-blue"><option value="">Select a model</option>{MODELS.map((item) => <option key={`${item.provider}/${item.name}`} value={`${item.provider}/${item.name}`}>{item.label}</option>)}</select></label>
      </section>

      <div className="mt-8"><ToolConfig onRefreshToolsTrigger={toolsRefreshTrigger} /></div>
    </div>
  </main>
);
