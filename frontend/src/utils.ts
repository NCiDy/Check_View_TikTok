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
  return role === "BOSS" ? "BOSS" : role === "LEADER" ? "LEADER" : "MEMBER";
}

export function statusLabel(status: string): string {
  if (status === "DIE") return "DIE / KHÓA";
  if (status === "UNCHECKED") return "CHƯA CHECK";
  return status;
}
