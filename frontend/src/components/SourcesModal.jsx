import React, { useState, useEffect } from 'react';
import { X, Globe, Plus, Trash2, CheckCircle2, AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';
import { fetchSources, toggleSource, createSource, deleteSource } from '../services/api';

export default function SourcesModal({ isOpen, onClose, onRefresh }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSource, setNewSource] = useState({
    name: '',
    url: '',
    source_type: 'CUSTOM_WEB',
    item_selector: ''
  });

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

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newSource.name || !newSource.url) {
      alert('กรุณากรอกชื่อและ URL ของเว็บไซต์');
      return;
    }
    try {
      const config_json = newSource.item_selector ? JSON.stringify({ item_selector: newSource.item_selector }) : null;
      await createSource({
        name: newSource.name,
        url: newSource.url,
        source_type: 'CUSTOM_WEB',
        config_json
      });
      setShowAddForm(false);
      setNewSource({ name: '', url: '', source_type: 'CUSTOM_WEB', item_selector: '' });
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
              <p className="text-xs text-slate-400">ควบคุมเว็บไซต์เป้าหมายและเพิ่ม URL ที่ต้องการให้ระบบเข้าไปดึงข้อมูล</p>
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
            onClick={() => setShowAddForm(!showAddForm)}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 text-xs font-medium transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{showAddForm ? 'ปิดแบบฟอร์ม' : 'เพิ่มเว็บไซต์เป้าหมาย'}</span>
          </button>
        </div>

        {/* Add Source Form */}
        {showAddForm && (
          <form onSubmit={handleAdd} className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3">
            <div className="text-xs font-semibold text-white">เพิ่มเว็บไซต์สำหรับดึงประกาศจัดซื้อจัดจ้าง</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">ชื่อหน่วยงาน / เว็บไซต์</label>
                <input
                  type="text"
                  placeholder="เช่น มหาวิทยาลัย..., กระทรวง..."
                  value={newSource.name}
                  onChange={(e) => setNewSource({ ...newSource, name: e.target.value })}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                  required
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">URL หน้าประกาศจัดซื้อจัดจ้าง</label>
                <input
                  type="url"
                  placeholder="https://example.com/procurement"
                  value={newSource.url}
                  onChange={(e) => setNewSource({ ...newSource, url: e.target.value })}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                  required
                />
              </div>
            </div>

            <div>
              <label className="text-[11px] text-slate-400 block mb-1">CSS Selector สำหรับรายการประกาศ (ไม่บังคับ - มีระบบตรวจจับอัตโนมัติ)</label>
              <input
                type="text"
                placeholder="เช่น table tr, .tender-item, .post-content"
                value={newSource.item_selector}
                onChange={(e) => setNewSource({ ...newSource, item_selector: e.target.value })}
                className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono text-[11px]"
              />
            </div>

            <div className="flex justify-end pt-1">
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
