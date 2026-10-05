import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/lib/store";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const { refreshToken, user, setAuth, logout } = useAuthStore.getState();

      if (refreshToken) {
        try {
          const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, null, {
            headers: { Authorization: `Bearer ${refreshToken}` },
          });
          const { access_token, refresh_token } = response.data;
          if (user) {
            setAuth(user, access_token, refresh_token);
          } else {
            useAuthStore.getState().setTokens(access_token, refresh_token);
          }
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return api(originalRequest);
        } catch {
          logout();
          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
        }
      } else {
        logout();
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
      }
    }

    return Promise.reject(error);
  }
);

export const authApi = {
  login: (email: string, password: string) =>
    api.post("/auth/login", new URLSearchParams({ username: email, password }), {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  register: (data: { email: string; password: string; full_name: string; phone?: string }) =>
    api.post("/auth/register", data),
  refresh: (refreshToken: string) =>
    api.post("/auth/refresh", null, { headers: { Authorization: `Bearer ${refreshToken}` } }),
  me: () => api.get("/auth/me"),
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
  assign: (id: string, user_id: string) => api.patch(`/leads/${id}/assign`, null, { params: { user_id } }),
  changeStage: (id: string, stage_id: string) => api.patch(`/leads/${id}/stage`, null, { params: { stage_id } }),
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
  list: (params?: { page?: number; size?: number; search?: string }) => api.get("/customers", { params }),
  get: (id: string) => api.get(`/customers/${id}`),
  create: (data: any) => api.post("/customers", data),
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
