// frontend/src/types/api.ts

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'down';
  llm: string;
  retriever: string;
  mcp_law: 'connected' | 'disconnected';
  mcp_tools_count: number;
}

export interface AskRequest {
  question: string;
  session_id?: string;
}

export type SSEEventType = 
  | 'category' 
  | 'sources' 
  | 'chunk' 
  | 'done' 
  | 'error'
  | 'law_source'
  | 'fallback';

export interface SSEEvent {
  type: SSEEventType;
  content?: string;
  reason?: string;         // type='category' 일 때
  summary_5w1h?: string;   // type='category' 일 때
  sources?: string[];      // type='sources' 일 때 출처 목록
  session_id?: string;     // type='done' 일 때
  response_time_ms?: number; // type='done' 일 때
  code?: string;           // type='error' 일 때
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  type?: string;
  sources?: string[];
  timestamp: string;
}
