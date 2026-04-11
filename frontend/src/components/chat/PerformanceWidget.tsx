'use client';
import React, { useState, useEffect } from 'react';
import { Activity, DollarSign, Cpu, BarChart2 } from 'lucide-react';
import { getSessionUsage } from '@/api/client';

interface PerformanceWidgetProps {
  sessionId: string;
  refreshTrigger: any; // Trigger refresh when messages change
}

const PerformanceWidget: React.FC<PerformanceWidgetProps> = ({ sessionId, refreshTrigger }) => {
  const [stats, setStats] = useState<{
    calls: number;
    total_tokens: number;
    total_cost: number;
    avg_latency: number;
  } | null>(null);

  useEffect(() => {
    if (sessionId) {
      fetchUsage();
    }
  }, [sessionId, refreshTrigger]);

  const fetchUsage = async () => {
    try {
      const data = await getSessionUsage(sessionId);
      setStats(data);
    } catch (err) {
      console.error('Failed to load usage stats', err);
    }
  };

  if (!stats || stats.calls === 0) return null;

  return (
    <div className="flex items-center gap-6 px-4 py-2 bg-gray-50/50 backdrop-blur-sm border-y border-gray-100/50 animate-in fade-in duration-700">
      <div className="flex items-center gap-1.5">
        <Activity size={12} className="text-blue-500" />
        <span className="text-[10px] font-bold text-gray-500 uppercase">Latency</span>
        <span className="text-[10px] font-bold text-gray-800">{stats.avg_latency}ms</span>
      </div>
      
      <div className="flex items-center gap-1.5">
        <Cpu size={12} className="text-purple-500" />
        <span className="text-[10px] font-bold text-gray-500 uppercase">Tokens</span>
        <span className="text-[10px] font-bold text-gray-800">{stats.total_tokens.toLocaleString()}</span>
      </div>

      <div className="flex items-center gap-1.5">
        <DollarSign size={12} className="text-green-600" />
        <span className="text-[10px] font-bold text-gray-500 uppercase">Session Cost</span>
        <span className="text-[10px] font-bold text-gray-800">${stats.total_cost.toFixed(4)}</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5 opacity-50">
        <BarChart2 size={12} />
        <span className="text-[9px] font-bold uppercase">Real-time Analytics Active</span>
      </div>
    </div>
  );
};

export default PerformanceWidget;
