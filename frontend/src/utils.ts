export function formatNumber(value?: number | null): string {
  return value == null ? "—" : new Intl.NumberFormat("vi-VN").format(value);
}

export function formatTime(value?: string | null): string {
  if (!value) return "Chưa có";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Chưa có" : date.toLocaleString("vi-VN");
}

export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";
}

export function roleLabel(role: string): string {
  if (role === "BOSS") return "BOSS";
  if (role === "MANAGER") return "QUẢN LÝ";
  if (role === "LEADER") return "LEADER";
  return "MEMBER";
}

export function statusLabel(status: string): string {
  if (status === "DIE") return "DIE / KHÓA";
  if (status === "UNCHECKED") return "CHƯA CHECK";
  return status;
}
