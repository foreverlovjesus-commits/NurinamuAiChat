'use client';
import React, { useState } from 'react';
import { diff_match_patch, DIFF_DELETE, DIFF_INSERT, DIFF_EQUAL } from 'diff-match-patch';
import { ArrowLeftRight, FileText, CheckCircle2, AlertCircle } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const ComparisonView: React.FC = () => {
  const [text1, setText1] = useState('');
  const [text2, setText2] = useState('');
  const [diffResult, setDiffResult] = useState<any[]>([]);
  const [isComparing, setIsComparing] = useState(false);

  const handleCompare = () => {
    setIsComparing(true);
    const dmp = new diff_match_patch();
    const diffs = dmp.diff_main(text1, text2);
    dmp.diff_cleanupSemantic(diffs);
    setDiffResult(diffs);
  };

  const renderDiff = () => {
    return diffResult.map(([type, text], index) => {
      const style = cn(
        "inline px-0.5 rounded",
        type === DIFF_DELETE ? "bg-red-100 text-red-700 line-through decoration-red-400" :
        type === DIFF_INSERT ? "bg-green-100 text-green-700 font-bold" :
        "text-gray-700"
      );
      return <span key={index} className={style}>{text}</span>;
    });
  };

  return (
    <div className="flex flex-col h-full bg-white p-8 overflow-y-auto animate-in fade-in slide-in-from-right-10 duration-500">
      {/* Header */}
      <div className="flex items-center gap-3 mb-10 border-b border-gray-100 pb-6">
        <div className="p-3 bg-blue-600 text-white rounded-2xl shadow-lg ring-4 ring-blue-50">
          <ArrowLeftRight size={24} />
        </div>
        <div>
          <h2 className="text-2xl font-black text-gray-900 leading-tight">법령/지침 조문 비교 분석</h2>
          <p className="text-xs text-gray-400 font-bold uppercase tracking-widest mt-1">Version Delta & Change Analysis Mode</p>
        </div>
      </div>

      {/* Input Grid */}
      <div className="grid grid-cols-2 gap-8 mb-8">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-black text-gray-400 uppercase tracking-widest">
            <FileText size={14} /> 원본 지침 (Original)
          </div>
          <textarea
            value={text1}
            onChange={(e) => setText1(e.target.value)}
            className="w-full h-64 p-5 bg-gray-50 border border-gray-100 rounded-2xl focus:ring-4 focus:ring-blue-100 focus:border-blue-500 resize-none transition-all outline-none text-sm leading-relaxed"
            placeholder="비교할 원본 텍스트나 이전 법령 조문을 붙여넣으세요..."
          />
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-black text-blue-500 uppercase tracking-widest">
            <CheckCircle2 size={14} /> 변경된 안 (Revision)
          </div>
          <textarea
            value={text2}
            onChange={(e) => setText2(e.target.value)}
            className="w-full h-64 p-5 bg-blue-50/30 border border-blue-100 rounded-2xl focus:ring-4 focus:ring-blue-100 focus:border-blue-500 resize-none transition-all outline-none text-sm leading-relaxed"
            placeholder="수정된 내용이나 최신 개정안을 붙여넣으세요..."
          />
        </div>
      </div>

      {/* Control Bar */}
      <div className="flex justify-center mb-10">
        <button
          onClick={handleCompare}
          disabled={!text1.trim() || !text2.trim()}
          className={cn(
            "px-10 py-4 rounded-full font-black text-sm uppercase tracking-[0.2em] transition-all shadow-xl",
            !text1.trim() || !text2.trim()
              ? "bg-gray-100 text-gray-300 cursor-not-allowed"
              : "bg-gray-900 text-white hover:bg-blue-600 hover:-translate-y-1 active:scale-95"
          )}
        >
          {diffResult.length > 0 ? "Re-Analyze Changes" : "Start Analysis"}
        </button>
      </div>

      {/* Result Display */}
      {diffResult.length > 0 && (
        <div className="space-y-6 animate-in zoom-in-95 duration-300">
           <div className="flex items-center gap-3 p-4 bg-gray-900 text-white rounded-2xl shadow-2xl">
              <AlertCircle size={18} className="text-blue-400" />
              <span className="text-[11px] font-black uppercase tracking-widest opacity-80">분석 결과: <span className="text-green-400">초록색</span>은 추가됨, <span className="text-red-400">빨간색</span>은 삭제됨</span>
           </div>
           
           <div className="p-8 bg-white border border-gray-100 rounded-3xl shadow-sm text-sm leading-[2.2] whitespace-pre-wrap font-sans min-h-[200px]">
             {renderDiff()}
           </div>
        </div>
      )}
    </div>
  );
};

export default ComparisonView;
