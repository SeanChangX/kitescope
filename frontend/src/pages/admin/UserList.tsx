import { useEffect, useState, useCallback } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

const PAGE_SIZE = 20;

type User = {
  id: number;
  display_name: string;
  email: string;
  avatar: string;
  last_seen: string | null;
  last_ip: string | null;
  banned: boolean;
  created_at: string;
  channel: string;
};

type SortBy = "id" | "display_name" | "email" | "last_seen" | "banned" | "created_at";
type Order = "asc" | "desc";

export default function UserList() {
  const { t } = useI18n();
  const [list, setList] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadMoreLoading, setLoadMoreLoading] = useState(false);
  const [sortBy, setSortBy] = useState<SortBy>("created_at");
  const [order, setOrder] = useState<Order>("desc");
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setSearchQuery(searchInput.trim()), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const load = useCallback(
    (reset: boolean) => {
      const offset = reset ? 0 : list.length;
      if (reset) {
        setLoading(true);
        setList([]);
      } else {
        setLoadMoreLoading(true);
      }
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
        sort_by: sortBy,
        order,
      });
      if (searchQuery) params.set("q", searchQuery);
      authFetch(`/api/admin/users?${params}`)
        .then((r) => (r.ok ? r.json() : { items: [], total: 0 }))
        .then((data: { items: User[]; total: number }) => {
          if (reset) {
            setList(data.items || []);
          } else {
            setList((prev: User[]) => [...prev, ...(data.items || [])]);
          }
          setTotal(data.total ?? 0);
        })
        .catch(() => {
          if (reset) setList([]);
          setTotal(0);
        })
        .finally(() => {
          setLoading(false);
          setLoadMoreLoading(false);
        });
    },
    [list.length, sortBy, order, searchQuery]
  );

  const loadFirst = useCallback(() => load(true), [load]);

  useEffect(() => {
    load(true);
  }, [sortBy, order, searchQuery]);

  async function ban(id: number) {
    if (!confirm(t("admin.banUserConfirm"))) return;
    const r = await authFetch(`/api/admin/users/${id}/ban`, { method: "POST" });
    if (r.ok) loadFirst();
  }

  async function unban(id: number) {
    if (!confirm(t("admin.unbanUserConfirm"))) return;
    const r = await authFetch(`/api/admin/users/${id}/unban`, { method: "POST" });
    if (r.ok) loadFirst();
  }

  async function remove(id: number) {
    if (!confirm(t("admin.deleteUserConfirm"))) return;
    const r = await authFetch(`/api/admin/users/${id}`, { method: "DELETE" });
    if (r.ok) loadFirst();
  }

  const sortOptions: { value: SortBy; labelKey: string }[] = [
    { value: "id", labelKey: "admin.sortId" },
    { value: "display_name", labelKey: "admin.sortName" },
    { value: "email", labelKey: "admin.sortEmail" },
    { value: "last_seen", labelKey: "admin.sortLastSeen" },
    { value: "banned", labelKey: "admin.sortBanned" },
    { value: "created_at", labelKey: "admin.sortCreatedAt" },
  ];

  return (
    <div className="ks-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-gaming font-medium text-text-primary">{t("admin.users")}</h3>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input
            type="text"
            placeholder={t("admin.searchUsers")}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="ks-input w-40 py-1 text-sm sm:w-52"
            aria-label={t("admin.searchUsers")}
          />
          <label className="text-text-muted">{t("admin.sortBy")}</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortBy)}
            className="ks-input py-1 pr-6 text-sm"
          >
            {sortOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>
          <select
            value={order}
            onChange={(e) => setOrder(e.target.value as Order)}
            className="ks-input py-1 pr-6 text-sm"
          >
            <option value="asc">{t("admin.orderAsc")}</option>
            <option value="desc">{t("admin.orderDesc")}</option>
          </select>
        </div>
      </div>
      {loading && list.length === 0 ? (
        <p className="text-text-muted py-4">{t("common.loading")}</p>
      ) : list.length === 0 ? (
        <p className="text-text-muted py-4">{t("admin.noUsers")}</p>
      ) : (
        <>
          <p className="mb-2 text-xs text-text-muted">
            {list.length} / {total}
          </p>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text-muted">
                  <th className="py-2 pr-2">{t("admin.userId")}</th>
                  <th className="py-2 pr-2">{t("admin.userName")}</th>
                  <th className="py-2 pr-2">{t("admin.userEmail")}</th>
                  <th className="py-2 pr-2">{t("admin.userChannel")}</th>
                  <th className="py-2 pr-2">{t("admin.lastSeen")}</th>
                  <th className="py-2 pr-2">{t("admin.banned")}</th>
                  <th className="py-2">{t("admin.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {list.map((u) => (
                  <tr key={u.id} className="border-b border-border-dark">
                    <td className="py-2 pr-2 text-text-primary">{u.id}</td>
                    <td className="py-2 pr-2 text-text-primary">{u.display_name || "-"}</td>
                    <td className="py-2 pr-2 text-text-secondary">{u.email || "-"}</td>
                    <td className="py-2 pr-2 text-text-secondary">
                      {u.channel ? u.channel.split(",").map((c: string) => t(c === "line" ? "admin.line" : "admin.telegram")).join(", ") : "-"}
                    </td>
                    <td className="py-2 pr-2 text-text-secondary">{u.last_seen ? new Date(u.last_seen).toLocaleString() : "-"}</td>
                    <td className="py-2 pr-2 text-text-secondary">{u.banned ? t("admin.yes") : t("admin.no")}</td>
                    <td className="py-2 flex gap-2">
                      {!u.banned ? (
                        <button
                          onClick={() => ban(u.id)}
                          className="ks-btn rounded bg-ks-warning/20 px-2 py-1 text-ks-warning hover:bg-ks-warning hover:text-bg-primary"
                        >
                          {t("admin.ban")}
                        </button>
                      ) : (
                        <button
                          onClick={() => unban(u.id)}
                          className="ks-btn rounded bg-ks-success/20 px-2 py-1 text-ks-success hover:bg-ks-success hover:text-bg-primary"
                        >
                          {t("admin.unban")}
                        </button>
                      )}
                      <button
                        onClick={() => remove(u.id)}
                        className="ks-btn rounded bg-ks-danger/20 px-2 py-1 text-ks-danger hover:bg-ks-danger hover:text-white"
                      >
                        {t("admin.delete")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="space-y-3 md:hidden">
            {list.map((u) => (
              <div
                key={u.id}
                className="rounded border border-border-dark p-3 text-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-text-primary">{u.display_name || "-"}</span>
                  <span className="text-text-muted">ID {u.id}</span>
                </div>
                <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-text-secondary">
                  <dt>{t("admin.userEmail")}</dt>
                  <dd>{u.email || "-"}</dd>
                  <dt>{t("admin.userChannel")}</dt>
                  <dd>{u.channel ? u.channel.split(",").map((c: string) => t(c === "line" ? "admin.line" : "admin.telegram")).join(", ") : "-"}</dd>
                  <dt>{t("admin.lastSeen")}</dt>
                  <dd>{u.last_seen ? new Date(u.last_seen).toLocaleString() : "-"}</dd>
                  <dt>{t("admin.banned")}</dt>
                  <dd>{u.banned ? t("admin.yes") : t("admin.no")}</dd>
                </dl>
                <div className="mt-3 flex flex-wrap gap-2">
                  {!u.banned ? (
                    <button
                      onClick={() => ban(u.id)}
                      className="ks-btn rounded bg-ks-warning/20 px-2 py-1 text-sm text-ks-warning hover:bg-ks-warning hover:text-bg-primary"
                    >
                      {t("admin.ban")}
                    </button>
                  ) : (
                    <button
                      onClick={() => unban(u.id)}
                      className="ks-btn rounded bg-ks-success/20 px-2 py-1 text-sm text-ks-success hover:bg-ks-success hover:text-bg-primary"
                    >
                      {t("admin.unban")}
                    </button>
                  )}
                  <button
                    onClick={() => remove(u.id)}
                    className="ks-btn rounded bg-ks-danger/20 px-2 py-1 text-sm text-ks-danger hover:bg-ks-danger hover:text-white"
                  >
                    {t("admin.delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>
          {list.length < total && (
            <div className="mt-3 flex justify-center">
              <button
                type="button"
                onClick={() => load(false)}
                disabled={loadMoreLoading}
                className="ks-btn ks-btn-secondary disabled:opacity-50"
              >
                {loadMoreLoading ? t("common.loading") : t("admin.loadMore")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
