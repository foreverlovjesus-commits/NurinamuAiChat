'use client';
import React, { useEffect, useState } from 'react';
import { MessageSquare, Plus, Clock } from 'lucide-react';
import { getAllSessions } from '@/api/client';

interface SidebarProps {
  currentSessionId: string;
  onSelectSession: (id: string | null) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ currentSessionId, onSelectSession }) => {
  const [sessions, setSessions] = useState<{ session_id: string; updated_at: string; preview?: string }[]>([]);

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const data = await getAllSessions();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error('세션 목록 불러오기 실패', err);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffH = Math.floor(diffMs / 3600000);
    const diffD = Math.floor(diffMs / 86400000);
    if (diffH < 1) return '방금 전';
    if (diffH < 24) return `${diffH}시간 전`;
    if (diffD < 7) return `${diffD}일 전`;
    return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
  };

  return (
    <aside
      role="complementary"
      aria-label="대화 목록"
      className="flex flex-col h-full w-60 flex-shrink-0"
      style={{
        background: 'var(--gov-navy-light)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        fontFamily: 'var(--font-main)',
      }}
    >
      {/* 헤더 */}
      <div
        className="px-4 py-4"
        style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
      >
        <div className="flex items-center gap-2 mb-3">
          <span
            className="text-[10px] font-bold tracking-wider"
            style={{ color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.1em' }}
          >
            대화 목록
          </span>
        </div>

        {/* 새 대화 버튼 */}
        <button
          onClick={() => onSelectSession(null)}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl transition-all font-semibold text-sm"
          style={{
            background: 'var(--gov-blue)',
            color: '#fff',
            border: 'none',
            cursor: 'pointer',
            fontFamily: 'var(--font-main)',
          }}
          aria-label="새로운 대화 시작"
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--gov-blue-light)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'var(--gov-blue)')}
        >
          <Plus size={15} strokeWidth={2.5} aria-hidden="true" />
          새로운 대화
        </button>
      </div>

      {/* 세션 목록 */}
      <nav
        aria-label="이전 대화 목록"
        className="flex-1 overflow-y-auto py-2 px-2"
      >
        {sessions.length === 0 ? (
          <p
            className="text-center text-[11px] py-8"
            style={{ color: 'rgba(255,255,255,0.25)' }}
          >
            저장된 대화가 없습니다
          </p>
        ) : (
          sessions.map((session) => {
            const isActive = currentSessionId === session.session_id;
            const sessionLabel = session.preview
              ? session.preview
              : `대화 ${session.session_id.slice(0, 8)}`;

            return (
              <button
                key={session.session_id}
                onClick={() => onSelectSession(session.session_id)}
                aria-label={`이전 대화: ${sessionLabel}, ${formatDate(session.updated_at)}`}
                aria-current={isActive ? 'true' : undefined}
                className="w-full flex items-start gap-2.5 px-3 py-2.5 rounded-xl text-sm transition-all mb-1 text-left"
                style={{
                  background: isActive ? 'rgba(201,168,76,0.12)' : 'transparent',
                  borderTop: 'none',
                  borderRight: 'none',
                  borderBottom: 'none',
                  borderLeft: isActive ? '3px solid var(--gov-gold)' : '3px solid transparent',
                  color: isActive ? '#fff' : 'rgba(255,255,255,0.55)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-main)',
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
                    e.currentTarget.style.color = 'rgba(255,255,255,0.85)';
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.color = 'rgba(255,255,255,0.55)';
                  }
                }}
              >
                <MessageSquare
                  size={14}
                  className="mt-0.5 flex-shrink-0"
                  style={{ color: isActive ? 'var(--gov-gold)' : 'inherit' }}
                  aria-hidden="true"
                />
                <div className="flex-1 min-w-0">
                  <div
                    className="truncate text-[12px] font-semibold leading-tight"
                    title={sessionLabel}
                  >
                    {sessionLabel}
                  </div>
                  <div
                    className="text-[10px] mt-0.5 flex items-center gap-1"
                    style={{ color: 'rgba(255,255,255,0.3)' }}
                  >
                    <Clock size={9} aria-hidden="true" />
                    {formatDate(session.updated_at)}
                  </div>
                </div>
              </button>
            );
          })
        )}
      </nav>

      {/* 하단 시스템 정보 */}
      <div
        className="px-4 py-3"
        style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
      >
        <div className="flex items-center gap-2">
          <div className="status-dot-active" aria-hidden="true" />
          <div>
            <div className="text-[10px] font-bold" style={{ color: 'rgba(255,255,255,0.5)' }}>
              누리나무 AI v4.1 정식 서비스
            </div>
            <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
              국민권익위원회 운영
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
