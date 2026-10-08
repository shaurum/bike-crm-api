import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/lib/store";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export { API_URL };

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

const AUTH_FREE_PATHS = ["/auth/login", "/auth/register", "/auth/refresh"];

function isAuthFree(url?: string) {
  if (!url) return false;
  return AUTH_FREE_PATHS.some((p) => url.includes(p));
}

let refreshing: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const { refreshToken, user, setAuth } = useAuthStore.getState();
  if (!refreshToken) throw new Error("Нет refresh токена");

  const { data } = await axios.post(
    `${API_URL}/api/v1/auth/refresh`,
    null,
    { headers: { Authorization: `Bearer ${refreshToken}` } }
  );

  if (user) setAuth(user, data.access_token, data.refresh_token);
  else useAuthStore.getState().setTokens(data.access_token, data.refresh_token);

  return data.access_token as string;
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token && !isAuthFree(config.url)) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;
    const status = error.response?.status;

    if (status !== 401 || !originalRequest || originalRequest._retry) {
      return Promise.reject(error);
    }
    if (isAuthFree(originalRequest.url)) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      refreshing = refreshing ?? refreshAccessToken();
      const token = await refreshing;
      originalRequest.headers.Authorization = `Bearer ${token}`;
      return api(originalRequest);
    } catch {
      useAuthStore.getState().logout();
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.replace("/login");
      }
      return Promise.reject(error);
    } finally {
      refreshing = null;
    }
  }
);

