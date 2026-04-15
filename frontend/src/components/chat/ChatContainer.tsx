'use client';
import React, { useState, useEffect, useRef } from 'react';
import ChatBubble from './ChatBubble';
import ChatInput from './ChatInput';
import Sidebar from './Sidebar';
import PerformanceWidget from './PerformanceWidget';
import ExportButton from './ExportButton';
import { ChatMessage, SSEEvent } from '@/types/api';
import { askStream, getHealth, getSessionHistory, getUIConfig } from '@/api/client';
import { LayoutDashboard, Share2, ShieldCheck, FileText, Zap } from 'lucide-react';

const ChatContainer: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [currentCategory, setCurrentCategory] = useState<string>('');
  const [refreshStats, setRefreshStats] = useState(0);
  const [uiConfig, setUiConfig] = useState({ 
    hide_session_list: false,
    hide_usage_stats: false,
    hide_secure_icon: false,
    hide_pdf_export: false,
    hide_share_icon: false,
    enable_conversation_history: false,
    app_name: "누리나무 AI 법률통합지원 시스템",
    app_bot_name: "누리나무 법률 AI",
    app_icon: "⚖️"
  });
  // 설정 로드 완료 여부 ─ true가 되기 전까지 사이드바를 렌더링 안 한(FOUC 방지)
  const [isConfigLoaded, setIsConfigLoaded] = useState(false);

  useEffect(() => {
    document.title = `${uiConfig.app_name} | 국민권익위원회`;
  }, [uiConfig.app_name]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 세션 초기화 ─ 관리자 설정(enable_conversation_history)에 따라 동적 제어
  useEffect(() => {
    getUIConfig().then(config => {
      setUiConfig(config);
      setIsConfigLoaded(true);  // 설정 로드 완료 신호
      if (config.enable_conversation_history) {
        let sid = localStorage.getItem('nurinamu_session_id');
        if (!sid) {
          sid = crypto.randomUUID();
          localStorage.setItem('nurinamu_session_id', sid);
        }
        setSessionId(sid);
        loadHistory(sid);
      } else {
        const sid = crypto.randomUUID();
        setSessionId(sid);
      }
    }).catch(() => setIsConfigLoaded(true));  // 실패시도 렌더링 허용
    getHealth().catch(err => console.error('백엔드 상태 확인 실패:', err));
  }, []);

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const loadHistory = async (sid: string) => {
    try {
      setIsLoading(true);
      const data = await getSessionHistory(sid);
      setMessages(data.messages || []);
      setRefreshStats(prev => prev + 1);
    } catch (err) {
      console.error('대화 이력 불러오기 실패', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectSession = (_sid: string | null) => {
    if (uiConfig.enable_conversation_history && _sid) {
      // 이력 연계 모드: 해당 세션 복원
      localStorage.setItem('nurinamu_session_id', _sid);
      setSessionId(_sid);
      loadHistory(_sid);
    } else {
      // 독립 모드: 항상 새 세션으로 초기화
      const nextSid = crypto.randomUUID();
      setSessionId(nextSid);
      setMessages([]);
      setRefreshStats(0);
    }
  };

  const handleSend = async (question: string) => {
    if (isLoading) return;

    const userMsg: ChatMessage = {
      role: 'user',
      content: question,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);
    setCurrentCategory('');

    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, assistantMsg]);

    try {
      let fullContent = '';
      let sources: string[] = [];

      for await (const event of askStream({ question, session_id: sessionId })) {
        switch (event.type) {
          case 'category':
            setCurrentCategory(event.content || '');
            updateLastMessage({ type: event.content || '' });
            break;
          case 'sources':
            sources = event.sources || [];
            updateLastMessage({ sources });
            break;
          case 'chunk':
            fullContent += event.content || '';
            updateLastMessage({ content: fullContent });
            break;
          case 'reset':
            // 재시도 시 부분 답변 초기화 → 새 답변이 깔끔하게 시작됨
            fullContent = '';
            updateLastMessage({ content: '' });
            break;
          case 'done':
            setIsLoading(false);
            setRefreshStats(prev => prev + 1);
            break;
          case 'error':
            setIsLoading(false);
            updateLastMessage({ content: `⚠️ 오류: ${event.content}` });
            break;
        }
      }
    } catch (error) {
      setIsLoading(false);
      updateLastMessage({
        content: `⚠️ 서버 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n\n${error instanceof Error ? error.message : String(error)}`
      });
    }
  };

  const updateLastMessage = (updates: Partial<ChatMessage>) => {
    setMessages(prev => {
      const newMsgs = [...prev];
      if (newMsgs.length > 0) {
        newMsgs[newMsgs.length - 1] = { ...newMsgs[newMsgs.length - 1], ...updates };
      }
      return newMsgs;
    });
  };

  // 추천 질의 — 실용적인 공공기관 법령 질문
  const suggestedQueries = [
    "청탁금지법상 경조사비 허용 기준은?",
    "공익신고자 보호 절차와 지원 사항",
    "행동강령 위반 시 신고 방법과 처리 절차",
  ];

  return (
    <div className="flex h-screen" style={{ background: 'var(--surface-1)' }}>
      {/* 
        사이드바: 설정 로드 전(isConfigLoaded=false)에는 알 렌더링 안 함 → FOUC(짧은 번쉽임) 방지
        모바일 기기(md 미만)에서는 무조건 숨김,
        hide_session_list=true 시에도 렌더링 제외.
      */}
      {isConfigLoaded && !uiConfig.hide_session_list && (
        <div className="hidden md:flex flex-col h-full">
          <Sidebar
            currentSessionId={sessionId}
            onSelectSession={handleSelectSession}
            appName={uiConfig.app_name}
          />
        </div>
      )}

      {/* 메인 채팅 영역 */}
      <div className="flex-1 flex flex-col h-full relative overflow-hidden" style={{ background: 'var(--surface-0)' }}>

        {/* 성능 분석 위젯 */}
        {!uiConfig.hide_usage_stats && (
          <PerformanceWidget sessionId={sessionId} refreshTrigger={refreshStats} />
        )}

        {/* 상단 헤더 */}
        <header
          className="flex-shrink-0 flex items-center justify-between px-3 md:px-6 py-3"
          style={{
            background: 'rgba(255,255,255,0.95)',
            backdropFilter: 'blur(12px)',
            borderBottom: '1px solid var(--surface-3)',
            boxShadow: '0 1px 8px rgba(0,0,0,0.04)',
          }}
        >
          <div className="flex items-center gap-3">
            {/* 시스템 로고/아이콘 */}
            <div
              className={`w-9 h-9 rounded-lg flex items-center justify-center ${uiConfig.app_logo_path ? 'overflow-hidden' : ''}`}
              style={{ background: uiConfig.app_logo_path ? 'transparent' : 'var(--gov-navy)' }}
              aria-hidden="true"
            >
              {uiConfig.app_logo_path ? (
                <img src={uiConfig.app_logo_path} alt="App Logo" className="w-full h-full object-cover" />
              ) : (
                <span style={{ fontSize: '18px' }}>
                  {uiConfig.app_icon}
                </span>
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1
                  className="text-sm font-bold leading-tight"
                  style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-main)' }}
                >
                  {uiConfig.app_name}
                </h1>
                {currentCategory && (
                  <span
                    className="text-[10px] px-2 py-0.5 rounded font-bold tracking-wider"
                    style={{
                      background: 'var(--gov-navy)',
                      color: 'var(--gov-gold)',
                      fontFamily: 'var(--font-main)',
                    }}
                    aria-live="polite"
                    aria-label={`현재 카테고리: ${currentCategory}`}
                  >
                    {currentCategory}
                  </span>
                )}
              </div>
              <p
                className="text-[11px] font-semibold"
                style={{ color: 'var(--text-muted)' }}
              >
                국민권익위원회 · 민원·법규 AI 통합지원 서비스 v4.1
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* 보안 연결 상태 */}
            {!uiConfig.hide_secure_icon && (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg"
              style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-3)' }}
              title="보안 연결 활성"
            >
              <div className="status-dot-active" aria-hidden="true" />
              <span className="text-[10px] font-semibold" style={{ color: 'var(--gov-success)' }}>
                보안 연결
              </span>
            </div>
            )}
            {!uiConfig.hide_pdf_export && (
              <ExportButton messages={messages} sessionId={sessionId} />
            )}
            {!uiConfig.hide_share_icon && (
            <button
              className="p-2 rounded-lg transition-colors"
              style={{ border: '1px solid var(--surface-3)', color: 'var(--text-muted)' }}
              title="대화 공유"
              aria-label="현재 대화 공유"
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--gov-blue)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              <Share2 size={15} />
            </button>
            )}
          </div>
        </header>

        {/* 메시지 영역 */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-3 md:px-6 py-6 scroll-smooth"
          role="log"
          aria-label="대화 내용"
          aria-live="polite"
          aria-atomic="false"
        >
          {/* 시작 안내 화면 */}
          {messages.length === 0 && !isLoading && (
            <div
              className="flex flex-col items-center justify-center h-full text-center max-w-lg mx-auto py-10"
              style={{ animation: 'fadeInUp 0.5s ease' }}
            >
              {/* 아이콘 */}
              <div className="relative mb-8">
                <div
                  className="absolute -inset-6 rounded-full"
                  style={{ background: 'rgba(30,95,168,0.06)' }}
                  aria-hidden="true"
                />
                <div
                  className="relative w-20 h-20 rounded-2xl flex items-center justify-center shadow-lg"
                  style={{ background: 'var(--gov-navy)' }}
                  aria-hidden="true"
                >
                  <LayoutDashboard size={36} color="var(--gov-gold)" strokeWidth={1.5} />
                </div>
              </div>

              {/* 설명 */}
              <div className="space-y-3 mb-8">
                <h2
                  className="text-xl font-bold"
                  style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-main)' }}
                >
                  민원·법규 AI 통합지원 시스템
                </h2>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                  행동강령, 청탁금지법, 공익신고 보호 등<br />
                  최신 법규를 실시간으로 검색하여 안전하고 정확한 답변을 드립니다.
                </p>
              </div>

              {/* 기능 배지 */}
              <div className="flex items-center gap-2 mb-8">
                {[
                  { icon: <ShieldCheck size={12} />, text: '법령 실시간 연동' },
                  { icon: <Zap size={12} />, text: 'AI 근거 분석' },
                  { icon: <FileText size={12} />, text: '출처 제공' },
                ].map(({ icon, text }) => (
                  <span
                    key={text}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-semibold"
                    style={{
                      background: 'var(--surface-2)',
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--surface-3)',
                    }}
                  >
                    {icon}
                    {text}
                  </span>
                ))}
              </div>

              {/* 추천 질의 */}
              <div
                className="w-full rounded-2xl p-4"
                style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-3)' }}
              >
                <p
                  className="text-[10px] font-bold mb-3 text-left"
                  style={{ color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}
                >
                  자주 묻는 질문
                </p>
                <div className="flex flex-col gap-2">
                  {suggestedQueries.map(q => (
                    <button
                      key={q}
                      onClick={() => handleSend(q)}
                      className="text-left text-sm px-4 py-2.5 rounded-xl transition-all font-medium"
                      style={{
                        background: 'var(--surface-0)',
                        border: '1px solid var(--surface-3)',
                        color: 'var(--text-secondary)',
                        fontFamily: 'var(--font-main)',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = 'var(--gov-blue)';
                        e.currentTarget.style.color = 'var(--gov-blue)';
                        e.currentTarget.style.background = 'rgba(30,95,168,0.04)';
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = 'var(--surface-3)';
                        e.currentTarget.style.color = 'var(--text-secondary)';
                        e.currentTarget.style.background = 'var(--surface-0)';
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 메시지 목록 */}
          {messages.map((msg, idx) => (
            <ChatBubble
              key={`${sessionId}-${idx}`}
              message={msg}
              previousMessage={idx > 0 && messages[idx - 1].role === 'user' ? messages[idx - 1] : undefined}
              sessionId={sessionId}
              index={idx}
              appBotName={uiConfig.app_bot_name}
              appName={uiConfig.app_name}
            />
          ))}

          {/* 분석 중 로딩 인디케이터 */}
          {isLoading && (messages.length === 0 || messages[messages.length - 1].content === '') && (
            <div
              className="flex items-center gap-3 p-4 rounded-2xl w-fit"
              role="status"
              aria-label="법령 분석 중입니다. 잠시 기다려 주세요."
              style={{
                background: 'var(--surface-0)',
                border: '1px solid var(--surface-3)',
                boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
              }}
            >
              <div className="flex items-center gap-1.5">
                {[0, 150, 300].map(delay => (
                  <div
                    key={delay}
                    className="w-2 h-2 rounded-full"
                    style={{
                      background: 'var(--gov-navy)',
                      animation: `bounce 1.2s ${delay}ms ease-in-out infinite`,
                    }}
                    aria-hidden="true"
                  />
                ))}
              </div>
              <span
                className="text-[11px] font-bold"
                style={{ color: 'var(--gov-navy)', letterSpacing: '0.04em' }}
              >
                법령 분석 중...
              </span>
            </div>
          )}
        </div>

        {/* 입력 영역 */}
        <footer
          className="flex-shrink-0 px-3 md:px-6 py-4"
          style={{
            background: 'linear-gradient(to top, var(--surface-0) 80%, transparent)',
          }}
        >
          <div
            className="max-w-3xl mx-auto rounded-2xl p-1"
            style={{
              background: 'var(--surface-0)',
              border: '1px solid var(--surface-3)',
              boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
            }}
          >
            <ChatInput onSend={handleSend} isLoading={isLoading} />
            {/* 하단 메타 정보 */}
            <div className="flex items-center justify-center gap-6 py-2 opacity-60">
              <span className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
                보안 연결 활성
              </span>
              <span style={{ color: 'var(--surface-3)' }}>|</span>
              <span className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
                {uiConfig.app_name} · 국민권익위원회
              </span>
              <span style={{ color: 'var(--surface-3)' }}>|</span>
              <span className="text-[10px] font-semibold" style={{ color: 'var(--text-muted)' }}>
                법제처 법령 연동
              </span>
            </div>
          </div>
        </footer>
      </div>

      <style>{`
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes bounce {
          0%, 100% { transform: translateY(0); }
          50%       { transform: translateY(-5px); }
        }
      `}</style>
    </div>
  );
};

export default ChatContainer;
