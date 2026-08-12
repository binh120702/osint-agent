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
  subject_id?: string | null;
  subject_name?: string | null;
}

export interface Subject {
  subject_id: string;
  name: string;
  subject_type: string;
  canonical_identifier?: string;
  aliases: string[];
  identifiers: string[];
  description?: string;
  investigation_goals?: string;
  status: 'active' | 'done';
  thread_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface SubjectEvidence {
  evidence_id: string;
  claim: string;
  source_url?: string;
  source_title?: string;
  confidence?: number;
  status: 'pending' | 'confirmed' | 'rejected';
  thread_id?: string;
  kind?: 'finding' | 'entity_metadata';
  entity_type?: string;
  entity_value?: string;
  metadata_key?: string;
  proposed_value?: string;
  created_at?: number | string;
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

export interface EntityMetadataValue {
  value: any;
  evidence_ids?: string[];
}

export interface KBEdge {
  source: string;
  target: string;
  type: string;
  properties: Record<string, any>;
}
