import React, { useState, useEffect } from 'react';
import { Shield, Bell, RefreshCw, Download, Layers, Radio, Settings, CheckCheck, ExternalLink } from 'lucide-react';
import { triggerScan, fetchNotificationLogs, markNotificationsRead } from '../services/api';

export default function Navbar({ activeTab, setActiveTab, onScanComplete, onOpenSettings, onOpenSources, onSelectTender }) {
  const [scanning, setScanning] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [showNotifMenu, setShowNotifMenu] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const loadNotifications = async () => {
    try {
      const logs = await fetchNotificationLogs();
      setNotifications(logs);
      const unread = logs.filter(n => n.status === 'UNREAD').length;
      setUnreadCount(unread);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setScanning(true);
    try {
      const res = await triggerScan();
      await loadNotifications();
      if (onScanComplete) onScanComplete(res);
    } catch (e) {
      alert('การสแกนล้มเหลว: ' + e.message);
    } finally {
      setScanning(false);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markNotificationsRead();
      setUnreadCount(0);
      loadNotifications();
    } catch (e) {
      console.error(e);
    }
  };

  const handleExportCSV = () => {
    window.open('/api/tenders/export/csv', '_blank');
  };

  return (
    <header className="sticky top-0 z-40 bg-[#0F172A]/90 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Name */}
          <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setActiveTab('tenders')}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-xl tracking-tight text-white">Cyber<span className="text-cyan-400">Watch</span></span>
                <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">Intelligence</span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">ระบบติดตามจัดซื้อจัดจ้างงาน Cybersecurity</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="hidden md:flex items-center space-x-1 bg-slate-900/60 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setActiveTab('tenders')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'tenders'
                  ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Radio className="w-4 h-4" />
              <span>ข้อมูลจัดซื้อทั้งหมด</span>
            </button>

            <button
              onClick={() => setActiveTab('pipeline')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'pipeline'
                  ? 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>Opportunity Pipeline</span>
            </button>

            <button
              onClick={onOpenSources}
              className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-all"
            >
              <span>แหล่งข้อมูล</span>
            </button>

            <button
              onClick={onOpenSettings}
              className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 transition-all"
            >
              <Settings className="w-4 h-4" />
              <span>ตั้งค่าแจ้งเตือน</span>
            </button>
          </nav>

          {/* Actions */}
          <div className="flex items-center space-x-2">
            {/* Scan Now Button */}
            <button
              onClick={handleScan}
              disabled={scanning}
              className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-xs sm:text-sm font-medium transition-all shadow-md shadow-cyan-500/20 active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">{scanning ? 'กำลังสแกน...' : 'สแกนเดี๋ยวนี้'}</span>
            </button>

            {/* Export CSV */}
            <button
              onClick={handleExportCSV}
              title="ส่งออกรายการเป็น CSV/Excel"
              className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 transition-all"
            >
              <Download className="w-4 h-4" />
            </button>

            {/* Notification Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowNotifMenu(!showNotifMenu)}
                className="relative p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 transition-all"
              >
                <Bell className="w-4 h-4" />
                {unreadCount > 0 && (
                  <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow-lg animate-pulse">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Menu Panel */}
              {showNotifMenu && (
                <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-2xl bg-[#131B2B] border border-slate-700 shadow-2xl p-4 z-50">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-white text-sm">การแจ้งเตือนประกาศใหม่</span>
                      {unreadCount > 0 && (
                        <span className="px-2 py-0.5 rounded-full text-[11px] bg-rose-500/20 text-rose-400 font-medium">
                          {unreadCount} ใหม่
                        </span>
                      )}
                    </div>
                    {unreadCount > 0 && (
                      <button
                        onClick={handleMarkAllRead}
                        className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center space-x-1"
                      >
                        <CheckCheck className="w-3.5 h-3.5" />
                        <span>อ่านแล้วทั้งหมด</span>
                      </button>
                    )}
                  </div>

                  <div className="mt-3 max-h-80 overflow-y-auto space-y-2.5 pr-1">
                    {notifications.length === 0 ? (
                      <div className="text-center py-6 text-slate-500 text-xs">ยังไม่มีรายการแจ้งเตือน</div>
                    ) : (
                      notifications.map(n => (
                        <div
                          key={n.id}
                          className={`p-3 rounded-xl border text-xs transition-all cursor-pointer ${
                            n.status === 'UNREAD'
                              ? 'bg-slate-800/80 border-cyan-500/30'
                              : 'bg-slate-900/40 border-slate-800 text-slate-400'
                          }`}
                          onClick={() => {
                            if (n.tender_id && onSelectTender) {
                              onSelectTender(n.tender_id);
                              setShowNotifMenu(false);
                            }
                          }}
                        >
                          <div className="flex items-start justify-between">
                            <span className="font-medium text-slate-200 line-clamp-1">{n.title}</span>
                            <span className="text-[10px] text-slate-500 ml-2 whitespace-nowrap">
                              {new Date(n.created_at).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-400 line-clamp-2">{n.message}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
