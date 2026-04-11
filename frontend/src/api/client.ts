// frontend/src/api/client.ts
import { SSEEvent, AskRequest } from '../types/api';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
const CHATAPI_KEY = process.env.NEXT_PUBLIC_CHAT_API_KEY || '';

/**
 * SSE 스트리밍 답변을 처리하는 핵심 클라이언트 함수
 */
export async function* askStream(request: AskRequest): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': CHATAPI_KEY,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('Response body is null');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.replace('data: ', ''));
          yield data as SSEEvent;
        } catch (e) {
          console.error('[SSE Parse Error]', e, line);
        }
      }
    }
  }
}

/**
 * 시스템 상태 확인
 */
export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}

/**
 * 전채 세션 목록 가져오기 (사이드바용)
 */
export async function getAllSessions(limit: number = 20) {
  const response = await fetch(`${API_BASE_URL}/sessions?limit=${limit}`, {
    headers: { 'X-API-Key': CHATAPI_KEY }
  });
  if (!response.ok) throw new Error('Failed to fetch sessions');
  return response.json();
}

/**
 * 특정 세션의 대화 이력 가져오기
 */
export async function getSessionHistory(sessionId: string) {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/history`, {
    headers: { 'X-API-Key': CHATAPI_KEY }
  });
  if (!response.ok) throw new Error('Failed to fetch history');
  return response.json();
}

/**
 * 답변에 대한 피드백 전송
 */
export async function postFeedback(sessionId: string, messageIndex: number, rating: number, comment?: string) {
  const response = await fetch(`${API_BASE_URL}/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': CHATAPI_KEY
    },
    body: JSON.stringify({ session_id: sessionId, message_index: messageIndex, rating, comment })
  });
  if (!response.ok) throw new Error('Failed to post feedback');
  return response.json();
}

/**
 * 실시간 세션 사용량 및 비용 정보 가져오기
 */
export async function getSessionUsage(sessionId: string) {
  const response = await fetch(`${API_BASE_URL}/usage/session/${sessionId}`, {
    headers: { 'X-API-Key': CHATAPI_KEY }
  });
  if (!response.ok) throw new Error('Failed to fetch usage');
  return response.json();
}