export const authApi = {
  login: (email: string, password: string) =>
    api.post("/auth/login", new URLSearchParams({ username: email, password }), {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  register: (data: {
    email: string;
    password: string;
    full_name: string;
    phone?: string;
    invite_token?: string;
  }) => api.post("/auth/register", data),
  registerStatus: () => api.get<{ open: boolean }>("/auth/register-status"),
  refresh: (refreshToken: string) =>
    api.post("/auth/refresh", null, { headers: { Authorization: `Bearer ${refreshToken}` } }),
  me: () => api.get("/auth/me"),
};

export const usersApi = {
  list: () => api.get("/users/list"),
};

/** Управление пользователями — только для роли admin (проверяет бэкенд). */
export const adminUsersApi = {
  list: () => api.get("/users"),
  create: (data: {
    email: string;
    password: string;
    full_name: string;
    phone?: string;
    role: string;
  }) => api.post("/users", data),
  update: (id: string, data: Partial<{ full_name: string; phone: string | null; role: string; is_active: boolean }>) =>
    api.patch(`/users/${id}`, data),
  resetPassword: (id: string, newPassword: string) =>
    api.post(`/users/${id}/password`, { new_password: newPassword }),
};

/** Пригласительные ссылки — админ создаёт, новичок регистрируется по токену. */
export interface InviteRecord {
  id: string;
  token: string;
  role: string;
  email: string | null;
  expires_at: string;
  used_at: string | null;
  created_at: string;
  status: "active" | "used" | "expired";
}

export const invitesApi = {
  list: () => api.get<InviteRecord[]>("/invites"),
  create: (data: { role: string; email?: string; days: number }) =>
    api.post<InviteRecord>("/invites", data),
  remove: (id: string) => api.delete(`/invites/${id}`),
  validate: (token: string) =>
    api.get<{ ok: boolean; role: string | null; email: string | null; detail: string | null }>(
      `/invites/validate/${token}`
    ),
};

/** Версия CRM и автообновление на сервере. */
export interface SystemVersion {
  current_sha: string | null;
  current_date: string | null;
  remote_sha: string | null;
  update_available: boolean;
  updating: boolean;
  last_check: string | null;
  auto_update: boolean;
  note: string | null;
}

export const systemApi = {
  version: () => api.get<SystemVersion>("/system/version"),
  checkUpdate: () => api.post<{ ok: boolean; detail: string }>("/system/update-check"),
};

export const documentsApi = {
  list: (params?: {
    page?: number;
    size?: number;
    kind?: string;
    status?: string;
    lead_id?: string;
    customer_id?: string;
  }) => api.get("/documents", { params }),
  company: () => api.get("/documents/company"),
  updateCompany: (data: any) => api.patch("/documents/company", data),
  generate: (lead_id: string, allow_incomplete = false) =>
    api.post("/documents/generate", { lead_id, allow_incomplete }),
  uploadScan: (file: File, opts?: { customer_id?: string | null; number?: string | null }) => {
    const form = new FormData();
    form.append("file", file);
    if (opts?.customer_id) form.append("customer_id", opts.customer_id);
    if (opts?.number) form.append("number", opts.number);
    return api.post("/documents", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  attachSigned: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/documents/${id}/signed`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  detachSigned: (id: string) => api.delete(`/documents/${id}/signed`),
  changeStatus: (id: string, status: string) =>
    api.patch(`/documents/${id}/status?doc_status=${status}`),
  remove: (id: string) => api.delete(`/documents/${id}`),
};

export const leadsApi = {
  list: (params?: {
    page?: number;
    size?: number;
    status?: string;
    stage_id?: string;
    source_id?: string;
    search?: string;
  }) => api.get("/leads", { params }),
  get: (id: string) => api.get(`/leads/${id}`),
  create: (data: {
    source_id: string;
    customer_id?: string | null;
    client_name?: string;
    client_phone?: string;
    client_email?: string;
    bike_id?: string | null;
    initial_message?: string;
  }) => api.post("/leads", data),
  assign: (id: string, user_id: string) => api.patch(`/leads/${id}/assign`, null, { params: { user_id } }),
  changeStage: (id: string, stage_id: string) => api.patch(`/leads/${id}/stage`, null, { params: { stage_id } }),
  updateDeal: (
    id: string,
    data: {
      customer_id?: string | null;
      bike_id?: string | null;
      amount?: number | null;
      deal_due_at?: string | null;
      rental_start_at?: string | null;
      rental_end_at?: string | null;
    }
  ) => api.patch(`/leads/${id}/deal`, data),
  comments: (id: string) => api.get(`/leads/${id}/comments`),
  addComment: (id: string, text: string) => api.post(`/leads/${id}/comments`, { text }),
  remove: (id: string) => api.delete(`/leads/${id}`),
  sources: () => api.get("/leads/sources/list"),
  stages: () => api.get("/leads/stages/list"),
};

export const bikesApi = {
  list: (params?: {
    page?: number;
    size?: number;
    status?: string;
    branch_id?: string;
    search?: string;
  }) => api.get("/bikes", { params }),
  get: (id: string) => api.get(`/bikes/${id}`),
  create: (data: any) => api.post("/bikes", data),
  update: (id: string, data: any) => api.patch(`/bikes/${id}`, data),
  remove: (id: string) => api.delete(`/bikes/${id}`),
  uploadPhoto: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/bikes/${id}/photo`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  checkAvailability: (id: string, start_at: string, end_at: string) =>
    api.get(`/bikes/${id}/availability`, { params: { start_at, end_at } }),
  branches: () => api.get("/bikes/branches/list"),
};

export const bookingsApi = {
  list: (params?: {
    page?: number;
    size?: number;
    status?: string;
    branch_id?: string;
    bike_id?: string;
    customer_id?: string;
    date_from?: string;
    date_to?: string;
  }) => api.get("/bookings", { params }),
  get: (id: string) => api.get(`/bookings/${id}`),
  confirm: (id: string) => api.post(`/bookings/${id}/confirm`),
  start: (id: string) => api.post(`/bookings/${id}/start`),
  complete: (id: string) => api.post(`/bookings/${id}/complete`),
};

export const customersApi = {
  list: (params?: {
    page?: number;
    size?: number;
    search?: string;
    is_blacklisted?: boolean;
  }) => api.get("/customers", { params }),
  get: (id: string) => api.get(`/customers/${id}`),
  create: (data: any) => api.post("/customers", data),
  update: (id: string, data: any) => api.patch(`/customers/${id}`, data),
  remove: (id: string) => api.delete(`/customers/${id}`),
  uploadDocument: (id: string, file: File, kind: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return api.post(`/customers/${id}/documents`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  removeDocument: (id: string, documentId: string) =>
    api.delete(`/customers/${id}/documents/${documentId}`),
};

export const tasksApi = {
  list: (params?: {
    page?: number;
    size?: number;
    status?: string;
    type?: string;
    assignee_id?: string;
    related_bike_id?: string;
    related_booking_id?: string;
  }) => api.get("/tasks", { params }),
  get: (id: string) => api.get(`/tasks/${id}`),
  updateStatus: (id: string, status: string) => api.patch(`/tasks/${id}/status`, null, { params: { status } }),
  create: (data: any) => api.post("/tasks", data),
};

export const webhooksApi = {
  avito: (data: any) => api.post("/webhooks/avito", data),
  vk: (data: any) => api.post("/webhooks/vk", data),
  telegram: (data: any) => api.post("/webhooks/telegram", data),
  email: (data: any) => api.post("/webhooks/email", data),
};

export const publicApi = {
  bikes: (params?: { branch_id?: string; available_only?: boolean }) => api.get("/public/bikes", { params }),
  bike: (id: string) => api.get(`/public/bikes/${id}`),
  availability: (params: { start_at: string; end_at: string; branch_id?: string }) =>
    api.get("/public/availability", { params }),
  createBooking: (data: any) => api.post("/public/bookings", data),
  widgetConfig: (domain: string) => api.get("/public/widget/config", { params: { domain } }),
};

export const dashboardApi = {
  stats: (days?: number) => api.get("/dashboard/stats", { params: { days } }),
  funnel: (days?: number) => api.get("/dashboard/funnel", { params: { days } }),
  bikesUtilization: (days?: number) => api.get("/dashboard/bikes-utilization", { params: { days } }),
  leadsBySource: (days?: number) => api.get("/dashboard/leads-by-source", { params: { days } }),
};
