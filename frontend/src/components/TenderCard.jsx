import React from 'react';
import { Bookmark, Calendar, Building2, Landmark, Building, ChevronRight, AlertCircle, Shield, BadgeCheck, CircleDashed, ExternalLink, Award, FileText } from 'lucide-react';
import { formatThaiDate, formatThaiDateTime, formatRelativeDate, getBiddingStateConfig, normalizeBiddingState } from '../utils/bidding';

const CATEGORY_STYLES = {
  "VA_PENTEST": {
    label: "VA / Pentest / Red Team",
    badge: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    dot: "bg-rose-500"
  },
  "AUDIT_COMPLIANCE": {
    label: "Audit & Compliance",
    badge: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    dot: "bg-emerald-500"
  },
  "SOC_MSSP": {
    label: "SOC & MSSP",
    badge: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    dot: "bg-blue-500"
  },
  "SOLUTION_IMPLEMENTATION": {
    label: "Security Solution",
    badge: "bg-purple-500/15 text-purple-400 border-purple-500/30",
    dot: "bg-purple-500"
  },
  "INCIDENT_RESPONSE": {
    label: "Incident Response",
    badge: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    dot: "bg-amber-500"
  },
  "TRAINING_DRILL": {
    label: "Training & Drill",
    badge: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
    dot: "bg-cyan-500"
  },
  "OTHER": {
    label: "Cybersecurity",
    badge: "bg-slate-500/15 text-slate-300 border-slate-500/30",
    dot: "bg-slate-400"
  }
};

const AGENCY_TYPE_CONFIG = {
  "สถาบันการเงิน": {
    badge: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    icon: Landmark,
    prefix: "🏦 "
  },
  "บริษัทเอกชนชั้นนำ": {
    badge: "bg-indigo-500/15 text-indigo-300 border-indigo-500/40",
    icon: Building,
    prefix: "🏢 "
  },
  "องค์กรกำกับดูแล": {
    badge: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    icon: Building2,
    prefix: "⚖️ "
  },
  "รัฐวิสาหกิจ": {
    badge: "bg-blue-500/10 text-blue-300 border-blue-500/30",
    icon: Building2,
    prefix: ""
  },
  "ส่วนราชการ": {
    badge: "bg-slate-800 text-slate-300 border-slate-700/60",
    icon: Building2,
    prefix: ""
  }
};

