import { initials } from "../utils";

export function Avatar({ name, url, size = "md" }: { name: string; url?: string | null; size?: "sm" | "md" | "lg" }) {
  return (
    <span className={`avatar avatar-${size}`} aria-label={name}>
      {url ? <img src={url} alt="" /> : initials(name)}
    </span>
  );
}
