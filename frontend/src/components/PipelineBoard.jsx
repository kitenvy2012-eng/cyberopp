import React from 'react';
import { Layers, ArrowRight, CheckCircle2, XCircle, Clock, Building2, ChevronRight, FileText } from 'lucide-react';
import { updateTender } from '../services/api';

const STAGES = [
  { id: 'SAVED', title: 'สนใจ / บันทึกไว้', color: 'border-cyan-500/30 text-cyan-400 bg-cyan-500/10' },
  { id: 'REVIEWING_TOR', title: 'กำลังศึกษา TOR', color: 'border-blue-500/30 text-blue-400 bg-blue-500/10' },
  { id: 'PREPARING_PROPOSAL', title: 'จัดทำราคา & ข้อเสนอ', color: 'border-amber-500/30 text-amber-400 bg-amber-500/10' },
  { id: 'BIDDING', title: 'ยื่นซองแล้ว', color: 'border-purple-500/30 text-purple-400 bg-purple-500/10' },
  { id: 'WON', title: 'ชนะการประมูล (Won)', color: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' },
  { id: 'LOST', title: 'ไม่ได้งาน (Lost)', color: 'border-slate-600 text-slate-400 bg-slate-800/40' },
];

export default function PipelineBoard({ tenders, onSelectTender, onRefresh }) {
  const formatMoney = (val) => {
    if (!val) return '0 บาท';
    if (val >= 1000000) return (val / 1000000).toFixed(1) + 'M';
    return (val / 1000).toFixed(0) + 'K';
  };

  const handleStageChange = async (tenderId, nextStage) => {
    try {
      await updateTender(tenderId, { pipeline_stage: nextStage });
      if (onRefresh) onRefresh();
    } catch (e) {
      alert('ย้ายสถานะไม่สำเร็จ: ' + e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center space-x-2">
            <Layers className="w-5 h-5 text-cyan-400" />
            <span>Opportunity Pipeline & Bidding Tracker</span>
          </h2>
          <p className="text-xs text-slate-400">ติดตามและบริหารสถานะโครงการจัดซื้อจัดจ้างที่ทีมงานกำลังเข้าร่วมประมูล</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
        {STAGES.map(stage => {
          const items = tenders.filter(t => t.pipeline_stage === stage.id);
          const totalVal = items.reduce((acc, t) => acc + (t.budget || 0), 0);

          return (
            <div key={stage.id} className="flex flex-col rounded-2xl bg-[#131B2B]/70 border border-slate-800 p-3 min-h-[500px]">
              {/* Column Header */}
              <div className="pb-3 border-b border-slate-800">
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-md border ${stage.color}`}>
                    {stage.title}
                  </span>
                  <span className="text-xs font-bold text-slate-400">{items.length}</span>
                </div>
                <div className="mt-2 text-[11px] text-slate-400 flex items-center justify-between">
                  <span>มูลค่ารวม:</span>
                  <span className="font-semibold text-white">{formatMoney(totalVal)}</span>
                </div>
              </div>

              {/* Items List */}
              <div className="mt-3 space-y-2.5 flex-1 overflow-y-auto pr-0.5">
                {items.length === 0 ? (
                  <div className="h-32 flex items-center justify-center text-[11px] text-slate-600 border border-dashed border-slate-800 rounded-xl">
                    ไม่มีโครงการ
                  </div>
                ) : (
                  items.map(tender => (
                    <div
                      key={tender.id}
                      className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-cyan-500/40 transition-all text-xs space-y-2 group cursor-pointer shadow-sm"
                      onClick={() => onSelectTender(tender)}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-semibold text-cyan-400 bg-cyan-500/10 px-1.5 py-0.2 rounded">
                          {tender.category}
                        </span>
                        {tender.submission_deadline && (
                          <span className="text-[10px] text-amber-400 font-medium">
                            {tender.submission_deadline}
                          </span>
                        )}
                      </div>

                      <h4 className="font-semibold text-slate-200 line-clamp-2 group-hover:text-cyan-300 leading-snug">
                        {tender.title}
                      </h4>

                      <div className="text-[11px] text-slate-400 truncate">
                        {tender.agency}
                      </div>

                      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between">
                        <span className="font-bold text-cyan-400">
                          {tender.budget ? (tender.budget / 1000000).toFixed(2) + 'M' : 'ไม่ระบุ'}
                        </span>

                        {/* Move stage quick actions */}
                        <div className="flex items-center space-x-1" onClick={(e) => e.stopPropagation()}>
                          <select
                            value={tender.pipeline_stage}
                            onChange={(e) => handleStageChange(tender.id, e.target.value)}
                            className="bg-slate-800 border border-slate-700 text-[10px] text-slate-300 rounded px-1.5 py-0.5 focus:outline-none focus:border-cyan-500"
                          >
                            <option value="NONE">ลบออก</option>
                            {STAGES.map(s => (
                              <option key={s.id} value={s.id}>{s.title}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
