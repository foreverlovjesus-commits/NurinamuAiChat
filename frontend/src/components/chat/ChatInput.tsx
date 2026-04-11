'use client';
import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

const ChatInput: React.FC<ChatInputProps> = ({ onSend, isLoading }) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = text.trim().length > 0 && !isLoading;

  const handleSend = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 자동 높이 조절
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [text]);

  return (
    <div
      className="flex items-end gap-3 p-3"
      role="form"
      aria-label="질문 입력 폼"
    >
      {/* 텍스트 입력 */}
      <label htmlFor="chat-message-input" className="sr-only">
        법령 질문 입력
      </label>
      <textarea
        id="chat-message-input"
        ref={textareaRef}
        className="flex-1 max-h-44 resize-none outline-none text-sm transition-all leading-relaxed"
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-main)',
          padding: '6px 4px',
          lineHeight: 1.7,
        }}
        placeholder="법령, 행동강령, 민원 등 궁금한 사항을 입력하세요. (Shift+Enter: 줄바꿈)"
        rows={1}
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isLoading}
        aria-label="질문 내용 입력"
        aria-describedby="chat-input-hint"
        aria-disabled={isLoading}
        aria-multiline="true"
      />

      {/* 힌트 텍스트 (스크린리더용) */}
      <span id="chat-input-hint" className="sr-only">
        Enter 키로 전송, Shift+Enter로 줄바꿈
      </span>

      {/* 전송 버튼 */}
      <button
        id="chat-send-button"
        onClick={handleSend}
        disabled={!canSend}
        className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-xl transition-all"
        style={{
          background: canSend ? 'var(--gov-navy)' : 'var(--surface-2)',
          color: canSend ? '#fff' : 'var(--text-disabled)',
          border: 'none',
          cursor: canSend ? 'pointer' : 'not-allowed',
          transform: 'scale(1)',
          boxShadow: canSend ? '0 2px 8px rgba(13,27,62,0.3)' : 'none',
          transition: 'all 0.15s ease',
        }}
        aria-label={isLoading ? '답변 생성 중입니다. 잠시 기다려 주세요.' : '질문 전송'}
        aria-busy={isLoading}
        onMouseEnter={e => {
          if (canSend) e.currentTarget.style.transform = 'scale(1.08)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.transform = 'scale(1)';
        }}
      >
        {isLoading ? (
          <Loader2 size={17} className="animate-spin" aria-hidden="true" />
        ) : (
          <Send size={16} strokeWidth={2.5} aria-hidden="true" />
        )}
      </button>
    </div>
  );
};

export default ChatInput;
