import React from 'react';
import { Bookmark, Calendar, Building2, Landmark, Building, ChevronRight, AlertCircle, Shield, BadgeCheck, CircleDashed, ExternalLink } from 'lucide-react';

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
    badge: "bg-indigo-500/10 text-indigo-300 border-indigo-500/30",
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

export default function TenderCard({ tender, onSelect, onToggleBookmark, onUpdatePipeline }) {
  const catStyle = CATEGORY_STYLES[tender.category] || CATEGORY_STYLES["OTHER"];
  const agencyConfig = AGENCY_TYPE_CONFIG[tender.agency_type] || {
    badge: "bg-slate-800 text-slate-400 border-slate-700/60",
    icon: Building2,
    prefix: ""
  };
  const AgencyIcon = agencyConfig.icon;

  // Calculate days remaining
  const getDaysRemaining = (deadline) => {
    if (!deadline) return null;
    const diff = new Date(deadline) - new Date();
    const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
    return days;
  };

  const daysRemaining = getDaysRemaining(tender.submission_deadline);

  const formatPrice = (val) => {
    if (!val || val === 0) return 'ไม่ระบุงบประมาณ';
    return val.toLocaleString('th-TH') + ' บาท';
  };

  const subTags = tender.sub_categories ? tender.sub_categories.split(',').map(s => s.trim()) : [];

  return (
    <div className="group rounded-2xl bg-[#131B2B]/90 border border-slate-800 hover:border-cyan-500/40 p-4 sm:p-5 transition-all shadow-md hover:shadow-cyan-500/5 flex flex-col justify-between relative overflow-hidden">
      {/* Top row: Category, Sector badge, Urgency badge, Bookmark */}
      <div>
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
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

            {daysRemaining !== null && daysRemaining > 0 && daysRemaining <= 7 && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse flex items-center space-x-1">
                <AlertCircle className="w-3 h-3" />
                <span>เหลืออีก {daysRemaining} วัน</span>
              </span>
            )}

            {daysRemaining !== null && daysRemaining <= 0 && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-800 text-slate-500 border border-slate-700">
                ปิดรับซองแล้ว
              </span>
            )}

            {!tender.submission_deadline && tender.status === 'IN_PROGRESS' && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30">
                ระหว่างดำเนินการ
              </span>
            )}

            {!tender.submission_deadline && tender.status === 'UNKNOWN' && (
              <span className="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
                ต้นทางไม่ระบุสถานะ
              </span>
            )}
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

        {/* Project Title */}
        <h3
          onClick={() => onSelect(tender)}
          className="mt-3 text-base font-semibold text-white group-hover:text-cyan-300 transition-colors cursor-pointer line-clamp-2 leading-snug"
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
          {tender.submission_deadline && (
            <div className="flex items-center space-x-1 text-slate-400 text-[11px] mr-1">
              <Calendar className="w-3.5 h-3.5 text-slate-500" />
              <span>{tender.submission_deadline}</span>
            </div>
          )}

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
