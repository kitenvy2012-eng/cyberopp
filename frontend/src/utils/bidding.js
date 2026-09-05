export const BIDDING_STATE_CONFIG = {
  OPEN_NOW: {
    label: 'เปิดรับข้อเสนออยู่',
    description: 'อยู่ในช่วงยื่นข้อเสนอตามวันเริ่มและวันสิ้นสุดที่ตรวจจากประกาศเชิญ',
    badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  },
  UPCOMING: {
    label: 'รอวันเปิดรับ',
    description: 'มีประกาศและกำหนดเวลาแล้ว แต่ยังไม่ถึงวันเริ่มยื่นข้อเสนอ',
    badge: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  },
  EXPIRED: {
    label: 'พ้นกำหนดยื่นข้อเสนอ',
    description: 'เลยกำหนดสิ้นสุดตามหลักฐานที่บันทึกไว้แล้ว',
    badge: 'bg-slate-800 text-slate-400 border-slate-700',
  },
  CLOSED: {
    label: 'ปิดรับข้อเสนอ',
    description: 'แหล่งข้อมูลระบุว่าการรับข้อเสนอสิ้นสุดหรือปิดแล้ว',
    badge: 'bg-slate-800 text-slate-400 border-slate-700',
  },
  STALE: {
    label: 'ต้องตรวจสถานะใหม่',
    description: 'หลักฐานกำหนดเวลาล่าสุดเกินช่วงตรวจสอบ 24 ชั่วโมง',
    badge: 'bg-rose-500/10 text-rose-300 border-rose-500/25',
  },
  UNCONFIRMED: {
    label: 'ยังกำหนดเวลายื่นไม่ได้',
    description: 'ยังไม่มีหลักฐานวันเริ่มและวันสิ้นสุดครบ จึงไม่นับว่าเปิดรับ',
    badge: 'bg-amber-500/10 text-amber-300 border-amber-500/25',
  },
};

export function getBiddingStateConfig(state) {
  return BIDDING_STATE_CONFIG[normalizeBiddingState(state)];
}

export function normalizeBiddingState(state) {
  return Object.prototype.hasOwnProperty.call(BIDDING_STATE_CONFIG, state)
    ? state
    : 'UNCONFIRMED';
}

export function formatThaiDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString('th-TH', {
    dateStyle: 'medium',
    timeZone: 'Asia/Bangkok',
  });
}

export function formatThaiDateTime(value) {
  if (!value) return null;
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return String(value);
    return value.toLocaleString('th-TH', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'Asia/Bangkok',
    });
  }
  const raw = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    return `${formatThaiDate(raw)} (ต้นทางไม่ระบุเวลา)`;
  }
  const isoLike = raw.includes(' ') ? raw.replace(' ', 'T') : raw;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(isoLike);
  const parsed = new Date(hasTimezone ? isoLike : `${isoLike}Z`);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString('th-TH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Bangkok',
  });
}

export function formatRelativeDate(value) {
  if (!value) return null;
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  const diffTime = now.getTime() - target.getTime();
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return 'เร็วๆ นี้';
  if (diffDays === 0) return 'ประกาศวันนี้';
  if (diffDays === 1) return 'ประกาศเมื่อวาน';
  if (diffDays < 7) return `ประกาศเมื่อ ${diffDays} วันก่อน`;
  if (diffDays < 30) return `ประกาศเมื่อ ${Math.floor(diffDays / 7)} สัปดาห์ก่อน`;
  if (diffDays < 365) return `ประกาศเมื่อ ${Math.floor(diffDays / 30)} เดือนก่อน`;
  return `${Math.floor(diffDays / 365)} ปีที่แล้ว`;
}
