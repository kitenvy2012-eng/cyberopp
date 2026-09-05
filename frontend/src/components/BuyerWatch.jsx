import React, { useEffect, useState } from 'react';
import { fetchBuyerWatch } from '../services/api';
import { formatThaiDate, formatThaiDateTime } from '../utils/bidding';

const HEALTH = { HEALTHY: 'อ่านต้นทางได้', NOT_CHECKED: 'ยังไม่ตรวจ', REGISTRATION_ONLY: 'ช่องทางลงทะเบียนคู่ค้า', WARNING: 'อ่านได้บางส่วน', FAILED: 'ตรวจต้นทางไม่สำเร็จ', DISABLED: 'ปิดการติดตาม', STALE_SOURCE: 'ต้องตรวจซ้ำ' };
const KIND = { INVITATION: 'ประกาศเชิญ — ต้องตรวจวันยื่น', AWARDED: 'ได้ผู้ชนะแล้ว', CANCELLED: 'ยกเลิกแล้ว', DRAFT: 'ร่าง / รับฟังความคิดเห็น', UNKNOWN: 'ยังไม่ยืนยันประเภท' };

export default function BuyerWatch({ refreshKey = 0 }) {
  const [buyers, setBuyers] = useState([]);
  const [privateOnly, setPrivateOnly] = useState(true);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let running = false;
    const load = async () => {
      if (running) return;
      running = true;
      try {
        const rows = await fetchBuyerWatch({ private_only: privateOnly, q }, controller.signal);
        if (!controller.signal.aborted) { setBuyers(rows); setError(''); }
      } catch (e) {
        if (!controller.signal.aborted) setError('โหลดกิจกรรมล่าสุดไม่สำเร็จ ข้อมูลที่ค้างอยู่ไม่ใช่การยืนยันสถานะปัจจุบัน');
      } finally { running = false; if (!controller.signal.aborted) setLoading(false); }
    };
    setLoading(true);
    const debounce = setTimeout(load, 180);
    const refresh = () => { if (document.visibilityState === 'visible') load(); };
    const timer = setInterval(refresh, 60000);
    window.addEventListener('focus', refresh);
    return () => { controller.abort(); clearTimeout(debounce); clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [privateOnly, q, refreshKey]);

  return <section className="space-y-5">
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold text-white">ติดตามประกาศรายบริษัท</h1>
      <p className="text-sm text-slate-400">เรียงตามวันที่เผยแพร่ที่ยืนยันได้จากต้นทาง ไม่ใช่วันที่ระบบเพิ่งดึงเจอ</p>
      <p className="text-xs text-slate-500">แสดงเฉพาะประกาศจากแหล่งที่เชื่อมและตรวจพบ ไม่ใช่จำนวนประกาศทั้งหมดของแต่ละบริษัท</p>
      <p className="text-xs text-amber-200 bg-amber-950/20 border border-amber-500/20 rounded-xl p-3">ประกาศทั่วไปและช่องทางคู่ค้าไม่เท่ากับงานไซเบอร์ที่เปิดรับ หากไม่มีวันที่เผยแพร่จะระบุว่า “ต้นทางไม่ระบุ” โดยไม่ใช้วันยื่นแบบ ชื่อไฟล์ หรือวันที่ตรวจพบแทน</p>
    </div>
    <div className="flex flex-wrap gap-3">
      <input aria-label="ค้นหาบริษัท" value={q} onChange={e => setQ(e.target.value)} placeholder="ชื่อบริษัท เช่น SCB, AIS, True…" className="flex-1 min-w-48 rounded-xl bg-slate-900 border border-slate-700 px-4 py-2 text-sm" />
      <select aria-label="ประเภทบริษัทที่ติดตาม" value={privateOnly ? 'private' : 'all'} onChange={e => setPrivateOnly(e.target.value === 'private')} className="rounded-xl bg-slate-900 border border-slate-700 px-3 py-2 text-sm"><option value="private">เอกชน / บริษัทจดทะเบียน</option><option value="all">ทุกองค์กร รวมภาครัฐ</option></select>
    </div>
    {error && <div role="alert" className="rounded-xl p-3 bg-rose-950 text-rose-200">{error}</div>}
    <div className="text-xs text-slate-400">{loading ? 'กำลังตรวจข้อมูล…' : `เป้าหมาย ${buyers.length} บริษัท • มีช่องทางบันทึกไว้ ${buyers.filter(b => b.sources.length).length} บริษัท • ยังต้องค้นหาแหล่งเพิ่ม ${buyers.filter(b => !b.sources.length).length} บริษัท`}</div>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {buyers.map(b => <article key={b.id} className="rounded-2xl bg-slate-900/70 border border-slate-800 p-5 space-y-4">
        <div><h2 className="font-semibold text-slate-100">{b.name}</h2><p className="text-xs text-slate-500 mt-1">{b.name_en || b.domain} • {b.industry}</p></div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div><div className="text-slate-400">ประกาศจัดซื้อล่าสุดที่มีวันที่</div><div className="text-white mt-1">{formatThaiDate(b.latest_procurement_date) || 'ยังยืนยันวันที่ไม่ได้'}</div></div>
          <div><div className="text-slate-400">ประกาศไซเบอร์ล่าสุด (ไม่รวมผู้ชนะ)</div><div className="text-white mt-1">{formatThaiDate(b.latest_cyber_opportunity_date) || 'ยังไม่มีหลักฐานที่ระบุวันที่'}</div></div>
          <div><div className="text-slate-400">ประกาศที่ระบุวันที่ใน 30 วัน</div><div className="text-white mt-1">{b.procurement_count_30d} รายการ • ไม่ระบุวัน {b.undated_count}</div></div>
          <div><div className="text-slate-400">ยืนยันช่วงยื่นจากหลักฐานล่าสุด</div><div className="text-cyan-300 mt-1">{b.actionable_count} งาน (รวมรอเปิด)</div></div>
        </div>
        {!b.sources.length && <p className="text-xs text-amber-300 border border-amber-500/20 rounded-xl p-3">ยังไม่พบช่องทางที่เชื่อมและตรวจสอบแล้ว — ไม่ได้แปลว่าบริษัทนี้ไม่มีประกาศหรือไม่มีงาน</p>}
        {b.sources.map(s => <div key={s.id} className="text-xs bg-slate-950/60 rounded-xl p-3 space-y-2">
          <a href={s.url} target="_blank" rel="noreferrer" className="text-cyan-300 underline">{s.name} ↗</a>
          <div className="text-amber-200">{HEALTH[s.health] || s.health}{s.requires_authentication ? ' • บางส่วนต้องลงทะเบียน/รับเชิญ' : ''}</div>
          <div className="text-slate-400">ตรวจต้นทางล่าสุด: {formatThaiDateTime(s.checked_at) || 'ยังไม่มีผลตรวจ'}</div>
          {s.notes && <p className="text-slate-400 leading-relaxed">{s.notes}</p>}
        </div>)}
        {b.notices.length > 0 && <details className="text-xs"><summary className="cursor-pointer text-cyan-300">ดูหลักฐานประกาศที่พบ ({b.notices.length} รายการล่าสุดที่แสดง)</summary><div className="mt-3 space-y-3">{b.notices.map((n, i) => <div key={i} className="border-t border-slate-800 pt-3 space-y-1"><a href={n.url} target="_blank" rel="noreferrer" className="text-slate-200 underline leading-relaxed">{n.title}</a><div className="text-amber-200">{KIND[n.notice_status] || n.notice_status}{n.is_cyber ? ' • เกี่ยวข้องไซเบอร์' : ' • ประกาศทั่วไป'}</div><div className="text-slate-400">เผยแพร่: {formatThaiDate(n.published_date) || 'ต้นทางไม่ระบุ'} • ระบบพบครั้งแรก: {formatThaiDateTime(n.first_seen_at)}</div></div>)}</div></details>}
      </article>)}
    </div>
    {!loading && !buyers.length && !error && <p className="text-slate-400">ไม่พบบริษัทตรงกับตัวกรอง</p>}
  </section>;
}
