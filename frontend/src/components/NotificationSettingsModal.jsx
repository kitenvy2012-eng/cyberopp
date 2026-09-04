import React, { useState, useEffect } from 'react';
import { X, BellRing, Send, CheckCircle2, AlertCircle, MessageSquare, Shield, HelpCircle } from 'lucide-react';
import { fetchNotificationChannels, updateNotificationChannel, testNotificationChannel } from '../services/api';

export default function NotificationSettingsModal({ isOpen, onClose }) {
  const [channels, setChannels] = useState([]);
  const [testingId, setTestingId] = useState(null);
  const [testResult, setTestResult] = useState({});
  const [savingId, setSavingId] = useState(null);

  const load = async () => {
    try {
      const data = await fetchNotificationChannels();
      setChannels(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (isOpen) load();
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFieldChange = (id, field, value) => {
    setChannels(prev => prev.map(c => c.id === id ? { ...c, [field]: value } : c));
  };

  const handleSave = async (channel) => {
    setSavingId(channel.id);
    try {
      await updateNotificationChannel(channel.id, channel);
      alert('บันทึกการตั้งค่าช่องทาง ' + channel.name + ' เรียบร้อย');
      load();
    } catch (e) {
      alert('บันทึกไม่สำเร็จ: ' + e.message);
    } finally {
      setSavingId(null);
    }
  };

  const handleTest = async (channelId) => {
    setTestingId(channelId);
    setTestResult(prev => ({ ...prev, [channelId]: null }));
    try {
      const res = await testNotificationChannel(channelId);
      setTestResult(prev => ({ ...prev, [channelId]: res }));
    } catch (e) {
      setTestResult(prev => ({ ...prev, [channelId]: { success: false, error: e.message } }));
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl bg-[#131B2B] border border-slate-700 shadow-2xl p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
              <BellRing className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">ตั้งค่าการแจ้งเตือนประกาศใหม่ (Alert Integrations)</h3>
              <p className="text-xs text-slate-400">กำหนดช่องทางรับแจ้งเตือนอัตโนมัติเมื่อระบบสแกนพบประกาศโครงการใหม่</p>
            </div>
          </div>

          <button onClick={onClose} className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Channel Cards */}
        <div className="space-y-4">
          {channels.map(channel => (
            <div key={channel.id} className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-white text-sm">{channel.name}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-cyan-400 border border-slate-700">
                    {channel.channel_type}
                  </span>
                </div>

                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={channel.is_enabled}
                    onChange={(e) => handleFieldChange(channel.id, 'is_enabled', e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500"></div>
                </label>
              </div>

              {/* Form fields depending on channel type */}
              {channel.channel_type === 'LINE_NOTIFY' && (
                <div className="space-y-2 text-xs">
                  <div>
                    <label className="text-slate-400 block mb-1">LINE Notify Token (รับได้จาก notify-bot.line.me)</label>
                    <input
                      type="password"
                      value={channel.token || ''}
                      onChange={(e) => handleFieldChange(channel.id, 'token', e.target.value)}
                      placeholder="ใส่ LINE Token ที่สร้างจากกลุ่มหรือส่วนตัว..."
                      className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-100 text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
              )}

              {channel.channel_type === 'DISCORD' && (
                <div className="space-y-2 text-xs">
                  <div>
                    <label className="text-slate-400 block mb-1">Discord Webhook URL</label>
                    <input
                      type="text"
                      value={channel.target_url || ''}
                      onChange={(e) => handleFieldChange(channel.id, 'target_url', e.target.value)}
                      placeholder="https://discord.com/api/webhooks/..."
                      className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-100 text-xs focus:outline-none focus:border-cyan-500 font-mono text-[11px]"
                    />
                  </div>
                </div>
              )}

              {channel.channel_type === 'TELEGRAM' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  <div>
                    <label className="text-slate-400 block mb-1">Bot Token</label>
                    <input
                      type="password"
                      value={channel.token || ''}
                      onChange={(e) => handleFieldChange(channel.id, 'token', e.target.value)}
                      placeholder="เช่น 123456:ABC-DEF..."
                      className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-100 text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Chat ID</label>
                    <input
                      type="text"
                      value={channel.chat_id || ''}
                      onChange={(e) => handleFieldChange(channel.id, 'chat_id', e.target.value)}
                      placeholder="เช่น -100123456789 หรือ user id"
                      className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-100 text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>
              )}

              {/* Filter: Min Budget */}
              <div className="flex items-center space-x-3 text-xs pt-1">
                <span className="text-slate-400">แจ้งเฉพาะโครงการที่มีงบประมาณตั้งแต่:</span>
                <input
                  type="number"
                  step="100000"
                  value={channel.min_budget || 0}
                  onChange={(e) => handleFieldChange(channel.id, 'min_budget', parseFloat(e.target.value) || 0)}
                  className="w-32 px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-slate-200 text-xs focus:outline-none focus:border-cyan-500 font-semibold"
                />
                <span className="text-slate-400">บาทขึ้นไป (0 = แจ้งทุกงบ)</span>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
                <div>
                  {testResult[channel.id] && (
                    <span className={`flex items-center space-x-1 ${testResult[channel.id].success ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {testResult[channel.id].success ? (
                        <>
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>ทดสอบสำเร็จ! ข้อความถูกส่งแล้ว</span>
                        </>
                      ) : (
                        <>
                          <AlertCircle className="w-3.5 h-3.5" />
                          <span>ทดสอบล้มเหลว: ตรวจสอบ Token/URL</span>
                        </>
                      )}
                    </span>
                  )}
                </div>

                <div className="flex items-center space-x-2">
                  {channel.channel_type !== 'IN_APP' && (
                    <button
                      onClick={() => handleTest(channel.id)}
                      disabled={testingId === channel.id}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-all flex items-center space-x-1"
                    >
                      <Send className={`w-3.5 h-3.5 ${testingId === channel.id ? 'animate-pulse' : ''}`} />
                      <span>{testingId === channel.id ? 'กำลังทดสอบ...' : 'ทดสอบส่งข้อความ'}</span>
                    </button>
                  )}

                  <button
                    onClick={() => handleSave(channel)}
                    disabled={savingId === channel.id}
                    className="px-3.5 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold transition-all shadow-md shadow-cyan-500/20"
                  >
                    {savingId === channel.id ? 'กำลังบันทึก...' : 'บันทึก'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