export default function TenderCard({ tender, onSelect, onToggleBookmark, onUpdatePipeline, dataStale = false }) {
  const catStyle = CATEGORY_STYLES[tender.category] || CATEGORY_STYLES["OTHER"];
  const agencyConfig = AGENCY_TYPE_CONFIG[tender.agency_type] || {
    badge: "bg-slate-800 text-slate-400 border-slate-700/60",
    icon: Building2,
    prefix: ""
  };
  const AgencyIcon = agencyConfig.icon;

  const biddingState = normalizeBiddingState(tender.bidding_state);
  const bidding = getBiddingStateConfig(biddingState);
  const bidStart = formatThaiDateTime(tender.bid_start_date);
  const bidDeadline = formatThaiDateTime(tender.bid_deadline_at);
  const announceDate = formatThaiDate(tender.announcement_date);
  const announceRelative = formatRelativeDate(tender.announcement_date);

  const isAwarded = tender.bid_notice_status === 'AWARDED' || tender.status === 'CLOSED';
  const isDraft = tender.bid_notice_status === 'DRAFT';
  const isInvitation = tender.bid_notice_status === 'INVITATION';

  const formatPrice = (val) => {
    if (!val || val === 0) return 'ไม่ระบุงบประมาณ';
    return val.toLocaleString('th-TH') + ' บาท';
  };

  const subTags = tender.sub_categories ? tender.sub_categories.split(',').map(s => s.trim()) : [];

  return (
    <div className={`group rounded-2xl bg-[#131B2B]/90 border ${isAwarded ? 'border-slate-800/80 opacity-80' : 'border-slate-800 hover:border-cyan-500/40'} p-4 sm:p-5 transition-all shadow-md hover:shadow-cyan-500/5 flex flex-col justify-between relative overflow-hidden`}>
      {/* Top row: Badges, Status, Bookmark */}
      <div>
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            {dataStale && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-rose-500/10 text-rose-300 border border-rose-500/30 flex items-center gap-1" title="การรีเฟรช API ครั้งล่าสุดไม่สำเร็จ โปรดเปิดหลักฐานต้นทางก่อนตัดสินใจ">
                <AlertCircle className="w-3 h-3" />
                snapshot อาจล้าสมัย
              </span>
            )}

            {/* Opportunity Status Badges */}
            {isAwarded && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center gap-1">
                <Award className="w-3 h-3 text-purple-400" />
                มีผู้ชนะแล้ว (สัญญาแล้ว)
              </span>
            )}
            {isInvitation && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                เปิดรับข้อเสนออยู่
              </span>
            )}
            {isDraft && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30 flex items-center gap-1">
                <FileText className="w-3 h-3 text-blue-400" />
                ร่างประกาศ / รับฟังวิจารณ์
              </span>
            )}

            {tender.verification_status === 'VERIFIED' ? (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                <BadgeCheck className="w-3 h-3" />
                ตรวจต้นทางแล้ว
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-amber-500/10 text-amber-300 border border-amber-500/25 flex items-center gap-1">
                <CircleDashed className="w-3 h-3" />
                รอยืนยัน
              </span>
            )}

            <span className={`px-2.5 py-1 rounded-lg text-xs font-semibold border flex items-center space-x-1.5 ${catStyle.badge}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${catStyle.dot}`}></span>
              <span>{catStyle.label}</span>
            </span>

            <span className={`px-2 py-0.5 rounded-md text-[11px] font-medium border flex items-center space-x-1 ${agencyConfig.badge}`}>
              <span>{agencyConfig.prefix}{tender.agency_type}</span>
            </span>

            <span
              title={bidding.description}
              className={`px-2 py-0.5 rounded-md text-[11px] font-medium border flex items-center gap-1 ${bidding.badge}`}
            >
              {['UNCONFIRMED', 'STALE'].includes(biddingState) ? (
                <AlertCircle className="w-3 h-3" />
              ) : (
                <Calendar className="w-3 h-3" />
              )}
              <span>{bidding.label}</span>
            </span>
          </div>

          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleBookmark(tender);
            }}
            className={`p-1.5 rounded-lg border transition-all ${
              tender.is_bookmarked
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-400'
                : 'bg-slate-800/60 border-slate-700/60 text-slate-400 hover:text-slate-200'
            }`}
            title={tender.is_bookmarked ? 'ยกเลิกบุ๊กมาร์ก' : 'บันทึกเป็นโครงการที่สนใจ'}
          >
            <Bookmark className={`w-4 h-4 ${tender.is_bookmarked ? 'fill-amber-400' : ''}`} />
          </button>
        </div>

        {/* Announcement Date Bar (Latest Date) */}
        {announceDate && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs text-cyan-300/90 font-medium">
            <span className="flex items-center gap-1 text-slate-400">
              <Calendar className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
              <span>วันที่ประกาศลงระบบ:</span>
            </span>
            <span className="text-slate-100 font-semibold">{announceDate}</span>
            {announceRelative && (
              <span className="px-1.5 py-0.2 rounded text-[10px] bg-cyan-500/20 text-cyan-200 border border-cyan-500/30">
                {announceRelative}
              </span>
            )}
          </div>
        )}

        {/* Project Title */}
        <h3
          onClick={() => onSelect(tender)}
          className="mt-2.5 text-base font-semibold text-white group-hover:text-cyan-300 transition-colors cursor-pointer line-clamp-2 leading-snug"
        >
          {tender.title}
        </h3>

        {/* Agency info */}
        <div className="mt-2 flex items-center space-x-2 text-xs text-slate-300">
          <AgencyIcon className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
          <span className="font-medium truncate">{tender.agency}</span>
          <span className="text-slate-600">•</span>
          <span className="text-slate-400 text-[11px]">{tender.tender_code}</span>
        </div>

        {/* Requirements Snippet */}
        {tender.requirements_summary && (
          <div className="mt-2.5 p-2 rounded-lg bg-slate-900/60 border border-slate-800/80 text-[11px] text-slate-300 flex items-start space-x-1.5">
            <Shield className="w-3.5 h-3.5 text-cyan-400 mt-0.5 flex-shrink-0" />
            <span className="line-clamp-1">{tender.requirements_summary}</span>
          </div>
        )}

        {/* Sub-tags */}
        {subTags.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1">
            {subTags.slice(0, 4).map((tag, i) => (
              <span key={i} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800/80 text-cyan-400/90 border border-slate-700/40">
                #{tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Bottom row: Budget, Deadline, Action */}
      <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div>
          <span className="text-[11px] text-slate-400 block">งบประมาณโครงการ</span>
          <span className="text-sm font-bold text-cyan-400">
            {formatPrice(tender.budget)}
          </span>
          {tender.median_price > 0 && tender.median_price !== tender.budget && (
            <span className="text-[10px] text-slate-500 ml-1.5 block sm:inline">
              (ราคากลาง: {(tender.median_price / 1000000).toFixed(2)}M)
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2">
          {(tender.source_record_url || tender.source_url) && (
            <a
              href={tender.source_record_url || tender.source_url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              title="เปิดหลักฐานต้นทาง"
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-emerald-300 border border-slate-700"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          <div className="flex flex-col items-end gap-0.5 text-[11px] mr-1">
            {biddingState === 'UPCOMING' && bidStart && (
              <div className="flex items-center space-x-1 text-blue-300">
                <Calendar className="w-3.5 h-3.5" />
                <span>เริ่ม {bidStart}</span>
              </div>
            )}
            <div className="flex items-center space-x-1 text-slate-400">
              <Calendar className="w-3.5 h-3.5 text-slate-500" />
              <span>{bidDeadline ? `ปิด ${bidDeadline}` : 'ยังยืนยันกำหนดปิดไม่ได้'}</span>
            </div>
            {tender.bid_evidence_url && (
              <a
                href={tender.bid_evidence_url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3" />
                หลักฐานกำหนดเวลา
              </a>
            )}
          </div>

          <button
            onClick={() => onSelect(tender)}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-cyan-500 hover:text-slate-950 text-slate-200 text-xs font-medium transition-all"
          >
            <span>ดูรายละเอียด</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
