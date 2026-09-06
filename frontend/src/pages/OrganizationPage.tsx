import { useQuery } from "@tanstack/react-query";
import {
  Handshake,
  LockKeyhole,
  Network,
  Smartphone,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Avatar } from "../components/Avatar";
import { notify } from "../api";
import { useAuth } from "../AuthContext";
import type { Department, User } from "../types";



interface OrganizationResponse {
  users: User[];
  departments: Department[];
}

function PersonCard({
  person,
  onOpen,
}: {
  person: User;
  onOpen: () => void;
}) {
  return (
    <button
      className={`org-card role-${person.role.toLowerCase()}`}
      onClick={onOpen}
    >
      <span className="org-avatar-wrap">
        <Avatar
          name={person.full_name}
          url={person.avatar_url}
          size="lg"
        />

        {person.is_online && <i className="online-dot" />}
      </span>

      <strong>{person.full_name}</strong>

      <span>
        {person.role}
        {person.is_system_owner ? " · BOSS chính" : ""}
      </span>

      <small>@{person.username}</small>

      <div className="org-stats">
        <span>
          <Smartphone size={13} />
          {person.machine_count} máy
        </span>

        <span>{person.account_count} kênh</span>
      </div>
    </button>
  );
}

function LeaderBranch({
  leader,
  members,
  onOpen,
}: {
  leader: User;
  members: User[];
  onOpen: (person: User) => void;
}) {
  return (
    <div className="org-branch">
      <PersonCard
        person={leader}
        onOpen={() => onOpen(leader)}
      />

      <div className="member-grid">
        {members.map((member) => (
          <PersonCard
            key={member.id}
            person={member}
            onOpen={() => onOpen(member)}
          />
        ))}

        {!members.length && (
          <div className="org-empty">Chưa có Member</div>
        )}
      </div>
    </div>
  );
}

export function OrganizationPage() {
  const navigate = useNavigate();
  const { user: current } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["organization"],
    queryFn: () =>
      api<OrganizationResponse>("/api/organization"),
  });

  const people = data?.users || [];
  const departments = data?.departments || [];

  const bosses = people.filter((item) => item.role === "BOSS");
  const managers = people.filter((item) => item.role === "MANAGER");
  const leaders = people.filter((item) => item.role === "LEADER");
  const members = people.filter((item) => item.role === "MEMBER");

  function canOpenPerson(person: User) {
    if (!current) return false;

    if (current.role === "BOSS" || current.role === "MANAGER") {
      return true;
    }

    if (current.id === person.id) {
      return true;
    }

    if (
      current.role === "LEADER" &&
      person.role === "MEMBER" &&
      person.leader_id === current.id
    ) {
      return true;
    }

    if (
      current.role === "LEADER" &&
      current.department_id &&
      current.department_id === person.department_id
    ) {
      const department = departments.find(
        (item) => item.id === current.department_id
      );

      return Boolean(
        department?.leader_collaboration_enabled &&
        ["LEADER", "MEMBER"].includes(person.role)
      );
    }

    return false;
  }

  function openPerson(person: User) {
    if (!canOpenPerson(person)) {
      notify(
        "Bạn có thể xem sơ đồ nhưng không có quyền xem kênh của người này",
        "info"
      );
      return;
    }

    navigate(`/accounts?owner=${person.id}`);
  }

  const assignedDepartmentIds = new Set(
    departments.map((department) => department.id)
  );

  const unassignedLeaders = leaders.filter(
    (leader) =>
      !leader.department_id ||
      !assignedDepartmentIds.has(leader.department_id)
  );

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TỔ CHỨC NHÂN SỰ</p>
          <h1>Sơ đồ công ty</h1>
          <p>
            BOSS → Quản lý → Phòng → Leader → Member
          </p>
        </div>

        <span className="heading-symbol">
          <Network size={24} />
        </span>
      </div>

      {isLoading ? (
        <div className="panel empty-state">
          Đang dựng sơ đồ…
        </div>
      ) : (
        <section className="org-chart panel">
          {bosses.length > 0 && (
            <div className="org-level org-boss-level">
              {bosses.map((person) => (
                <PersonCard
                  key={person.id}
                  person={person}
                  onOpen={() => openPerson(person)}
                />
              ))}
            </div>
          )}

          {managers.length > 0 && (
            <div className="org-level org-manager-level">
              {managers.map((person) => (
                <PersonCard
                  key={person.id}
                  person={person}
                  onOpen={() => openPerson(person)}
                />
              ))}
            </div>
          )}

          <div className="department-grid">
            {departments.map((department) => {
              const departmentLeaders = leaders.filter(
                (leader) =>
                  leader.department_id === department.id
              );

              return (
                <section
                  className="department-card"
                  key={department.id}
                >
                  <header className="department-heading">
                    <div>
                      <p className="eyebrow">PHÒNG</p>
                      <h2>{department.name}</h2>
                    </div>

                    <span
                      className={
                        department.leader_collaboration_enabled
                          ? "department-mode enabled"
                          : "department-mode"
                      }
                    >
                      {department.leader_collaboration_enabled ? (
                        <Handshake size={14} />
                      ) : (
                        <LockKeyhole size={14} />
                      )}

                      {department.leader_collaboration_enabled
                        ? "Hợp tác"
                        : "Riêng từng nhóm"}
                    </span>
                  </header>

                  <div className="department-leaders">
                    {departmentLeaders.map((leader) => (
                      <LeaderBranch
                        key={leader.id}
                        leader={leader}
                        members={members.filter(
                          (member) =>
                            member.leader_id === leader.id
                        )}
                        onOpen={openPerson}
                      />
                    ))}

                    {!departmentLeaders.length && (
                      <div className="org-empty">
                        Chưa có Leader trong phòng
                      </div>
                    )}
                  </div>
                </section>
              );
            })}

            {unassignedLeaders.length > 0 && (
              <section className="department-card unassigned">
                <header className="department-heading">
                  <div>
                    <p className="eyebrow">PHÒNG</p>
                    <h2>Chưa phân phòng</h2>
                  </div>
                </header>

                <div className="department-leaders">
                  {unassignedLeaders.map((leader) => (
                    <LeaderBranch
                      key={leader.id}
                      leader={leader}
                      members={members.filter(
                        (member) =>
                          member.leader_id === leader.id
                      )}
                      onOpen={openPerson}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>

          {!people.length && (
            <div className="empty-state">
              Chưa có dữ liệu nhân sự.
            </div>
          )}
        </section>
      )}
    </div>
  );
}