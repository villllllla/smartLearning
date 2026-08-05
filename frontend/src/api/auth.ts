import { api } from "./client";

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  role: string;
  tenant_id: number;
  tenant_name: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface MeResponse {
  user: AuthUser;
  auth_enabled: boolean;
}

export const authApi = {
  login: (body: { email: string; password: string }) =>
    api.post<LoginResponse>("/auth/login", body, { skipAuth: true }),
  register: (body: {
    tenant_name: string;
    email: string;
    password: string;
    display_name?: string;
  }) => api.post<LoginResponse>("/auth/register", body, { skipAuth: true }),
  me: () => api.get<MeResponse>("/auth/me"),
  changePassword: (body: { current_password: string; new_password: string }) =>
    api.post<void>("/auth/change-password", body),
};
