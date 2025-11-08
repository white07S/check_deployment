const API_BASE = (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");

export function resolveHttp(path) {
  if (!API_BASE) {
    return path;
  }
  return `${API_BASE}${path}`;
}

export function resolveWs(path) {
  const origin = API_BASE || window.location.origin;
  const url = new URL(path, origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

async function handleJson(response) {
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      throw new Error(`Unexpected response from server (${response.status})`);
    }
  }

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || response.statusText;
    throw new Error(detail);
  }

  return payload;
}

const buildQueryString = (params = {}) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    query.set(key, String(value));
  });
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
};

export const chatApi = {
  async listSessions(userId) {
    const query = buildQueryString({ user_id: userId });
    const response = await fetch(resolveHttp(`/sessions${query}`));
    const payload = await handleJson(response);
    return payload.sessions || [];
  },

  async createSession({ userId, llmSessionId, title }) {
    const response = await fetch(resolveHttp(`/sessions`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        llm_session_id: llmSessionId,
        title,
      }),
    });
    return handleJson(response);
  },

  async listMessages({ userId, chatSessionId }) {
    const query = buildQueryString({ user_id: userId });
    const response = await fetch(resolveHttp(`/sessions/${chatSessionId}/messages${query}`));
    const payload = await handleJson(response);
    return payload.messages || [];
  },

  async listPrompts(filters = {}, userId) {
    const query = buildQueryString({
      user_id: userId,
      user_created: filters.user_created,
      keywords: filters.keywords,
    });
    const response = await fetch(resolveHttp(`/prompts/list${query}`));
    const payload = await handleJson(response);
    return payload.prompts || [];
  },

  async createPrompt(data, userId) {
    const query = buildQueryString({ user_id: userId });
    const response = await fetch(resolveHttp(`/prompts/create${query}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return handleJson(response);
  },

  async updatePrompt(promptId, data, userId) {
    const query = buildQueryString({ user_id: userId });
    const response = await fetch(resolveHttp(`/prompts/${promptId}${query}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return handleJson(response);
  },

  async deletePrompt(promptId, userId) {
    const query = buildQueryString({ user_id: userId });
    const response = await fetch(resolveHttp(`/prompts/${promptId}${query}`), {
      method: "DELETE",
    });
    return handleJson(response);
  },

  async copyPrompt(promptId, userId) {
    const query = buildQueryString({ user_id: userId });
    const response = await fetch(resolveHttp(`/prompts/copy${query}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt_id: promptId }),
    });
    return handleJson(response);
  },

  async getPromptSuggestions(limit = 5) {
    const clamped = Math.max(1, Math.min(limit, 50));
    const response = await fetch(resolveHttp(`/prompts/suggestions/${clamped}`));
    const payload = await handleJson(response);
    return payload.suggestions || [];
  },
};
