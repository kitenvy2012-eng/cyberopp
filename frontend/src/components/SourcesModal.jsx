import React, { useState, useEffect } from 'react';
import { X, Globe, Plus, Trash2, CheckCircle2, AlertTriangle, ExternalLink, RefreshCw, Play, Loader2, Calendar, ShieldCheck, Building } from 'lucide-react';
import { fetchSources, toggleSource, createSource, deleteSource, testSource } from '../services/api';

export default function SourcesModal({ isOpen, onClose, onRefresh }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSource, setNewSource] = useState({
    name: '',
    url: '',
    source_type: 'CUSTOM_WEB',
    agency_type: 'บริษัทเอกชนชั้นนำ',
    item_selector: ''
  });
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchSources();
      setSources(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) load();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleToggle = async (id) => {
    try {
      await toggleSource(id);
      load();
      if (onRefresh) onRefresh();
    } catch (e) {
      alert('ไม่สามารถสลับสถานะได้: ' + e.message);
    }
  };

  const handleTestUrl = async () => {
    if (!newSource.url) {
      alert('กรุณากรอก URL หน้าจัดซื้อจัดจ้างก่อนทดสอบ');
      return;
    }
    setIsTesting(true);
    setTestError('');
    setTestResult(null);
    try {
      const res = await testSource({
        url: newSource.url,
        name: newSource.name,
        agency_type: newSource.agency_type,
        item_selector: newSource.item_selector || null,
      });
      setTestResult(res);
      if (res.suggested_agency_type && (!newSource.name || newSource.agency_type === 'บริษัทเอกชนชั้นนำ')) {
        setNewSource(prev => ({ ...prev, agency_type: res.suggested_agency_type }));
      }
    } catch (err) {
      setTestError(err.message || 'เกิดข้อผิดพลาดในการทดสอบ');
    } finally {
      setIsTesting(false);
    }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newSource.name || !newSource.url) {
      alert('กรุณากรอกชื่อและ URL ของเว็บไซต์');
      return;
    }
    try {
      const configObj = {};
      if (newSource.name) configObj.agency_name = newSource.name;
      if (newSource.agency_type) configObj.agency_type = newSource.agency_type;
      if (newSource.item_selector) configObj.item_selector = newSource.item_selector;

      await createSource({
        name: newSource.name,
        url: newSource.url,
        source_type: newSource.agency_type === 'บริษัทเอกชนชั้นนำ' ? 'CORPORATE' : 'CUSTOM_WEB',
        config_json: Object.keys(configObj).length > 0 ? JSON.stringify(configObj) : null
      });
      setShowAddForm(false);
      setNewSource({ name: '', url: '', source_type: 'CUSTOM_WEB', agency_type: 'บริษัทเอกชนชั้นนำ', item_selector: '' });
      setTestResult(null);
      setTestError('');
      load();
      if (onRefresh) onRefresh();
    } catch (e) {
      alert('เพิ่มแหล่งข้อมูลไม่สำเร็จ: ' + e.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('ยืนยันการลบแหล่งข้อมูลนี้?')) return;
    try {
      await deleteSource(id);
      load();
      if (onRefresh) onRefresh();
    } catch (e) {
      alert('ลบไม่สำเร็จ: ' + e.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl bg-[#131B2B] border border-slate-700 shadow-2xl p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
              <Globe className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">จัดการแหล่งข้อมูลประกาศ (Procurement Sources)</h3>
              <p className="text-xs text-slate-400">ควบคุมเว็บไซต์เป้าหมาย เพิ่มและทดสอบ URL จัดซื้อจัดจ้างของบริษัทเอกชนและหน่วยงาน</p>
            </div>
          </div>

          <button onClick={onClose} className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Add Source Toggle Button */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-300">แหล่งข้อมูลที่ระบบติดตาม ({sources.length})</span>
          <button
            onClick={() => {
              setShowAddForm(!showAddForm);
              setTestResult(null);
              setTestError('');
            }}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 text-xs font-medium transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{showAddForm ? 'ปิดแบบฟอร์ม' : 'เพิ่มเว็บไซต์เป้าหมายใหม่'}</span>
          </button>
        </div>

        {/* Add Source Form */}
        {showAddForm && (
          <form onSubmit={handleAdd} className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-white">เพิ่มเว็บไซต์จัดซื้อจัดจ้าง / ประกวดราคา</span>
              <span className="text-[11px] text-slate-400">รองรับทั้งบริษัทเอกชนและหน่วยงาน</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">ชื่อหน่วยงาน / บริษัท</label>
                <input
                  type="text"
                  placeholder="เช่น บริษัท ปูนซิเมนต์ไทย จำกัด (มหาชน), ธนาคาร..."
                  value={newSource.name}
                  onChange={(e) => setNewSource({ ...newSource, name: e.target.value })}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                  required
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">กลุ่มองค์กร</label>
                <select
                  value={newSource.agency_type}
                  onChange={(e) => setNewSource({ ...newSource, agency_type: e.target.value })}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="บริษัทเอกชนชั้นนำ">🏢 บริษัทเอกชนชั้นนำ (Corporate)</option>
                  <option value="สถาบันการเงิน">🏦 สถาบันการเงิน (Financial)</option>
                  <option value="ส่วนราชการ">🏛️ ส่วนราชการ (Government)</option>
                  <option value="รัฐวิสาหกิจ">⚡ รัฐวิสาหกิจ (State Enterprise)</option>
                  <option value="องค์การมหาชน">🌐 องค์การมหาชน (Public Org)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-[11px] text-slate-400 block mb-1">URL หน้าประกาศจัดซื้อจัดจ้าง</label>
              <input
                type="url"
                placeholder="https://example.com/procurement หรือ /bidding"
                value={newSource.url}
                onChange={(e) => setNewSource({ ...newSource, url: e.target.value })}
                className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono text-[11px]"
                required
              />
            </div>

            <div>
              <label className="text-[11px] text-slate-400 block mb-1">CSS Selector สำหรับรายการประกาศ (ไม่บังคับ - ตรวจจับอัตโนมัติ)</label>
              <input
                type="text"
                placeholder="เช่น table tr, .tender-item, .post-content (เว้นว่างได้)"
                value={newSource.item_selector}
                onChange={(e) => setNewSource({ ...newSource, item_selector: e.target.value })}
                className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono text-[11px]"
              />
            </div>

            {/* Test Preview Section */}
            {isTesting && (
              <div className="p-3 rounded-lg bg-slate-800/80 border border-slate-700 flex items-center space-x-2 text-xs text-cyan-300">
                <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                <span>กำลังเชื่อมต่อไปยัง URL เพื่อทดสอบดึงข้อมูลประกาศ...</span>
              </div>
            )}

            {testError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-start space-x-2 text-xs text-rose-300">
                <AlertTriangle className="w-4 h-4 text-rose-400 mt-0.5 flex-shrink-0" />
                <span>{testError}</span>
              </div>
            )}

            {testResult && (
              <div className="p-3.5 rounded-xl bg-slate-800/90 border border-cyan-500/30 space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>ผลการทดสอบ: พบ {testResult.total_items_found} รายการ</span>
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                    สถานะ: {testResult.status}
                  </span>
                </div>

                {testResult.sample_items.length > 0 ? (
                  <div className="space-y-1.5 pt-1">
                    <span className="text-[11px] text-slate-400 font-medium">ตัวอย่างรายการที่ตรวจพบ ({testResult.sample_items.length} รายการแรก):</span>
                    {testResult.sample_items.map((item, idx) => (
                      <div key={idx} className="p-2 rounded bg-slate-900/80 border border-slate-700/80 space-y-1 text-[11px]">
                        <div className="font-medium text-slate-200 line-clamp-1">{item.title}</div>
                        <div className="flex flex-wrap items-center gap-2 text-slate-400 text-[10px]">
                          {item.announcement_date && <span>📅 ประกาศ: {item.announcement_date}</span>}
                          {item.submission_deadline && <span>⏱️ ปิดรับ: {item.submission_deadline}</span>}
                          {item.is_cyber_relevant && (
                            <span className="text-emerald-400 font-medium">🛡️ เกี่ยวข้องกับ Cyber</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-amber-300">
                    เข้าถึงหน้าเว็บได้สำเร็จ แต่ไม่พบรายการประกาศที่ตรงกับ selector (ลองระบุ CSS Selector เพิ่มเติม)
                  </p>
                )}
              </div>
            )}

            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                onClick={handleTestUrl}
                disabled={isTesting || !newSource.url}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-cyan-300 text-xs font-semibold transition-all border border-cyan-500/30 flex items-center space-x-1.5"
              >
                {isTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-cyan-400 text-cyan-400" />}
                <span>ทดสอบดึงข้อมูล (Test URL)</span>
              </button>

              <button
                type="submit"
                className="px-4 py-1.5 rounded-lg bg-cyan-500 text-slate-950 text-xs font-semibold hover:bg-cyan-400 transition-all shadow-md shadow-cyan-500/20"
              >
                บันทึกแหล่งข้อมูลใหม่
              </button>
            </div>
          </form>
        )}

        {/* Source List */}
        <div className="space-y-2.5">
          {sources.map(s => (
            <div
              key={s.id}
              className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between gap-3 text-xs"
            >
              <div className="space-y-1 min-w-0">
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-white truncate">{s.name}</span>
                  <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                    {s.source_type}
                  </span>
                  {s.last_status === 'SUCCESS' && (
                    <span className="text-[10px] text-emerald-400 flex items-center space-x-0.5">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>ดึงข้อมูลได้</span>
                    </span>
                  )}
                  {s.last_status === 'PARTIAL' && (
                    <span className="text-[10px] text-amber-400 flex items-center space-x-0.5">
                      <AlertTriangle className="w-3 h-3" />
                      <span>สำเร็จบางส่วน</span>
                    </span>
                  )}
                  {s.last_status === 'FAILED' && (
                    <span className="text-[10px] text-rose-400 flex items-center space-x-0.5">
                      <AlertTriangle className="w-3 h-3" />
                      <span>ดึงไม่สำเร็จ</span>
                    </span>
                  )}
                  {s.last_status === 'DISABLED_UNVERIFIED' && (
                    <span className="text-[10px] text-slate-400 flex items-center space-x-0.5">
                      <AlertTriangle className="w-3 h-3" />
                      <span>URL เดิมยังไม่ยืนยัน</span>
                    </span>
                  )}
                  {s.last_status === 'DISABLED_BLOCKED_BY_SOURCE' && (
                    <span className="text-[10px] text-slate-400 flex items-center space-x-0.5">
                      <AlertTriangle className="w-3 h-3" />
                      <span>ต้นทางบล็อกการเข้าถึง</span>
                    </span>
                  )}
                  {s.last_status === 'DISABLED_JS_RENDERED' && (
                    <span className="text-[10px] text-slate-400 flex items-center space-x-0.5">
                      <AlertTriangle className="w-3 h-3" />
                      <span>ต้นทางเรนเดอร์ด้วย JavaScript</span>
                    </span>
                  )}
                </div>

                <div className="text-[11px] text-slate-400 truncate flex items-center space-x-2">
                  <a href={s.url} target="_blank" rel="noreferrer" className="hover:text-cyan-400 truncate flex items-center space-x-1">
                    <span>{s.url}</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                </div>
              </div>

              <div className="flex items-center space-x-3 flex-shrink-0">
                {/* Active Toggle */}
                <button
                  onClick={() => handleToggle(s.id)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                    s.is_active
                      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                      : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                >
                  {s.is_active ? 'กำลังเปิดสแกน' : 'ปิดการสแกน'}
                </button>

                {s.source_type === 'CUSTOM_WEB' && (
                  <button
                    onClick={() => handleDelete(s.id)}
                    className="p-1.5 rounded-lg text-rose-400 hover:bg-rose-500/10 transition-all"
                    title="ลบแหล่งข้อมูล"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
