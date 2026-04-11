'use client';
import React, { useState } from 'react';
import ChatContainer from '@/components/chat/ChatContainer';
import ComparisonView from '@/components/chat/ComparisonView';
import { MessageSquare, ArrowLeftRight, Settings, ShieldCheck, Scale } from 'lucide-react';

// ── 공공기관 공식 인트라넷 레이아웃 ─────────────────────────────────────────────

export default function Home() {
  const [activeTab, setActiveTab] = useState<'chat' | 'compare'>('chat');

  return (
    <div className="flex h-screen overflow-hidden" style={{ fontFamily: 'var(--font-main)' }}>

      {/* 좌측 아이코닉 내비게이션 (공공기관 딥 네이비) */}
      <nav
        role="navigation"
        aria-label="주요 메뉴"
        className="w-[68px] flex flex-col items-center py-5 gap-0 border-r z-50 flex-shrink-0"
        style={{
          background: 'var(--gov-navy)',
          borderColor: 'rgba(255,255,255,0.07)',
        }}
      >
        {/* 기관 로고 영역 */}
        <div className="flex flex-col items-center gap-1 mb-6 px-2">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center shadow-lg"
            style={{ background: 'var(--gov-gold)' }}
            aria-hidden="true"
          >
            <Scale size={20} color="var(--gov-navy)" strokeWidth={2.5} />
          </div>
          <span
            className="text-[8px] font-bold tracking-wider text-center leading-tight"
            style={{ color: 'var(--gov-gold)', opacity: 0.85 }}
          >
            권익위
          </span>
        </div>

        {/* 구분선 */}
        <div style={{ width: '32px', height: '1px', background: 'rgba(255,255,255,0.1)', marginBottom: '16px' }} />

        {/* 탭 메뉴 */}
        <div className="flex flex-col gap-2 w-full px-2">
          <NavButton
            label="AI 법령 상담"
            icon={<MessageSquare size={20} strokeWidth={2} />}
            isActive={activeTab === 'chat'}
            onClick={() => setActiveTab('chat')}
            id="nav-chat"
          />
          <NavButton
            label="문서 비교"
            icon={<ArrowLeftRight size={20} strokeWidth={2} />}
            isActive={activeTab === 'compare'}
            onClick={() => setActiveTab('compare')}
            id="nav-compare"
          />
        </div>

        {/* 하단 상태 표시 */}
        <div className="mt-auto flex flex-col items-center gap-4 pb-2 px-2 w-full">
          {/* 시스템 상태 */}
          <div
            className="flex flex-col items-center gap-1"
            title="시스템 정상 운영 중"
          >
            <ShieldCheck
              size={18}
              strokeWidth={2}
              style={{ color: '#22c55e' }}
              aria-label="보안 연결 활성"
            />
            <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '7px', fontWeight: 700, letterSpacing: '0.05em' }}>
              보안 연결
            </span>
          </div>
          {/* 설정 */}
          <button
            className="flex flex-col items-center gap-1 w-full py-2 rounded-lg transition-all"
            style={{ color: 'rgba(255,255,255,0.4)' }}
            title="시스템 설정"
            aria-label="시스템 설정"
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.07)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <Settings size={18} strokeWidth={2} />
            <span style={{ fontSize: '7px', fontWeight: 700 }}>설정</span>
          </button>
        </div>
      </nav>

      {/* 메인 콘텐츠 영역 */}
      <section
        className="flex-1 relative overflow-hidden"
        style={{ background: 'var(--surface-1)' }}
        aria-live="polite"
        aria-label="메인 콘텐츠"
      >
        {activeTab === 'chat' ? (
          <div className="h-full" style={{ animation: 'fadeIn 0.3s ease' }}>
            <ChatContainer />
          </div>
        ) : (
          <div className="h-full bg-white" style={{ animation: 'fadeIn 0.3s ease' }}>
            <ComparisonView />
          </div>
        )}
      </section>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// ── 내비게이션 버튼 컴포넌트 ────────────────────────────────────────────────────
interface NavButtonProps {
  label: string;
  icon: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
  id: string;
}

function NavButton({ label, icon, isActive, onClick, id }: NavButtonProps) {
  return (
    <button
      id={id}
      onClick={onClick}
      aria-pressed={isActive}
      aria-label={label}
      title={label}
      className="relative w-full flex flex-col items-center gap-1 py-2.5 px-1 rounded-xl transition-all duration-200 focus-visible:outline-2 outline-offset-2"
      style={{
        background: isActive ? 'rgba(201,168,76,0.15)' : 'transparent',
        color: isActive ? 'var(--gov-gold)' : 'rgba(255,255,255,0.45)',
        outline: 'none',
        border: 'none',
        cursor: 'pointer',
      }}
      onMouseEnter={e => {
        if (!isActive) e.currentTarget.style.color = 'rgba(255,255,255,0.8)';
      }}
      onMouseLeave={e => {
        if (!isActive) e.currentTarget.style.color = 'rgba(255,255,255,0.45)';
      }}
    >
      {icon}
      <span style={{ fontSize: '9px', fontWeight: 700, letterSpacing: '0.02em', lineHeight: 1.2 }}>
        {label.split(' ')[0]}<br />{label.split(' ')[1] || ''}
      </span>
      {/* 활성 인디케이터 */}
      {isActive && (
        <span
          className="absolute right-0 top-1/2 -translate-y-1/2"
          style={{
            width: '3px', height: '28px',
            background: 'var(--gov-gold)',
            borderRadius: '2px 0 0 2px',
          }}
          aria-hidden="true"
        />
      )}
    </button>
  );
}
