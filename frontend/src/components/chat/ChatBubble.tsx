'use client';
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { ThumbsUp, ThumbsDown, Copy, Check, BookOpen } from 'lucide-react';
import { ChatMessage } from '@/types/api';
import { postFeedback } from '@/api/client';

interface ChatBubbleProps {
  message: ChatMessage;
  sessionId: string;
  index: number;
}

const ChatBubble: React.FC<ChatBubbleProps> = ({ message, sessionId, index }) => {
  const isAssistant = message.role === 'assistant';
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFeedback = async (type: 'up' | 'down') => {
    if (feedback) return;
    setFeedback(type);
    try {
      await postFeedback(sessionId, index, type === 'up' ? 5 : 1);
    } catch (err) {
      console.error('피드백 저장 실패', err);
    }
  };

  const timestamp = new Date(message.timestamp).toLocaleString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <article
      className={`flex w-full mb-6 group ${isAssistant ? 'justify-start' : 'justify-end'}`}
      style={{ animation: 'fadeInUp 0.25s ease' }}
    >
      <div
        className="relative max-w-[88%] rounded-2xl p-5 transition-shadow"
        style={
          isAssistant
            ? {
                background: 'var(--surface-0)',
                border: '1px solid var(--surface-3)',
                borderTopLeftRadius: '4px',
                color: 'var(--text-primary)',
                boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
              }
            : {
                background: 'var(--gov-navy)',
                borderTopRightRadius: '4px',
                color: '#fff',
                boxShadow: '0 2px 12px rgba(13,27,62,0.25)',
              }
        }
      >
        {/* 발신자 메타 */}
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2">
            <div
              className="w-5 h-5 rounded-md flex items-center justify-center text-[9px] font-black"
              style={
                isAssistant
                  ? { background: 'var(--gov-navy)', color: 'var(--gov-gold)' }
                  : { background: 'rgba(255,255,255,0.2)', color: '#fff' }
              }
              aria-hidden="true"
            >
              {isAssistant ? 'AI' : '나'}
            </div>
            <span
              className="text-[11px] font-bold"
              style={{ color: isAssistant ? 'var(--text-muted)' : 'rgba(255,255,255,0.7)' }}
            >
              {isAssistant ? '누리나무 법률 AI' : '질문'}
            </span>
          </div>

          {/* 법령 카테고리 태그 */}
          {isAssistant && message.type && (
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-bold"
              style={{
                background: 'rgba(13,27,62,0.06)',
                color: 'var(--gov-navy)',
                border: '1px solid rgba(13,27,62,0.12)',
                fontFamily: 'var(--font-main)',
              }}
              aria-label={`답변 유형: ${message.type}`}
            >
              {message.type}
            </span>
          )}
        </div>

        {/* 본문 */}
        <div
          className="text-sm leading-relaxed break-words"
          style={{ fontFamily: 'var(--font-main)', lineHeight: 1.75 }}
        >
          {isAssistant ? (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={{
                h1: ({ children }) => (
                  <h2 className="text-base font-bold mt-4 mb-2" style={{ color: 'var(--gov-navy)' }}>{children}</h2>
                ),
                h2: ({ children }) => (
                  <h3 className="text-sm font-bold mt-3 mb-1.5" style={{ color: 'var(--gov-navy)' }}>{children}</h3>
                ),
                h3: ({ children }) => (
                  <h4 className="text-sm font-semibold mt-2 mb-1" style={{ color: 'var(--text-secondary)' }}>{children}</h4>
                ),
                strong: ({ children }) => (
                  <strong className="font-bold" style={{ color: 'var(--gov-navy)' }}>{children}</strong>
                ),
                code: ({ children }) => (
                  <code
                    className="px-1.5 py-0.5 rounded text-[12px]"
                    style={{ background: 'var(--surface-2)', color: 'var(--gov-navy)', fontFamily: 'var(--font-mono)' }}
                  >
                    {children}
                  </code>
                ),
                blockquote: ({ children }) => (
                  <blockquote
                    className="pl-4 py-1 my-2"
                    style={{ borderLeft: '3px solid var(--gov-gold)', color: 'var(--text-secondary)', fontStyle: 'normal' }}
                  >
                    {children}
                  </blockquote>
                ),
                ul: ({ children }) => (
                  <ul className="list-disc pl-4 space-y-1 my-2">{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol className="list-decimal pl-4 space-y-1 my-2">{children}</ol>
                ),
                // FIRAC 모드 <details>/<summary> 스타일링
                details: ({ children, ...props }) => (
                  <details
                    {...props}
                    className="my-2 rounded-lg overflow-hidden"
                    style={{
                      border: '1px solid var(--surface-3)',
                      background: 'var(--surface-1)',
                    }}
                  >
                    {children}
                  </details>
                ),
                summary: ({ children, ...props }) => (
                  <summary
                    {...props}
                    className="px-4 py-2.5 cursor-pointer select-none text-sm font-semibold"
                    style={{
                      background: 'rgba(13,27,62,0.04)',
                      color: 'var(--gov-navy)',
                      listStyle: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <span style={{ fontSize: '10px', opacity: 0.5 }}>▶</span>
                    {children}
                  </summary>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>

          ) : (
            <div className="whitespace-pre-wrap">{message.content}</div>
          )}
        </div>

        {/* 참조 법령 출처 */}
        {isAssistant && message.sources && message.sources.length > 0 && (
          <div
            className="mt-4 pt-4"
            style={{ borderTop: '1px solid var(--surface-3)' }}
          >
            <div
              className="flex items-center gap-1.5 mb-2.5"
              style={{ color: 'var(--text-muted)', fontSize: '11px', fontWeight: 700 }}
            >
              <BookOpen size={12} strokeWidth={2.5} aria-hidden="true" />
              <span>참조 법령 및 출처</span>
            </div>
            <div className="flex flex-wrap gap-1.5" role="list" aria-label="참조 출처 목록">
              {message.sources.map((source, idx) => (
                <span
                  key={idx}
                  role="listitem"
                  className="px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors"
                  style={{
                    background: 'rgba(13,27,62,0.05)',
                    color: 'var(--gov-navy)',
                    border: '1px solid rgba(13,27,62,0.1)',
                    fontFamily: 'var(--font-main)',
                  }}
                >
                  {source}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 액션 버튼 (호버 시 표시) */}
        {isAssistant && message.content && (
          <div
            className="absolute -right-11 top-2 flex flex-col gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
            role="group"
            aria-label="답변 관련 작업"
          >
            <button
              onClick={handleCopy}
              className="p-2 rounded-full transition-all"
              style={{
                background: 'var(--surface-0)',
                border: '1px solid var(--surface-3)',
                color: copied ? 'var(--gov-success)' : 'var(--text-muted)',
                boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
              }}
              title="답변 복사"
              aria-label={copied ? '복사 완료' : '답변 복사'}
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>

            <button
              onClick={() => handleFeedback('up')}
              disabled={!!feedback}
              className="p-2 rounded-full transition-all"
              style={{
                background: feedback === 'up' ? 'rgba(26,122,74,0.1)' : 'var(--surface-0)',
                border: `1px solid ${feedback === 'up' ? 'var(--gov-success)' : 'var(--surface-3)'}`,
                color: feedback === 'up' ? 'var(--gov-success)' : 'var(--text-muted)',
                boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
              }}
              title="도움이 됐어요"
              aria-label="도움이 됐어요"
              aria-pressed={feedback === 'up'}
            >
              <ThumbsUp size={13} fill={feedback === 'up' ? 'currentColor' : 'none'} />
            </button>

            <button
              onClick={() => handleFeedback('down')}
              disabled={!!feedback}
              className="p-2 rounded-full transition-all"
              style={{
                background: feedback === 'down' ? 'rgba(185,28,28,0.07)' : 'var(--surface-0)',
                border: `1px solid ${feedback === 'down' ? 'var(--gov-error)' : 'var(--surface-3)'}`,
                color: feedback === 'down' ? 'var(--gov-error)' : 'var(--text-muted)',
                boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
              }}
              title="개선이 필요해요"
              aria-label="개선이 필요해요"
              aria-pressed={feedback === 'down'}
            >
              <ThumbsDown size={13} fill={feedback === 'down' ? 'currentColor' : 'none'} />
            </button>
          </div>
        )}

        {/* 타임스탬프 */}
        <div
          className={`text-[10px] mt-3 font-medium ${isAssistant ? 'text-left' : 'text-right'}`}
          style={{ color: isAssistant ? 'var(--text-muted)' : 'rgba(255,255,255,0.45)' }}
          aria-label={`${isAssistant ? 'AI 답변' : '질문'} 시각: ${timestamp}`}
        >
          {timestamp}
        </div>
      </div>

      <style>{`
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </article>
  );
};

export default ChatBubble;
