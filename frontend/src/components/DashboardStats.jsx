import React from 'react';
import { ShieldAlert, Clock, Coins, Briefcase, Landmark, Building, Activity } from 'lucide-react';

const CATEGORY_NAMES = {
  "VA_PENTEST": "VA / Pentest / Red Team",
  "AUDIT_COMPLIANCE": "Audit & Compliance",
  "SOC_MSSP": "SOC & Managed Services",
  "SOLUTION_IMPLEMENTATION": "Security Solutions",
  "INCIDENT_RESPONSE": "Incident Response",
  "TRAINING_DRILL": "Training & Cyber Drill",
  "OTHER": "งานไซเบอร์ทั่วไป"
};

export default function DashboardStats({ stats, selectedCategory, onSelectCategory, selectedSector, onSelectSector }) {
  if (!stats) return null;

  const formatCurrency = (val) => {
    if (val >= 1000000) {
      return (val / 1000000).toFixed(1) + ' ล้านบาท';
    }
    return val.toLocaleString('th-TH') + ' บาท';
  };

  const finCount = stats.agency_type_counts?.["สถาบันการเงิน"] || 0;
  const corpCount = stats.agency_type_counts?.["บริษัทเอกชนชั้นนำ"] || 0;
  const govCount = (stats.agency_type_counts?.["ส่วนราชการ"] || 0) + 
                   (stats.agency_type_counts?.["รัฐวิสาหกิจ"] || 0) + 
                   (stats.agency_type_counts?.["องค์กรกำกับดูแล"] || 0) +
                   (stats.agency_type_counts?.["องค์การมหาชน"] || 0);

  return (
    <div className="space-y-4">
      {/* 4 KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {/* Total Tenders */}
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-800/60 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-cyan-500/40 transition-all">
          <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/10 rounded-full blur-2xl group-hover:bg-cyan-500/20 transition-all"></div>
          <div className="flex items-center justify-between">
            <span className="text-xs sm:text-sm font-medium text-slate-400">ระเบียนจัดซื้อทั้งหมด</span>
            <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Briefcase className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-2xl sm:text-3xl font-bold text-white tracking-tight">{stats.total_tenders}</span>
            <span className="text-xs text-slate-400">โครงการ</span>
          </div>
          <div className="mt-2 flex items-center text-[11px] text-cyan-400/80">
            <Activity className="w-3 h-3 mr-1" />
            <span>เฉพาะรายการที่มีหลักฐานย้อนกลับ</span>
          </div>
        </div>

        {/* Active Tenders */}
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-800/60 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-emerald-500/40 transition-all">
          <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full blur-2xl group-hover:bg-emerald-500/20 transition-all"></div>
          <div className="flex items-center justify-between">
            <span className="text-xs sm:text-sm font-medium text-slate-400">กำลังเปิดรับซอง</span>
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <ShieldAlert className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-2xl sm:text-3xl font-bold text-emerald-400 tracking-tight">{stats.active_tenders}</span>
            <span className="text-xs text-slate-400">โครงการ</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400">พร้อมเข้าร่วมประกวดราคา</div>
        </div>

        {/* Closing Soon */}
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-800/60 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-amber-500/40 transition-all">
          <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/10 rounded-full blur-2xl group-hover:bg-amber-500/20 transition-all"></div>
          <div className="flex items-center justify-between">
            <span className="text-xs sm:text-sm font-medium text-slate-400">ใกล้หมดเขต (≤ 7 วัน)</span>
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-2xl sm:text-3xl font-bold text-amber-400 tracking-tight">{stats.closing_soon_tenders}</span>
            <span className="text-xs text-slate-400">โครงการเร่งด่วน</span>
          </div>
          <div className="mt-2 text-[11px] text-amber-400/80 font-medium">ตรวจเอกสารต้นฉบับก่อนดำเนินการ</div>
        </div>

        {/* Total Budget */}
        <div className="p-4 sm:p-5 rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-800/60 border border-slate-800 backdrop-blur-sm relative overflow-hidden group hover:border-purple-500/40 transition-all">
          <div className="absolute top-0 right-0 w-24 h-24 bg-purple-500/10 rounded-full blur-2xl group-hover:bg-purple-500/20 transition-all"></div>
          <div className="flex items-center justify-between">
            <span className="text-xs sm:text-sm font-medium text-slate-400">งบที่ต้นทางระบุรวม</span>
            <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Coins className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-xl sm:text-2xl font-bold text-purple-300 tracking-tight">{formatCurrency(stats.total_budget)}</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-400">ไม่รวมรายการที่ต้นทางไม่ระบุวงเงิน</div>
        </div>
      </div>

      {/* Sector Quick Metric Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 p-3 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-xs">
        <div
          onClick={() => onSelectSector && onSelectSector('สถาบันการเงิน')}
          className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/80 hover:bg-emerald-950/30 border border-slate-800 hover:border-emerald-500/30 cursor-pointer transition-all"
        >
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400">
              <Landmark className="w-4 h-4" />
            </div>
            <div>
              <span className="font-semibold text-slate-200 block">สถาบันการเงิน & ธนาคาร</span>
              <span className="text-[11px] text-slate-500">จัดประเภทจากชื่อหน่วยงานต้นทาง</span>
            </div>
          </div>
          <span className="font-bold text-emerald-400 text-sm">{finCount} งาน</span>
        </div>

        <div
          onClick={() => onSelectSector && onSelectSector('บริษัทเอกชนชั้นนำ')}
          className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/80 hover:bg-indigo-950/30 border border-slate-800 hover:border-indigo-500/30 cursor-pointer transition-all"
        >
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Building className="w-4 h-4" />
            </div>
            <div>
              <span className="font-semibold text-slate-200 block">บริษัทเอกชนชั้นนำ</span>
              <span className="text-[11px] text-slate-500">แสดงเมื่อเชื่อม source ที่ยืนยันแล้ว</span>
            </div>
          </div>
          <span className="font-bold text-indigo-400 text-sm">{corpCount} งาน</span>
        </div>

        <div
          onClick={() => onSelectSector && onSelectSector('ALL')}
          className="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/80 hover:bg-cyan-950/30 border border-slate-800 hover:border-cyan-500/30 cursor-pointer transition-all"
        >
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400">
              <Briefcase className="w-4 h-4" />
            </div>
            <div>
              <span className="font-semibold text-slate-200 block">ภาครัฐ & รัฐวิสาหกิจ</span>
              <span className="text-[11px] text-slate-500">e-GP, สกมช. และหน้า procurement ทางการ</span>
            </div>
          </div>
          <span className="font-bold text-cyan-400 text-sm">{govCount} งาน</span>
        </div>
      </div>

      {/* Category Quick Filter Pills */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1 scrollbar-none">
        <button
          onClick={() => onSelectCategory('ALL')}
          className={`px-3 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap transition-all flex items-center space-x-1.5 ${
            selectedCategory === 'ALL'
              ? 'bg-cyan-500 text-slate-950 font-semibold shadow-md shadow-cyan-500/20'
              : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700/60'
          }`}
        >
          <span>ทุกประเภทงาน ({stats.total_tenders})</span>
        </button>

        {Object.entries(stats.category_counts || {}).map(([cat, count]) => (
          <button
            key={cat}
            onClick={() => onSelectCategory(cat)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap transition-all flex items-center space-x-1.5 ${
              selectedCategory === cat
                ? 'bg-cyan-500 text-slate-950 font-semibold shadow-md shadow-cyan-500/20'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700/60'
            }`}
          >
            <span>{CATEGORY_NAMES[cat] || cat}</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              selectedCategory === cat ? 'bg-black/20 text-slate-900' : 'bg-slate-700 text-slate-300'
            }`}>
              {count}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
