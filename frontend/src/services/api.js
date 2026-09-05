// Same-origin by default. On Netlify the `/api/*` proxy in `_redirects` points
// at the deployed backend, so nothing here changes. Set VITE_API_BASE at build
// time only to call a backend directly, which then needs CORS_ORIGINS set on it.
const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/+$/, '') || '/api';

export async function fetchBuyerWatch(params, signal) {
  const res = await fetch(`${API_BASE}/buyers/watch?${new URLSearchParams(params)}`, { signal });
  if (!res.ok) throw new Error('Unable to load buyer activity');
  return res.json();
}

const TENDER_FILTER_KEYS = new Set([
  'q',
  'category',
  'agency_type',
  'status',
  'min_budget',
  'max_budget',
  'pipeline_stage',
  'is_bookmarked',
  'verification_status',
  'data_origin',
  'verified_only',
  'official_only',
  'open_for_bidding',
  'opportunity_scope',
  'include_quarantined',
  'sort_by',
  'limit',
  'offset',
]);

export function serializeTenderFilters(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, val]) => {
    if (
      TENDER_FILTER_KEYS.has(key)
      && val !== undefined
      && val !== null
      && val !== ''
      && val !== 'ALL'
    ) {
      query.append(key, val);
    }
  });
  return query.toString();
}

export function getTenderExportUrl(params = {}) {
  const query = serializeTenderFilters(params);
  return `${API_BASE}/tenders/export/csv${query ? `?${query}` : ''}`;
}

export async function fetchTenders(params = {}) {
  const query = serializeTenderFilters(params);
  const res = await fetch(`${API_BASE}/tenders${query ? `?${query}` : ''}`);
  if (!res.ok) throw new Error('Failed to fetch tenders');
  return res.json();
}

export async function fetchTender(id) {
  const res = await fetch(`${API_BASE}/tenders/${encodeURIComponent(id)}`);
  if (!res.ok) {
    const error = new Error(`Failed to fetch tender (${res.status})`);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export async function updateTender(id, data) {
  const res = await fetch(`${API_BASE}/tenders/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update tender');
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

export async function triggerScan() {
  const res = await fetch(`${API_BASE}/scan`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger scan');
  return res.json();
}

export async function fetchScanLogs() {
  const res = await fetch(`${API_BASE}/scan/logs`);
  if (!res.ok) throw new Error('Failed to fetch scan logs');
  return res.json();
}

export async function fetchSources() {
  const res = await fetch(`${API_BASE}/sources`);
  if (!res.ok) throw new Error('Failed to fetch sources');
  return res.json();
}

export async function toggleSource(id) {
  const res = await fetch(`${API_BASE}/sources/${id}/toggle`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to toggle source');
  return res.json();
}

export async function createSource(data) {
  const res = await fetch(`${API_BASE}/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create source');
  return res.json();
}

export async function deleteSource(id) {
  const res = await fetch(`${API_BASE}/sources/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete source');
  return res.json();
}

export async function testSource(data) {
  const res = await fetch(`${API_BASE}/sources/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'ทดสอบดึงข้อมูลไม่สำเร็จ');
  }
  return res.json();
}

export async function fetchNotificationChannels() {
  const res = await fetch(`${API_BASE}/notifications/channels`);
  if (!res.ok) throw new Error('Failed to fetch notification channels');
  return res.json();
}

export async function updateNotificationChannel(id, data) {
  const res = await fetch(`${API_BASE}/notifications/channels/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update notification channel');
  return res.json();
}

export async function testNotificationChannel(id) {
  const res = await fetch(`${API_BASE}/notifications/test/${id}`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to test notification channel');
  return res.json();
}

export async function fetchNotificationLogs() {
  const res = await fetch(`${API_BASE}/notifications/logs`);
  if (!res.ok) throw new Error('Failed to fetch notification logs');
  return res.json();
}

export async function markNotificationsRead() {
  const res = await fetch(`${API_BASE}/notifications/mark-read`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to mark notifications read');
  return res.json();
}
