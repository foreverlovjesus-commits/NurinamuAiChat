'use client';
import React, { useState } from 'react';
import { FileText, Download, Loader2 } from 'lucide-react';
import { jsPDF } from 'jspdf';
import { ChatMessage } from '@/types/api';

interface ExportButtonProps {
  messages: ChatMessage[];
  sessionId: string;
}

const ExportButton: React.FC<ExportButtonProps> = ({ messages, sessionId }) => {
  const [isGenerating, setIsGenerating] = useState(false);

  const generatePDF = async () => {
    if (messages.length === 0) return;
    setIsGenerating(true);

    try {
      const doc = new jsPDF();
      const pageWidth = doc.internal.pageSize.getWidth();
      const margin = 20;
      let y = 30;

      // Header
      doc.setFontSize(22);
      doc.setTextColor(30, 64, 175); // Blue-700
      doc.text("누리나무 AI 법률 자문 리포트", margin, y);
      
      y += 10;
      doc.setFontSize(10);
      doc.setTextColor(156, 163, 175); // Gray-400
      doc.text(`세션 ID: ${sessionId} | 일시: ${new Date().toLocaleString()}`, margin, y);
      
      y += 15;
      doc.setDrawColor(229, 231, 235); // Gray-200
      doc.line(margin, y, pageWidth - margin, y);
      y += 15;

      // Messages
      messages.forEach((msg, idx) => {
        const isAssistant = msg.role === 'assistant';
        
        // Add multi-page handling if content is long
        if (y > 250) {
          doc.addPage();
          y = 20;
        }

        // Role Label
        doc.setFontSize(11);
        doc.setTextColor(isAssistant ? 37 : 75, isAssistant ? 99 : 85, isAssistant ? 235 : 99); // Blue or Gray
        doc.text(isAssistant ? "■ 누리나무 법률 비서" : "■ 질문자", margin, y);
        y += 7;

        // Content
        doc.setFontSize(10);
        doc.setTextColor(55, 65, 81); // Gray-700
        const splitText = doc.splitTextToSize(msg.content, pageWidth - (margin * 2));
        
        doc.text(splitText, margin, y);
        y += (splitText.length * 6) + 10;

        // Space between messages
        y += 5;
      });

      // Footer
      doc.setFontSize(8);
      doc.setTextColor(156, 163, 175);
      doc.text("본 결과는 참고용이며 법적 효력이 없습니다. © 2026 NuriNamu Enterprise", margin, 280);

      doc.save(`nurinamu_report_${sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      console.error('PDF generation failed', err);
      alert('PDF 생성 중 오류가 발생했습니다.');
    } finally {
      setIsGenerating(false);
    }
  };

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
