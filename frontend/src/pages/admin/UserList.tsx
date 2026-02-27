import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";

type User = {
  id: number;
  display_name: string;
  email: string;
  avatar: string;
  last_seen: string | null;
  last_ip: string | null;
  banned: boolean;
  created_at: string;
};

export default function UserList() {
  const [list, setList] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    authFetch("/api/admin/users")
      .then((r) => (r.ok ? r.json() : []))
      .then(setList)
      .catch(() => setList([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function ban(id: number) {
    if (!confirm("Ban this user?")) return;
    const r = await authFetch(`/api/admin/users/${id}/ban`, { method: "POST" });
    if (r.ok) load();
  }

  async function remove(id: number) {
    if (!confirm("Permanently delete this user? This cannot be undone.")) return;
    const r = await authFetch(`/api/admin/users/${id}`, { method: "DELETE" });
    if (r.ok) load();
  }

  if (loading) return <p className="text-text-muted">Loading...</p>;

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">Users</h3>
      {list.length === 0 ? (
        <p className="text-text-muted">No users yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text-muted">
                <th className="py-2 pr-2">ID</th>
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">Email</th>
                <th className="py-2 pr-2">Last seen</th>
                <th className="py-2 pr-2">Banned</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.id} className="border-b border-border-dark">
                  <td className="py-2 pr-2 text-text-primary">{u.id}</td>
                  <td className="py-2 pr-2 text-text-primary">{u.display_name || "-"}</td>
                  <td className="py-2 pr-2 text-text-secondary">{u.email || "-"}</td>
                  <td className="py-2 pr-2 text-text-secondary">{u.last_seen ? new Date(u.last_seen).toLocaleString() : "-"}</td>
                  <td className="py-2 pr-2 text-text-secondary">{u.banned ? "Yes" : "No"}</td>
                  <td className="py-2 flex gap-2">
                    {!u.banned && (
                      <button
                        onClick={() => ban(u.id)}
                        className="ks-btn rounded bg-ks-warning/20 px-2 py-1 text-ks-warning hover:bg-ks-warning hover:text-bg-primary"
                      >
                        Ban
                      </button>
                    )}
                    <button
                      onClick={() => remove(u.id)}
                      className="ks-btn rounded bg-ks-danger/20 px-2 py-1 text-ks-danger hover:bg-ks-danger hover:text-white"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
