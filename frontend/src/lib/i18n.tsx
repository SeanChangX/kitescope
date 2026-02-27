import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export type Locale = "en" | "zh-TW";

const STORAGE_KEY = "kitescope-locale";

const messages: Record<Locale, Record<string, string>> = {
  en: {
    "app.name": "KiteScope",
    "nav.login": "Login",
    "nav.logout": "Logout",
    "nav.notifications": "Notifications",
    "nav.admin": "Admin",
    "nav.backToApp": "Back to app",
    "home.title": "Live streams",
    "home.subtitle": "Real-time kite detection with history and weather per location.",
    "home.noStreams": "No approved streams yet. Suggest a stream at the bottom; admin will approve.",
    "home.suggestTitle": "Suggest a stream",
    "home.suggestDesc": "Have a camera or stream URL? Submit it here for admin approval. Once approved, it will appear above with live detection and history.",
    "card.signalInterrupted": "Signal interrupted",
    "card.previewUnavailable": "Preview unavailable. Stream may be offline or inaccessible from server.",
    "card.recognitionDisabled": "Recognition disabled",
    "card.temp": "Temp",
    "card.wind10m": "Wind (10m)",
    "card.wind80m": "Wind (80m)",
    "card.condition": "Condition",
    "suggest.title": "Suggest a stream",
    "suggest.urlPlaceholder": "Stream or camera URL",
    "suggest.namePlaceholder": "Name (optional)",
    "suggest.locationPlaceholder": "Location (e.g. city or lat,lon)",
    "suggest.submit": "Submit",
    "suggest.example": "Example: https://example.com/snapshot.jpg, rtsp://ip:554/stream, or YouTube live link. Type is auto-detected.",
    "suggest.urlRequired": "Stream URL (required)",
    "suggest.locationForWeather": "Location (for weather)",
    "suggest.submitted": "Submitted for approval.",
    "suggest.failed": "Failed to submit.",
    "suggest.networkError": "Network error.",
    "suggest.optional": "(optional)",
    "suggest.submitting": "Submitting...",
    "login.title": "Login",
    "login.telegram": "Login with Telegram",
    "login.line": "Login with LINE",
    "login.lineUnavailable": "LINE login: Unavailable",
    "login.telegramUnavailable": "Telegram login: Unavailable",
    "login.signIn": "Sign in",
    "login.signInDesc": "Sign in to receive real-time kite count notifications and go kiting at the right time.",
    "login.backToHome": "Back to home",
    "notifications.title": "Notifications",
    "admin.dashboard": "Dashboard",
    "admin.sources": "Sources",
    "admin.users": "Users",
    "admin.settings": "Settings",
    "admin.liveStreams": "Live streams",
    "admin.pendingSources": "Pending sources",
    "admin.noPending": "No pending suggestions.",
    "admin.editStreamsDesc": "Edit name, location, enabled, URL, and direct embed. Direct embed: turns off recognition to save server resources. Deletion removes history and notification subscriptions.",
    "admin.noStreams": "No streams yet. Approve suggestions from the Dashboard.",
    "admin.enabled": "Enabled",
    "admin.directEmbed": "Direct embed",
    "admin.directEmbedHint": "Turn off recognition to save server resources",
    "admin.directEmbedNoYoutube": "off for YouTube, use proxy playback",
    "admin.save": "Save",
    "admin.cancel": "Cancel",
    "admin.edit": "Edit",
    "admin.delete": "Delete",
    "admin.name": "Name",
    "admin.location": "Location (place or lat,lon)",
    "admin.streamUrl": "Stream URL",
    "admin.deleteConfirm": "Delete this stream? Its history and notification subscriptions will be removed.",
    "admin.disabled": "Disabled",
    "admin.broadcast": "Broadcast",
    "admin.broadcastDesc": "Send a message to all non-banned users who have LINE or Telegram linked.",
    "admin.approve": "Approve",
    "admin.reject": "Reject",
    "admin.deleteSuggestionConfirm": "Delete this suggestion?",
    "common.loading": "Loading...",
    "card.loadingPreview": "Loading...",
    "aria.github": "GitHub repository",
  },
  "zh-TW": {
    "app.name": "KiteScope",
    "nav.login": "登入",
    "nav.logout": "登出",
    "nav.notifications": "通知設定",
    "nav.admin": "管理後台",
    "nav.backToApp": "返回首頁",
    "home.title": "即時畫面",
    "home.subtitle": "即時風箏偵測，含歷史與各地天氣。",
    "home.noStreams": "尚無已核准的畫面。請在下方建議來源，由管理員審核。",
    "home.suggestTitle": "建議畫面來源",
    "home.suggestDesc": "有攝影機或直播網址？在此提交後由管理員審核，通過後會顯示在上方並有即時偵測與歷史。",
    "card.signalInterrupted": "訊號中斷",
    "card.previewUnavailable": "無法載入預覽，來源可能離線或無法從伺服器存取。",
    "card.recognitionDisabled": "辨識已關閉",
    "card.temp": "氣溫",
    "card.wind10m": "風（10m）",
    "card.wind80m": "風（80m）",
    "card.condition": "天氣",
    "suggest.title": "建議畫面來源",
    "suggest.urlPlaceholder": "直播或攝影機網址",
    "suggest.namePlaceholder": "名稱（選填）",
    "suggest.locationPlaceholder": "地點（例如城市或 lat,lon）",
    "suggest.submit": "送出",
    "suggest.example": "例如：https://example.com/snapshot.jpg、rtsp://ip:554/stream 或 YouTube 直播連結，類型會自動判斷。",
    "suggest.urlRequired": "直播網址（必填）",
    "suggest.locationForWeather": "地點（用於天氣）",
    "suggest.submitted": "已送出，等待審核。",
    "suggest.failed": "送出失敗。",
    "suggest.networkError": "網路錯誤。",
    "suggest.optional": "（選填）",
    "suggest.submitting": "送出中…",
    "login.title": "登入",
    "login.telegram": "使用 Telegram 登入",
    "login.line": "使用 LINE 登入",
    "login.lineUnavailable": "LINE 登入：不可用",
    "login.telegramUnavailable": "Telegram 登入：不可用",
    "login.signIn": "登入",
    "login.signInDesc": "登入後可接收即時風箏數量通知，掌握放風箏好時機。",
    "login.backToHome": "返回首頁",
    "notifications.title": "通知設定",
    "admin.dashboard": "儀表板",
    "admin.sources": "來源",
    "admin.users": "使用者",
    "admin.settings": "設定",
    "admin.liveStreams": "即時畫面",
    "admin.pendingSources": "待審核來源",
    "admin.noPending": "尚無待審核的建議。",
    "admin.editStreamsDesc": "可編輯名稱、地點、啟用、直播網址與直接嵌入。直接嵌入：關閉辨識以節省伺服器資源。刪除會一併移除歷史與通知訂閱。",
    "admin.noStreams": "尚無畫面，請從儀表板審核建議。",
    "admin.enabled": "啟用",
    "admin.directEmbed": "直接嵌入",
    "admin.directEmbedHint": "關閉辨識以節省伺服器資源",
    "admin.directEmbedNoYoutube": "YouTube 不適用，改由 proxy 直接播放",
    "admin.save": "儲存",
    "admin.cancel": "取消",
    "admin.edit": "編輯",
    "admin.delete": "刪除",
    "admin.name": "名稱",
    "admin.location": "地點（地名或 lat,lon）",
    "admin.streamUrl": "直播網址",
    "admin.deleteConfirm": "確定要刪除此畫面？其歷史與通知訂閱將一併移除。",
    "admin.disabled": "已停用",
    "admin.broadcast": "廣播",
    "admin.broadcastDesc": "發送訊息給所有已綁定 LINE 或 Telegram 且未停權的使用者。",
    "admin.approve": "核准",
    "admin.reject": "拒絕",
    "admin.deleteSuggestionConfirm": "確定要刪除此建議？",
    "common.loading": "載入中…",
    "card.loadingPreview": "載入中…",
    "aria.github": "GitHub 儲存庫",
  },
};

function detectLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored === "zh-TW" || stored === "en") return stored;
  const lang = navigator.language || (navigator as { userLanguage?: string }).userLanguage || "";
  if (/^zh(-(TW|HK|MO))?$/i.test(lang) || lang.startsWith("zh-")) return "zh-TW";
  return "en";
}

type I18nContextValue = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => (typeof window !== "undefined" ? detectLocale() : "en"));

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem(STORAGE_KEY, l);
  }, []);

  const t = useCallback(
    (key: string) => messages[locale][key] ?? messages.en[key] ?? key,
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
