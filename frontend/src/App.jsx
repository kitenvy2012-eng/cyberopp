import React, { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import DashboardStats from './components/DashboardStats';
import FilterBar from './components/FilterBar';
import TenderCard from './components/TenderCard';
import TenderDetailModal from './components/TenderDetailModal';
import PipelineBoard from './components/PipelineBoard';
import SourcesModal from './components/SourcesModal';
import NotificationSettingsModal from './components/NotificationSettingsModal';
import { fetchTenders, fetchStats, updateTender } from './services/api';
import { ShieldCheck, Inbox, Loader2, AlertTriangle } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('tenders'); // 'tenders' | 'pipeline'
  const [stats, setStats] = useState(null);
  const [tenders, setTenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTender, setSelectedTender] = useState(null);
  const [isSourcesOpen, setIsSourcesOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const [filters, setFilters] = useState({
    q: '',
    category: 'ALL',
    agency_type: 'ALL',
    status: 'ALL',
    verification_status: 'ALL',
    min_budget: '',
    max_budget: '',
    sort_by: 'newest'
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, tendersData] = await Promise.all([
        fetchStats(),
        fetchTenders(filters)
      ]);
      setStats(statsData);
      setTenders(tendersData);
    } catch (e) {
      console.error('Failed to load data:', e);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Audio notification chime
  const playAlertSound = () => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
      osc.frequency.setValueAtTime(880, ctx.currentTime + 0.1); // A5
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } catch (e) {
      // AudioContext might be blocked until user interaction
    }
  };

  const handleScanComplete = (result) => {
    loadData();
    if (result.status === 'SKIPPED') {
      alert(`มีรอบสแกนกำลังทำงานอยู่แล้ว — ${result.details || 'โปรดลองใหม่ภายหลัง'}`);
    } else if (result.status === 'FAILED') {
      alert(`❌ สแกนไม่สำเร็จ\n${result.details || 'กรุณาตรวจสอบแหล่งข้อมูลและ API key'}`);
    } else if (result.status === 'PARTIAL') {
      alert(`⚠️ สแกนได้บางส่วน พบใหม่ ${result.new_found || 0} รายการ\n${result.details || ''}`);
    } else if (result.new_found > 0) {
      playAlertSound();
      alert(`🎉 พบประกาศ Cybersecurity ใหม่ ${result.new_found} รายการ!`);
    } else {
      alert('สแกนเสร็จสิ้น ไม่พบประกาศใหม่เพิ่มเติม');
    }
  };

  const handleToggleBookmark = async (tender) => {
    try {
      const updated = await updateTender(tender.id, { is_bookmarked: !tender.is_bookmarked });
      setTenders(prev => prev.map(t => t.id === tender.id ? updated : t));
      const newStats = await fetchStats();
      setStats(newStats);
    } catch (e) {
      alert('เกิดข้อผิดพลาด: ' + e.message);
    }
  };

  const handleSelectTenderById = async (tenderId) => {
    try {
      const res = await fetch(`/api/tenders/${tenderId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedTender(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleResetFilters = () => {
    setFilters({
      q: '',
      category: 'ALL',
      agency_type: 'ALL',
      status: 'ALL',
      verification_status: 'ALL',
      min_budget: '',
      max_budget: '',
      sort_by: 'newest'
    });
  };

  return (
    <div className="min-h-screen bg-[#0B0F17] text-slate-100 flex flex-col selection:bg-cyan-500/25 selection:text-cyan-300">
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onScanComplete={handleScanComplete}
        onOpenSources={() => setIsSourcesOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onSelectTender={handleSelectTenderById}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs">
          <div className="flex items-start gap-2 text-emerald-200">
            <ShieldCheck className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
            <div>
              <span className="font-semibold">โหมดข้อมูลจริง</span>
              <span className="text-emerald-300/75"> — ไม่มีข้อมูล demo/mock อยู่ในระบบแล้ว ทุกรายการมาจากการดึงสดจากแหล่งจริงและมีลิงก์หลักฐานย้อนกลับได้</span>
            </div>
          </div>
          {(stats?.pending_tenders > 0 || stats?.quarantined_tenders > 0) && (
            <div className="flex items-center gap-1.5 text-amber-300 whitespace-nowrap">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>รอตรวจ {stats?.pending_tenders || 0} • กักกัน {stats?.quarantined_tenders || 0}</span>
            </div>
          )}
        </div>

        {/* KPI Dashboard Overview */}
        <DashboardStats
          stats={stats}
          selectedCategory={filters.category}
          onSelectCategory={(cat) => setFilters(prev => ({ ...prev, category: cat }))}
          selectedSector={filters.agency_type}
          onSelectSector={(sector) => setFilters(prev => ({ ...prev, agency_type: sector }))}
        />

        {/* Tab 1: All Tenders Explorer */}
        {activeTab === 'tenders' && (
          <div className="space-y-4">
            {/* Filter & Search Bar */}
            <FilterBar
              filters={filters}
              setFilters={setFilters}
              onReset={handleResetFilters}
            />

            {/* Results Header */}
            <div className="flex items-center justify-between px-1 text-xs text-slate-400">
              <div>
                พบทั้งหมด <span className="font-semibold text-cyan-400">{tenders.length}</span> โครงการ
                {filters.category !== 'ALL' && <span> ในหมวด <span className="text-white">{filters.category}</span></span>}
              </div>
              {stats?.latest_scan?.completed_at && (
                <div className="hidden sm:block text-[11px] text-slate-500">
                  สแกนล่าสุด: {new Date(stats.latest_scan.completed_at).toLocaleTimeString('th-TH')}
                </div>
              )}
            </div>

            {/* Tenders Grid */}
            {loading ? (
              <div className="min-h-[300px] flex flex-col items-center justify-center space-y-3 text-slate-500">
                <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
                <span className="text-xs">กำลังโหลดข้อมูลประกาศจัดซื้อจัดจ้าง...</span>
              </div>
            ) : tenders.length === 0 ? (
              <div className="min-h-[300px] rounded-2xl bg-[#131B2B]/60 border border-slate-800 flex flex-col items-center justify-center p-8 text-center space-y-3">
                <Inbox className="w-12 h-12 text-slate-600" />
                <div className="space-y-1">
                  <h4 className="text-base font-semibold text-slate-300">ไม่พบประกาศที่ตรงตามเงื่อนไข</h4>
                  <p className="text-xs text-slate-500 max-w-md">ลองเปลี่ยนคำค้นหา หรือกดล้างตัวกรองเพื่อดูโครงการทั้งหมด</p>
                </div>
                <button
                  onClick={handleResetFilters}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-400 text-xs font-semibold transition-all border border-slate-700"
                >
                  ล้างตัวกรองทั้งหมด
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {tenders.map(tender => (
                  <TenderCard
                    key={tender.id}
                    tender={tender}
                    onSelect={(t) => setSelectedTender(t)}
                    onToggleBookmark={handleToggleBookmark}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Opportunity Pipeline Board */}
        {activeTab === 'pipeline' && (
          <PipelineBoard
            tenders={tenders}
            onSelectTender={(t) => setSelectedTender(t)}
            onRefresh={loadData}
          />
        )}
      </main>

      {/* Modals */}
      {selectedTender && (
        <TenderDetailModal
          tender={selectedTender}
          onClose={() => setSelectedTender(null)}
          onUpdate={() => {
            loadData();
          }}
        />
      )}

      <SourcesModal
        isOpen={isSourcesOpen}
        onClose={() => setIsSourcesOpen(false)}
        onRefresh={loadData}
      />

      <NotificationSettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-[#0B0F17] py-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center space-x-2">
            <span className="font-semibold text-slate-400">CyberWatch Thailand</span>
            <span>—</span>
            <span>Source-backed Cybersecurity Procurement Intelligence</span>
          </div>
          <div className="text-[11px] text-slate-600">
            แสดงผลตามหลักฐานที่ดึงได้จริง พร้อมสถานะ VERIFIED / PENDING / QUARANTINED
          </div>
        </div>
      </footer>
    </div>
  );
}
