'use client';
import React, { useState } from 'react';
import { FileText, Loader2 } from 'lucide-react';
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import { ChatMessage } from '@/types/api';

interface ExportButtonProps {
  messages: ChatMessage[];
  sessionId: string;
  compact?: boolean;
  appName?: string;
  appBotName?: string;
}

const ExportButton: React.FC<ExportButtonProps> = ({ messages, sessionId, compact, appName = "누리나무 AI 법률통합지원 시스템", appBotName = "누리나무 법률 비서" }) => {
  const [isGenerating, setIsGenerating] = useState(false);

  const generatePDF = async () => {
    if (messages.length === 0) return;
    setIsGenerating(true);

    try {
      // Create a temporary DOM element to render standard HTML so html2canvas can capture Korean natively
      const element = document.createElement('div');
      element.style.padding = '30px';
      element.style.fontFamily = '"Malgun Gothic", "Apple SD Gothic Neo", sans-serif';
      element.style.width = '800px';
      element.style.background = 'white';
      element.style.color = 'black';
      element.style.position = 'absolute';
      element.style.left = '-9999px';
      
      let html = `
        <h1 style="color: #1d4ed8; font-size: 24px; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;">${appName} 자문 리포트</h1>
        <p style="color: #6b7280; font-size: 12px; margin-bottom: 25px;">세션 ID: ${sessionId} | 일시: ${new Date().toLocaleString()}</p>
      `;

      messages.forEach(msg => {
        const isAssistant = msg.role === 'assistant';
        const label = isAssistant ? `■ ${appBotName}` : "■ 질문자";
        const color = isAssistant ? "#2563eb" : "#4b5563";
        // Convert markdown/newlines to standard layout safely using split/join to avoid complex regex escaping
        let textHtml = msg.content
          .split('\n').join('<br/>')
          .split('### ').join('<br/><b style="color: #1e3a8a; font-size: 14px;">')
          .split('<details>').join('<div style="margin-top: 15px; background-color: #f8fafc; padding: 15px; border: 1px solid #e2e8f0; border-radius: 8px;">')
          .split('</details>').join('</div>')
          .split('<summary>').join('<div style="font-weight: bold; color: #1e3a8a; margin-bottom: 10px; font-size: 14px;">')
          .split('</summary>').join('</div>');
        
        html += `
          <div style="margin-bottom: 30px;">
            <div style="font-size: 14px; font-weight: bold; color: ${color}; margin-bottom: 10px;">${label}</div>
            <div style="font-size: 13px; line-height: 1.85; color: #374151; word-break: keep-all; word-wrap: break-word; letter-spacing: -0.02em;">${textHtml}</div>
          </div>
        `;
      });

      html += `<div style="font-size: 10px; color: #9ca3af; margin-top: 50px;">본 결과는 참고용이며 법적 효력이 없습니다.</div>`;
      
      element.innerHTML = html;
      document.body.appendChild(element);

      // Capture the element using html2canvas
      const canvas = await html2canvas(element, { scale: 2, useCORS: true });
      document.body.removeChild(element);

      // Add to PDF handling multi-page splitting
      const imgData = canvas.toDataURL('image/png');
      const doc = new jsPDF('p', 'mm', 'a4');
      
      const pdfWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();
      const imgHeight = (canvas.height * pdfWidth) / canvas.width;
      
      let heightLeft = imgHeight;
      let position = 0;

      doc.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
      heightLeft -= pageHeight;

      while (heightLeft > 0) {
        position = heightLeft - imgHeight;
        doc.addPage();
        doc.addImage(imgData, 'PNG', 0, position, pdfWidth, imgHeight);
        heightLeft -= pageHeight;
      }

      doc.save(`nurinamu_report_${sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      console.error('PDF generation failed', err);
      alert('PDF 생성 중 오류가 발생했습니다.');
    } finally {
      setIsGenerating(false);
    }
  };

  if (compact) {
    return (
      <button
        onClick={generatePDF}
        disabled={isGenerating || messages.length === 0}
        className="p-2 rounded-full transition-all"
        style={{
          background: 'var(--surface-0)',
          border: '1px solid var(--surface-3)',
          color: 'var(--text-muted)',
          boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
        }}
        title="이 답변만 PDF로 다운로드"
        aria-label="이 답변 PDF 내보내기"
      >
        {isGenerating ? <Loader2 size={13} className="animate-spin text-blue-500" /> : <FileText size={13} />}
      </button>
    );
  }

  return (
    <button
      onClick={generatePDF}
      disabled={isGenerating || messages.length === 0}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-all text-xs font-bold uppercase tracking-wider ${
        isGenerating
          ? 'bg-gray-50 text-gray-400 border-gray-100 cursor-not-allowed'
          : 'bg-white text-gray-700 border-gray-200 hover:border-blue-500 hover:text-blue-600 hover:shadow-sm'
      }`}
    >
      {isGenerating ? (
        <Loader2 size={14} className="animate-spin text-blue-500" />
      ) : (
        <FileText size={14} />
      )}
      <span>PDF 리포트 내보내기</span>
    </button>
  );
};

export default ExportButton;
