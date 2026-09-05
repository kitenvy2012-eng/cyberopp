import React from 'react';
import { Search, Filter, ArrowUpDown, X, Landmark, Building, ShieldCheck } from 'lucide-react';

export default function FilterBar({ filters, setFilters, onReset }) {
  const handleChange = (field, value) => {
    setFilters(prev => ({ ...prev, [field]: value }));
  };

  const handleBudgetPreset = (preset) => {
    if (preset === 'ALL') {
      setFilters(prev => ({ ...prev, min_budget: '', max_budget: '' }));
    } else if (preset === 'UNDER_1M') {
      setFilters(prev => ({ ...prev, min_budget: '', max_budget: 1000000 }));
    } else if (preset === '1M_5M') {
      setFilters(prev => ({ ...prev, min_budget: 1000000, max_budget: 5000000 }));
    } else if (preset === '5M_15M') {
      setFilters(prev => ({ ...prev, min_budget: 5000000, max_budget: 15000000 }));
    } else if (preset === 'OVER_15M') {
      setFilters(prev => ({ ...prev, min_budget: 15000000, max_budget: '' }));
    }
  };

  const isBudgetActive = (preset) => {
    const { min_budget, max_budget } = filters;
    if (preset === 'ALL' && !min_budget && !max_budget) return true;
    if (preset === 'UNDER_1M' && !min_budget && max_budget === 1000000) return true;
    if (preset === '1M_5M' && min_budget === 1000000 && max_budget === 5000000) return true;
    if (preset === '5M_15M' && min_budget === 5000000 && max_budget === 15000000) return true;
    if (preset === 'OVER_15M' && min_budget === 15000000 && !max_budget) return true;
    return false;
  };

  return (
    <div className="bg-[#131B2B] rounded-2xl border border-slate-800 p-4 space-y-3.5 shadow-lg">
      {/* Top row: Search input & Sorting */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={filters.q || ''}
            onChange={(e) => handleChange('q', e.target.value)}
            placeholder="ค้นหาโครงการ หน่วยงาน หรือเลขโครงการ (เช่น Pentest, SOC, ISO 27001, Firewall)..."
            className="w-full pl-10 pr-10 py-2.5 rounded-xl bg-slate-900/90 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all"
          />
          {filters.q && (
            <button
              onClick={() => handleChange('q', '')}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center space-x-1.5 bg-emerald-950/30 border border-emerald-500/30 rounded-xl px-3 py-2 text-xs text-emerald-200">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <select
              aria-label="ขอบเขตประกาศ"
              value={
                filters.open_for_bidding
                  ? 'ACTIONABLE'
                  : filters.opportunity_scope === 'ACTIVE_ONLY'
                  ? 'ACTIVE_ONLY'
                  : filters.opportunity_scope === 'AWARDED'
                  ? 'AWARDED'
                  : 'ALL'
              }
              onChange={(e) => {
                const val = e.target.value;
                if (val === 'ACTIONABLE') {
                  setFilters((prev) => ({ ...prev, open_for_bidding: true, opportunity_scope: '' }));
                } else if (val === 'ACTIVE_ONLY') {
                  setFilters((prev) => ({ ...prev, open_for_bidding: false, opportunity_scope: 'ACTIVE_ONLY' }));
                } else if (val === 'AWARDED') {
                  setFilters((prev) => ({ ...prev, open_for_bidding: false, opportunity_scope: 'AWARDED' }));
                } else {
                  setFilters((prev) => ({ ...prev, open_for_bidding: false, opportunity_scope: 'ALL' }));
                }
              }}
              className="bg-transparent text-emerald-200 text-xs focus:outline-none cursor-pointer"
            >
              <option value="ACTIVE_ONLY" className="bg-slate-900">🎯 ประกาศที่ยังต้องตรวจช่วงยื่น</option>
              <option value="ACTIONABLE" className="bg-slate-900">⏱️ เฉพาะที่ยืนยันวันยื่นข้อเสนอแล้ว</option>
              <option value="AWARDED" className="bg-slate-900">🏆 โครงการที่มีผู้ชนะแล้ว (สัญญาแล้ว)</option>
              <option value="ALL" className="bg-slate-900">📁 ประกาศทั้งหมด (ไม่เกิน 1 ปี)</option>
            </select>
          </div>

          {/* Sorting */}
          <div className="flex items-center space-x-1.5 bg-slate-900/90 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-slate-300">
            <ArrowUpDown className="w-3.5 h-3.5 text-cyan-400" />
            <select
              value={filters.sort_by || 'newest'}
              onChange={(e) => handleChange('sort_by', e.target.value)}
              className="bg-transparent text-slate-200 text-xs focus:outline-none cursor-pointer"
            >
              <option value="newest" className="bg-slate-900">ประกาศใหม่ล่าสุด</option>
              <option value="deadline" className="bg-slate-900">วันปิดรับใกล้ที่สุด</option>
              <option value="budget_desc" className="bg-slate-900">งบประมาณสูงสุด</option>
              <option value="budget_asc" className="bg-slate-900">งบประมาณต่ำสุด</option>
            </select>
          </div>
        </div>
      </div>

      {/* Middle row: Sector Quick Filter Badges (Financial, Corporate, Gov) */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1 text-xs">
        <span className="text-slate-400 font-medium whitespace-nowrap mr-1">กลุ่มเป้าหมาย:</span>
        <button
          onClick={() => handleChange('agency_type', 'ALL')}
          className={`px-3 py-1 rounded-xl whitespace-nowrap transition-all border ${
            filters.agency_type === 'ALL'
              ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 font-semibold'
              : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
          }`}
        >
          ทุกกลุ่มองค์กร
        </button>

        <button
          onClick={() => handleChange('agency_type', 'สถาบันการเงิน')}
          className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl whitespace-nowrap transition-all border ${
            filters.agency_type === 'สถาบันการเงิน'
              ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-semibold shadow-sm'
              : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
          }`}
        >
          <Landmark className="w-3.5 h-3.5 text-emerald-400" />
          <span>สถาบันการเงิน (Banks & FinTech)</span>
        </button>

        <button
          onClick={() => handleChange('agency_type', 'บริษัทเอกชนชั้นนำ')}
          className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl whitespace-nowrap transition-all border ${
            filters.agency_type === 'บริษัทเอกชนชั้นนำ'
              ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40 font-semibold shadow-sm'
              : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
          }`}
        >
          <Building className="w-3.5 h-3.5 text-indigo-400" />
          <span>บริษัทเอกชนชั้นนำ (Top Enterprises)</span>
        </button>

        <button
          onClick={() => handleChange('agency_type', 'รัฐวิสาหกิจ')}
          className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl whitespace-nowrap transition-all border ${
            filters.agency_type === 'รัฐวิสาหกิจ'
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold shadow-sm'
              : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
          }`}
        >
          <span>รัฐวิสาหกิจ</span>
        </button>

        <button
          onClick={() => handleChange('agency_type', 'ส่วนราชการ')}
          className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl whitespace-nowrap transition-all border ${
            filters.agency_type === 'ส่วนราชการ'
              ? 'bg-blue-500/20 text-blue-300 border-blue-500/40 font-semibold shadow-sm'
              : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
          }`}
        >
          <span>ส่วนราชการ</span>
        </button>
      </div>

      {/* Bottom row: Filter selectors */}
      <div className="flex flex-wrap items-center gap-2.5 pt-1 text-xs">
        <span className="text-slate-400 flex items-center space-x-1">
          <Filter className="w-3.5 h-3.5 text-slate-500" />
          <span>ตัวกรอง:</span>
        </span>

        {/* Agency Type Dropdown */}
        <select
          value={filters.agency_type || 'ALL'}
          onChange={(e) => handleChange('agency_type', e.target.value)}
          className="bg-slate-900/90 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-300 focus:outline-none focus:border-cyan-500"
        >
          <option value="ALL" className="bg-slate-900">ทุกประเภทองค์กร</option>
          <option value="สถาบันการเงิน" className="bg-slate-900">🏦 สถาบันการเงิน</option>
          <option value="บริษัทเอกชนชั้นนำ" className="bg-slate-900">🏢 บริษัทเอกชนชั้นนำ</option>
          <option value="รัฐวิสาหกิจ" className="bg-slate-900">รัฐวิสาหกิจ</option>
          <option value="องค์กรกำกับดูแล" className="bg-slate-900">องค์กรกำกับดูแล</option>
          <option value="ส่วนราชการ" className="bg-slate-900">ส่วนราชการ</option>
          <option value="องค์การมหาชน" className="bg-slate-900">องค์การมหาชน</option>
        </select>

        {/* Status */}
        <select
          value={filters.status || 'ALL'}
          onChange={(e) => handleChange('status', e.target.value)}
          className="bg-slate-900/90 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-300 focus:outline-none focus:border-cyan-500"
        >
          <option value="ALL" className="bg-slate-900">ทุกสถานะระเบียน</option>
          <option value="OPEN" className="bg-slate-900">สถานะระเบียน: OPEN</option>
          <option value="CLOSING_SOON" className="bg-slate-900">สถานะระเบียน: CLOSING_SOON</option>
          <option value="IN_PROGRESS" className="bg-slate-900">โครงการระหว่างดำเนินการ</option>
          <option value="UNKNOWN" className="bg-slate-900">ต้นทางไม่ระบุสถานะ</option>
          <option value="CLOSED" className="bg-slate-900">ปิดรับแล้ว</option>
        </select>

        {/* Verification */}
        <select
          value={filters.verification_status || 'ALL'}
          onChange={(e) => handleChange('verification_status', e.target.value)}
          className="bg-slate-900/90 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-300 focus:outline-none focus:border-cyan-500"
        >
          <option value="ALL" className="bg-slate-900">ทุกระดับการยืนยัน</option>
          <option value="VERIFIED" className="bg-slate-900">✓ ยืนยันจาก structured source</option>
          <option value="PENDING" className="bg-slate-900">รอตรวจ field mapping</option>
        </select>

        {/* Budget presets */}
        <div className="flex items-center space-x-1 bg-slate-900/60 p-0.5 rounded-lg border border-slate-800">
          <button
            onClick={() => handleBudgetPreset('ALL')}
            className={`px-2 py-1 rounded text-[11px] ${
              isBudgetActive('ALL') ? 'bg-cyan-500/20 text-cyan-400 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            ทุกงบ
          </button>
          <button
            onClick={() => handleBudgetPreset('UNDER_1M')}
            className={`px-2 py-1 rounded text-[11px] ${
              isBudgetActive('UNDER_1M') ? 'bg-cyan-500/20 text-cyan-400 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            &lt; 1 ล้าน
          </button>
          <button
            onClick={() => handleBudgetPreset('1M_5M')}
            className={`px-2 py-1 rounded text-[11px] ${
              isBudgetActive('1M_5M') ? 'bg-cyan-500/20 text-cyan-400 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            1 - 5 ล้าน
          </button>
          <button
            onClick={() => handleBudgetPreset('5M_15M')}
            className={`px-2 py-1 rounded text-[11px] ${
              isBudgetActive('5M_15M') ? 'bg-cyan-500/20 text-cyan-400 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            5 - 15 ล้าน
          </button>
          <button
            onClick={() => handleBudgetPreset('OVER_15M')}
            className={`px-2 py-1 rounded text-[11px] ${
              isBudgetActive('OVER_15M') ? 'bg-cyan-500/20 text-cyan-400 font-semibold' : 'text-slate-400 hover:text-white'
            }`}
          >
            &gt; 15 ล้าน
          </button>
        </div>

        {/* Reset button */}
        {(filters.q || filters.agency_type !== 'ALL' || filters.status !== 'ALL' || filters.verification_status !== 'ALL' || filters.open_for_bidding === false || filters.min_budget || filters.max_budget) && (
          <button
            onClick={onReset}
            className="text-xs text-rose-400 hover:text-rose-300 ml-auto flex items-center space-x-1"
          >
            <span>ล้างตัวกรอง</span>
          </button>
        )}
      </div>
    </div>
  );
}
