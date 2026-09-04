import React, { useState } from 'react';
import { 
  X, ExternalLink, Download, Bookmark, Calendar, Building2, Landmark, Building, 
  Shield, Check, Save, FileText, Globe, BadgeCheck, CircleDashed, Database 
} from 'lucide-react';
import { updateTender } from '../services/api';

const PIPELINE_STAGES = [
  { id: "NONE", label: "ยังไม่ติดตาม" },
  { id: "SAVED", label: "สนใจ (Saved)" },
  { id: "REVIEWING_TOR", label: "กำลังศึกษา TOR" },
  { id: "PREPARING_PROPOSAL", label: "กำลังทำราคา & ข้อเสนอ" },
  { id: "BIDDING", label: "ยื่นซองประกวดราคาแล้ว" },
  { id: "WON", label: "ชนะการประมูล (Won)" },
  { id: "LOST", label: "ไม่ได้งาน (Lost)" }
];

export default function TenderDetailModal({ tender, onClose, onUpdate }) {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'source_document' | 'provenance'
  const [pipelineStage, setPipelineStage] = useState(tender.pipeline_stage || "NONE");
  const [notes, setNotes] = useState(tender.notes || "");
  const [isBookmarked, setIsBookmarked] = useState(tender.is_bookmarked || false);
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  if (!tender) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateTender(tender.id, {
        pipeline_stage: pipelineStage,
        notes: notes,
        is_bookmarked: isBookmarked
      });
      setSavedSuccess(true);
      if (onUpdate) onUpdate(updated);
      setTimeout(() => setSavedSuccess(false), 2000);
    } catch (e) {
      alert('บันทึกไม่สำเร็จ: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  const formatPrice = (val) => {
    if (!val || val === 0) return 'ไม่ระบุงบประมาณ';
    return val.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' บาท';
  };

  const sourceDocumentUrl = tender.tor_url || null;
  const sourcePageUrl = tender.source_record_url || tender.source_url || null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl bg-[#131B2B] border border-slate-700 shadow-2xl overflow-hidden">
        
        {/* Modal Header */}
        <div className="p-4 sm:p-6 pb-3 border-b border-slate-800 flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1.5 pr-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-lg text-xs font-semibold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                  {tender.category}
                </span>
                <span className="px-2 py-0.5 rounded-md text-xs bg-slate-800 text-slate-300 border border-slate-700">
                  {tender.agency_type}
                </span>
                {tender.verification_status === 'VERIFIED' ? (
                  <span className="px-2 py-0.5 rounded-md text-xs bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                    <BadgeCheck className="w-3.5 h-3.5" /> ตรวจหลักฐานแล้ว
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-md text-xs bg-amber-500/10 text-amber-300 border border-amber-500/25 flex items-center gap-1">
                    <CircleDashed className="w-3.5 h-3.5" /> รอยืนยัน
                  </span>
                )}
                <span className="text-xs text-slate-400">เลขที่: {tender.tender_code}</span>
              </div>
              <h2 className="text-base sm:text-xl font-bold text-white leading-snug">{tender.title}</h2>
            </div>

            <button
              onClick={onClose}
              className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white transition-all flex-shrink-0"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation Tabs Inside Modal */}
          <div className="flex items-center space-x-2 mt-4 border-b border-slate-800/60 pb-1">
            <button
              onClick={() => setActiveTab('overview')}
              className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                activeTab === 'overview'
                  ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>ภาพรวม & รายละเอียด</span>
            </button>

            {sourceDocumentUrl && <button
              onClick={() => setActiveTab('source_document')}
              className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                activeTab === 'source_document'
                  ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Download className="w-4 h-4" />
              <span>📄 เอกสารต้นฉบับ</span>
            </button>}

            <button
              onClick={() => setActiveTab('provenance')}
              className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                activeTab === 'provenance'
                  ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Globe className="w-4 h-4" />
              <span>🌐 หลักฐาน & ที่มา</span>
            </button>
          </div>
        </div>

        {/* Modal Body (Scrollable) */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          
          {/* TAB 1: OVERVIEW */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Quick Actions Strip */}
              <div className="flex flex-wrap items-center justify-between gap-2.5 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                <div className="flex items-center space-x-2 text-xs">
                  <span className="text-slate-400">หลักฐานย้อนกลับ:</span>
                  {sourceDocumentUrl && <a
                    href={sourceDocumentUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2.5 py-1 rounded-md bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/40 font-medium"
                  >
                    เปิดเอกสารต้นฉบับ
                  </a>}
                  <button
                    onClick={() => setActiveTab('provenance')}
                    className="px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 hover:text-white border border-slate-700"
                  >
                    ดูที่มาข้อมูล
                  </button>
                </div>

                {sourcePageUrl && <div className="flex items-center space-x-2">
                  <a
                    href={sourcePageUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-semibold shadow-sm transition-all"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>เปิดเว็บต้นทางจริง</span>
                  </a>
                </div>}
              </div>

              {/* Overview Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-4 rounded-xl bg-slate-900/80 border border-slate-800">
                <div>
                  <span className="text-xs text-slate-400 block">หน่วยงานเจ้าของโครงการ</span>
                  <span className="text-sm font-medium text-slate-200">{tender.agency}</span>
                </div>

                <div>
                  <span className="text-xs text-slate-400 block">งบประมาณโครงการ</span>
                  <span className="text-sm font-bold text-cyan-400">{formatPrice(tender.budget)}</span>
                </div>

                <div>
                  <span className="text-xs text-slate-400 block">ราคากลาง</span>
                  <span className="text-sm font-medium text-slate-300">{formatPrice(tender.median_price)}</span>
                </div>

                <div>
                  <span className="text-xs text-slate-400 block">วิธีการจัดหา</span>
                  <span className="text-sm text-slate-200">{tender.procurement_method || 'ไม่ระบุ'}</span>
                </div>

                <div>
                  <span className="text-xs text-slate-400 block">วันที่ประกาศลงระบบ</span>
                  <span className="text-sm text-slate-200">{tender.announcement_date || '-'}</span>
                </div>

                <div>
                  <span className="text-xs text-slate-400 block">กำหนดวันสุดท้ายยื่นซอง</span>
                  <span className="text-sm font-semibold text-amber-400">{tender.submission_deadline || 'โปรดดูในประกาศ'}</span>
                </div>
              </div>

              {/* Description */}
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-white flex items-center space-x-1.5">
                  <FileText className="w-4 h-4 text-cyan-400" />
                  <span>ขอบเขตงานและรายละเอียดโครงการ</span>
                </h4>
                <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800/80 text-xs sm:text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {tender.description || 'ไม่มีรายละเอียดเพิ่มเติม'}
                </div>
              </div>

              {/* Extracted Requirements / Certificates */}
              {tender.requirements_summary && (
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-white flex items-center space-x-1.5">
                    <Shield className="w-4 h-4 text-emerald-400" />
                    <span>สรุปคุณสมบัติและข้อกำหนดสำคัญ (AI/Rule Extraction)</span>
                  </h4>
                  <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-500/30 text-xs sm:text-sm text-emerald-200">
                    {tender.requirements_summary}
                  </div>
                </div>
              )}

              {/* Pipeline & Internal Tracking Section */}
              <div className="p-4 sm:p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
                <h4 className="text-sm font-semibold text-white flex items-center justify-between">
                  <span>การติดตามสถานะโครงการ (Pipeline Management)</span>
                  <button
                    onClick={() => setIsBookmarked(!isBookmarked)}
                    className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all ${
                      isBookmarked
                        ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                        : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                    }`}
                  >
                    <Bookmark className={`w-3.5 h-3.5 ${isBookmarked ? 'fill-amber-400' : ''}`} />
                    <span>{isBookmarked ? 'บันทึกไว้แล้ว' : 'เพิ่มในรายการโปรด'}</span>
                  </button>
                </h4>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-400 mb-1.5 block">สถานะใน Pipeline</label>
                    <select
                      value={pipelineStage}
                      onChange={(e) => setPipelineStage(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
                    >
                      {PIPELINE_STAGES.map(stage => (
                        <option key={stage.id} value={stage.id}>{stage.label}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 mb-1.5 block">บันทึกเพิ่มเติม / มอบหมายทีมงาน</label>
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      rows={2}
                      placeholder="เช่น มอบหมายทีม Pentest ทำราคา, รอเอกสารผลงานจากฝ่ายกฎหมาย..."
                      className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 resize-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end space-x-3 pt-2">
                  {savedSuccess && (
                    <span className="text-xs text-emerald-400 flex items-center space-x-1">
                      <Check className="w-3.5 h-3.5" />
                      <span>บันทึกเรียบร้อย!</span>
                    </span>
                  )}
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs sm:text-sm font-semibold transition-all shadow-md shadow-cyan-500/20 active:scale-95 disabled:opacity-50"
                  >
                    <Save className="w-4 h-4" />
                    <span>{saving ? 'กำลังบันทึก...' : 'บันทึกการติดตาม'}</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: ORIGINAL SOURCE DOCUMENT ONLY */}
          {activeTab === 'source_document' && sourceDocumentUrl && (
            <div className="space-y-4">
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-sm text-emerald-100">
                <div className="flex items-start gap-2">
                  <BadgeCheck className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                  <div>
                    <div className="font-semibold">เอกสารนี้เป็นลิงก์ต้นฉบับจากแหล่งข้อมูล</div>
                    <div className="mt-1 text-xs text-emerald-300/75">ระบบไม่สร้าง TOR, ราคา, วันที่ หรือเนื้อหาแทนเจ้าของประกาศ</div>
                  </div>
                </div>
              </div>
              <a
                href={sourceDocumentUrl}
                target="_blank"
                rel="noreferrer"
                className="w-full rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold px-4 py-3 flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                เปิด / ดาวน์โหลดเอกสารจากต้นทาง
              </a>
              <p className="break-all text-[11px] text-slate-500">{sourceDocumentUrl}</p>
            </div>
          )}

          {/* TAB 3: PROVENANCE, NEVER A GENERATED SNAPSHOT */}
          {activeTab === 'provenance' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Database className="w-4 h-4 text-cyan-400" />
                หลักฐานและสายที่มาของข้อมูล
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl bg-slate-900/80 border border-slate-800 p-4 text-xs">
                <div><span className="text-slate-500 block">แหล่งข้อมูล</span><span className="text-slate-200">{tender.source_name || '-'}</span></div>
                <div><span className="text-slate-500 block">วิธีนำเข้า</span><span className="text-slate-200">{tender.data_origin || '-'}</span></div>
                <div><span className="text-slate-500 block">สถานะการยืนยัน</span><span className="text-slate-200">{tender.verification_status || 'PENDING'}</span></div>
                <div><span className="text-slate-500 block">วิธีตรวจ</span><span className="text-slate-200">{tender.verification_method || '-'}</span></div>
                <div><span className="text-slate-500 block">พบครั้งแรก</span><span className="text-slate-200">{tender.first_seen_at || tender.created_at || '-'}</span></div>
                <div><span className="text-slate-500 block">ตรวจล่าสุด</span><span className="text-slate-200">{tender.last_verified_at || tender.last_seen_at || '-'}</span></div>
                <div className="sm:col-span-2"><span className="text-slate-500 block">Evidence hash</span><span className="font-mono text-[10px] text-slate-300 break-all">{tender.evidence_hash || '-'}</span></div>
              </div>
              {Array.isArray(tender.provenance) && tender.provenance.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-300">หลักฐานที่บันทึกไว้ ({tender.provenance.length})</div>
                  {tender.provenance.map((evidence) => (
                    <div key={evidence.id} className="rounded-xl bg-slate-900/60 border border-slate-800 p-3 text-xs space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-slate-200">{evidence.source_name}</span>
                        <span className={`px-2 py-0.5 rounded border text-[10px] ${evidence.verification_status === 'VERIFIED' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-amber-500/10 border-amber-500/30 text-amber-300'}`}>
                          {evidence.source_type} • {evidence.verification_status}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                        <div><span className="text-slate-500 block">Source record ID</span><span className="text-slate-300 break-all">{evidence.source_record_id || '-'}</span></div>
                        <div><span className="text-slate-500 block">ดึงเมื่อ</span><span className="text-slate-300">{evidence.retrieved_at || '-'}</span></div>
                        <div className="sm:col-span-2"><span className="text-slate-500 block">Content SHA-256</span><span className="font-mono text-[10px] text-slate-400 break-all">{evidence.content_sha256 || '-'}</span></div>
                      </div>
                      {evidence.verification_notes && <p className="text-[11px] text-slate-400">{evidence.verification_notes}</p>}
                      <div className="flex flex-wrap gap-2">
                        {evidence.source_url && <a href={evidence.source_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1"><ExternalLink className="w-3 h-3" />เปิดแหล่งข้อมูล</a>}
                        {evidence.document_url && <a href={evidence.document_url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1"><Download className="w-3 h-3" />เปิดเอกสาร</a>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {sourcePageUrl ? (
                <a
                  href={sourcePageUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="w-full rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold px-4 py-3 flex items-center justify-center gap-2 text-sm"
                >
                  <ExternalLink className="w-4 h-4" />
                  เปิดหลักฐานบนเว็บต้นทาง
                </a>
              ) : (
                <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-xs text-amber-200">รายการนี้ยังไม่มี URL หลักฐาน จึงยังไม่ควรถือว่ายืนยันแล้ว</div>
              )}
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
