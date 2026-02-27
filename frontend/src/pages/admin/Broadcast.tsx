import { useState } from "react";
import { authFetch } from "../../lib/auth";
import { useI18n } from "../../lib/i18n";

export default function Broadcast() {
  const { t } = useI18n();
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ recipients: number; sent: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!message.trim()) return;
    setSending(true);
    setResult(null);
    setError(null);
    try {
      const r = await authFetch("/api/admin/notifications/broadcast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message.trim() }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        setResult({ recipients: data.recipients ?? 0, sent: data.sent ?? 0 });
        setMessage("");
      } else {
        setError((data.detail as string) || "Failed to send.");
      }
    } catch {
      setError("Request failed.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="ks-card">
      <h3 className="font-gaming mb-3 font-medium text-text-primary">{t("admin.broadcast")}</h3>
      <p className="mb-2 text-sm text-text-secondary">
        {t("admin.broadcastDesc")}
      </p>
      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Message to send..."
        className="ks-input mb-2 min-h-[80px]"
        rows={3}
        disabled={sending}
      />
      {error && <p className="mb-2 text-sm text-ks-danger">{error}</p>}
      {result !== null && (
        <p className="mb-2 text-sm text-text-secondary">
          Sent to {result.sent} of {result.recipients} recipients.
        </p>
      )}
      <button
        type="button"
        onClick={send}
        disabled={sending || !message.trim()}
        className="ks-btn ks-btn-primary disabled:opacity-50"
      >
        {sending ? "Sending..." : "Send to all"}
      </button>
    </div>
  );
}
