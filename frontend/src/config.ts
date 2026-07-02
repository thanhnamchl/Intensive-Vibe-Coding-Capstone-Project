export const API_BASE: string =
    (import.meta.env.VITE_API_BASE as string | undefined) ??
    'http://localhost:8000/api';

export const MAX_UPLOAD_BYTES: number =
    Number(import.meta.env.VITE_MAX_UPLOAD_BYTES) || 10 * 1024 * 1024; // 10 MB mặc định

export const CHART_COLORS = [
    '#22c55e', '#3b82f6', '#ef4444', '#eab308', '#a855f7',
    '#06b6d4', '#f97316', '#ec4899', '#14b8a6', '#6366f1'
];