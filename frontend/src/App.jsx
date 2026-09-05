import React, { useState, useEffect, useCallback, useRef } from 'react';
import Navbar from './components/Navbar';
import DashboardStats from './components/DashboardStats';
import FilterBar from './components/FilterBar';
import TenderCard from './components/TenderCard';
import TenderDetailModal from './components/TenderDetailModal';
import PipelineBoard from './components/PipelineBoard';
import SourcesModal from './components/SourcesModal';
import NotificationSettingsModal from './components/NotificationSettingsModal';
import { fetchTender, fetchTenders, fetchStats, updateTender } from './services/api';
import { ShieldCheck, Inbox, Loader2, AlertTriangle, RefreshCw } from 'lucide-react';
import { formatThaiDateTime } from './utils/bidding';

export default function App() {
  const [activeTab, setActiveTab] = useState('tenders'); // 'tenders' | 'pipeline'
  const [stats, setStats] = useState(null);
  const [tenders, setTenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTender, setSelectedTender] = useState(null);
  const [isSourcesOpen, setIsSourcesOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [refreshError, setRefreshError] = useState(null);
  const [lastSuccessfulRefresh, setLastSuccessfulRefresh] = useState(null);
  const latestRequestRef = useRef(0);
  const lastAutoRefreshRef = useRef(0);
  const selectedTenderRef = useRef(null);

  const [filters, setFilters] = useState({
    q: '',
    category: 'ALL',
    agency_type: 'ALL',
    status: 'ALL',
    verification_status: 'ALL',
    open_for_bidding: false,
    opportunity_scope: 'ACTIVE_ONLY',
    min_budget: '',
    max_budget: '',
    sort_by: 'newest'
  });

  const loadData = useCallback(async ({ background = false } = {}) => {
    const requestId = ++latestRequestRef.current;
    const selectedTenderId = selectedTenderRef.current?.id || null;
    if (!background) setLoading(true);
    try {
      const [statsData, tendersData, selectedTenderData] = await Promise.all([
        fetchStats(),
        fetchTenders(activeTab === 'pipeline'
          ? { ...filters, open_for_bidding: false }
          : filters),
        selectedTenderId ? fetchTender(selectedTenderId) : Promise.resolve(null),
      ]);
      if (requestId !== latestRequestRef.current) return;
      setStats(statsData);
      setTenders(tendersData);
      if (selectedTenderId && selectedTenderData) {
        setSelectedTender(previous => (
          previous?.id === selectedTenderId ? selectedTenderData : previous
        ));
      }
      setRefreshError(null);
      setLastSuccessfulRefresh(new Date());
    } catch (e) {
      console.error('Failed to load data:', e);
      if (requestId === latestRequestRef.current) {
        setRefreshError({
          message: e?.message || 'ไม่สามารถติดต่อ API ได้',
          failedAt: new Date(),
        });
      }
    } finally {
      if (requestId === latestRequestRef.current) setLoading(false);
    }
  }, [filters, activeTab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    selectedTenderRef.current = selectedTender;
  }, [selectedTender]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState !== 'visible') return;
      const now = Date.now();
      if (now - lastAutoRefreshRef.current < 1000) return;
      lastAutoRefreshRef.current = now;
      loadData({ background: true });
    };

    const interval = window.setInterval(refreshWhenVisible, 60_000);
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
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
    loadData({ background: true });
    const newRecords = Number(result.new_found || 0);
    const actionableNew = Number(result.actionable_new_found || 0);
    if (result.status === 'SKIPPED') {
      alert(`มีรอบสแกนกำลังทำงานอยู่แล้ว — ${result.details || 'โปรดลองใหม่ภายหลัง'}`);
    } else if (result.status === 'FAILED') {
      alert(`❌ สแกนไม่สำเร็จ\n${result.details || 'กรุณาตรวจสอบแหล่งข้อมูลและ API key'}`);
    } else if (result.status === 'PARTIAL') {
      if (actionableNew > 0) playAlertSound();
      alert(`⚠️ สแกนได้บางส่วน\nระเบียนใหม่ ${newRecords} รายการ (อาจรวมข้อมูลย้อนหลัง)\nโอกาสใหม่ที่ยังยื่นได้ ${actionableNew} รายการ\n${result.details || ''}`);
    } else if (actionableNew > 0) {
      playAlertSound();
      alert(`🎉 พบโอกาสใหม่ที่ยังยื่นข้อเสนอได้ ${actionableNew} รายการ\nนำเข้าระเบียนใหม่ทั้งหมด ${newRecords} รายการ (อาจรวมข้อมูลย้อนหลัง)`);
    } else if (newRecords > 0) {
      alert(`สแกนเสร็จสิ้น เพิ่มระเบียนใหม่ ${newRecords} รายการ (อาจรวมข้อมูลย้อนหลัง)\nยังไม่พบโอกาสใหม่ที่ยืนยันว่ามีเวลายื่นข้อเสนอ`);
    } else {
      alert('สแกนเสร็จสิ้น ไม่พบระเบียนหรือโอกาสยื่นข้อเสนอใหม่');
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
      const data = await fetchTender(tenderId);
      setSelectedTender(data);
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
      open_for_bidding: false,
      opportunity_scope: 'ACTIVE_ONLY',
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
        tenderFilters={activeTab === 'pipeline'
          ? { ...filters, open_for_bidding: false }
          : filters}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {refreshError && (
          <div role="alert" className="rounded-2xl border border-rose-500/40 bg-rose-950/30 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs text-rose-100">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-semibold">อัปเดตสถานะล่าสุดไม่สำเร็จ — ข้อมูลบนหน้าจออาจล้าสมัย</div>
                <div className="mt-0.5 text-rose-200/75">
                  {lastSuccessfulRefresh
                    ? `ข้อมูลที่เห็นมาจากการโหลดสำเร็จเมื่อ ${formatThaiDateTime(lastSuccessfulRefresh)}`
                    : 'ยังไม่มีการโหลดข้อมูลสำเร็จในรอบนี้'}
                  {' '}อย่าถือป้าย “เปิดรับ” เป็นสถานะปัจจุบันจนกว่าจะรีเฟรชสำเร็จหรือเปิดตรวจหลักฐานต้นทาง
                </div>
              </div>
            </div>
            <button
              onClick={() => loadData()}
              className="px-3 py-2 rounded-xl bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 text-rose-100 font-semibold flex items-center justify-center gap-1.5 whitespace-nowrap"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              ลองอัปเดตอีกครั้ง
            </button>
          </div>
        )}

        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs">
          <div className="flex items-start gap-2 text-emerald-200">
            <ShieldCheck className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
            <div>
              <span className="font-semibold">โหมดโอกาสยื่นข้อเสนอ</span>
              <span className="text-emerald-300/75"> — คัดกรองเฉพาะประกาศใหม่และยังไม่สิ้นสุดโครงการ เรียงตามวันที่ประกาศลงระบบล่าสุด</span>
            </div>
          </div>
          {(stats?.unconfirmed_deadline_tenders > 0 || stats?.pending_tenders > 0) && (
            <div className="flex items-center gap-1.5 text-amber-300 whitespace-nowrap">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>ยืนยันกำหนดเวลาไม่ได้ {stats?.unconfirmed_deadline_tenders || 0} • รอตรวจข้อมูล {stats?.pending_tenders || 0}</span>
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
                {filters.open_for_bidding
                  ? 'พบโอกาสที่ยังมีเวลายื่นข้อเสนอ '
                  : filters.opportunity_scope === 'ACTIVE_ONLY'
                  ? 'พบโอกาสใหม่ที่ยังยื่นข้อเสนอได้ '
                  : filters.opportunity_scope === 'AWARDED'
                  ? 'โครงการที่มีผู้ชนะแล้ว/สัญญาแล้ว '
                  : 'ประกาศทั้งหมด '}
                <span className="font-semibold text-cyan-400">{tenders.length}</span> โครงการ
                {filters.category !== 'ALL' && <span> ในหมวด <span className="text-white">{filters.category}</span></span>}
              </div>
              {stats?.latest_scan?.completed_at && (
                <div className="hidden sm:block text-[11px] text-slate-500">
                  สแกนล่าสุด: {formatThaiDateTime(stats.latest_scan.completed_at)}
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
                  <h4 className="text-base font-semibold text-slate-300">
                    {filters.open_for_bidding
                      ? 'ยังไม่พบประกาศที่ยืนยันว่ามีเวลายื่นข้อเสนอ'
                      : 'ไม่พบประกาศที่ตรงตามเงื่อนไข'}
                  </h4>
                  <p className="text-xs text-slate-500 max-w-lg">
                    {filters.open_for_bidding
                      ? 'ไม่ได้หมายความว่าไม่มีงาน แต่อาจยังไม่มีประกาศที่มีวันเริ่ม–วันสิ้นสุดครบและตรวจสถานะล่าสุดแล้ว'
                      : 'หน้านี้แสดงเฉพาะประกาศที่ต้นทางลงวันที่ไว้และอายุไม่เกิน 1 ปี ลองเปลี่ยนคำค้นหาหรือล้างตัวกรอง'}
                  </p>
                </div>
                <button
                  onClick={() => filters.open_for_bidding
                    ? setFilters(prev => ({ ...prev, open_for_bidding: false }))
                    : handleResetFilters()}
                  className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-400 text-xs font-semibold transition-all border border-slate-700"
                >
                  {filters.open_for_bidding ? 'ดูประกาศใหม่ล่าสุดทั้งหมด' : 'ล้างตัวกรอง'}
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {tenders.map(tender => (
                  <TenderCard
                    key={tender.id}
                    tender={tender}
                    dataStale={Boolean(refreshError)}
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
          dataStale={Boolean(refreshError)}
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
