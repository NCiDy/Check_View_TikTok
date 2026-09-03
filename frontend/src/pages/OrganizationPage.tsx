import { useQuery } from "@tanstack/react-query";
import { Network, Smartphone } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Avatar } from "../components/Avatar";
import type { User } from "../types";

function PersonCard({ person, onOpen }: { person: User; onOpen: () => void }) {
  return (
    <button className={`org-card role-${person.role.toLowerCase()}`} onClick={onOpen}>
      <span className="org-avatar-wrap"><Avatar name={person.full_name} url={person.avatar_url} size="lg" />{person.is_online && <i className="online-dot" />}</span>
      <strong>{person.full_name}</strong>
      <span>{person.role}{person.is_system_owner ? " · BOSS chính" : ""}</span>
      <small>@{person.username}</small>
      <div className="org-stats"><span><Smartphone size={13} /> {person.machine_count} máy</span><span>{person.account_count} kênh</span></div>
    </button>
  );
}

export function OrganizationPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["organization"],
    queryFn: () => api<{ users: User[] }>("/api/organization"),
  });
  const people = data?.users || [];
  const bosses = people.filter((item) => item.role === "BOSS");
  const leaders = people.filter((item) => item.role === "LEADER");
  const members = people.filter((item) => item.role === "MEMBER");

  return (
    <div className="page-stack">
      <div className="page-heading"><div><p className="eyebrow">TỔ CHỨC NHÂN SỰ</p><h1>Sơ đồ công ty</h1><p>Quan hệ BOSS → Leader → Member theo đúng phạm vi được phép xem.</p></div><span className="heading-symbol"><Network size={24} /></span></div>
      {isLoading ? <div className="panel empty-state">Đang dựng sơ đồ…</div> : (
        <section className="org-chart panel">
          {bosses.length > 0 && <div className="org-level org-boss-level">{bosses.map((person) => <PersonCard key={person.id} person={person} onOpen={() => navigate(`/accounts?owner=${person.id}`)} />)}</div>}
          <div className="org-branches">
            {leaders.map((leader) => (
              <div className="org-branch" key={leader.id}>
                <div className="branch-line" />
                <PersonCard person={leader} onOpen={() => navigate(`/accounts?owner=${leader.id}`)} />
                <div className="member-grid">
                  {members.filter((member) => member.leader_id === leader.id).map((member) => <PersonCard key={member.id} person={member} onOpen={() => navigate(`/accounts?owner=${member.id}`)} />)}
                  {!members.some((member) => member.leader_id === leader.id) && <div className="org-empty">Chưa có Member</div>}
                </div>
              </div>
            ))}
          </div>
          {!people.length && <div className="empty-state">Chưa có dữ liệu nhân sự.</div>}
        </section>
      )}
    </div>
  );
}
