export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: Array<{
    name: string;
    id?: string;
    arguments?: Record<string, any>;
  }>;
  isToolCall?: boolean;
  toolName?: string;
  toolArgs?: any;
  toolResult?: string;
  metrics?: {
    duration_sec: number;
    iterations: number;
    tools_called: number;
  };
}

export interface Thread {
  thread_id: string;
  title?: string;
  message_count: number;
}

export interface ToolInfo {
  name: string;
  enabled: boolean;
  description?: string;
}

export interface KBEntity {
  id: string;
  label: string;
  properties: Record<string, any>;
}

export interface KBEdge {
  source: string;
  target: string;
  type: string;
  properties: Record<string, any>;
}
