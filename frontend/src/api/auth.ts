import { apiClient } from "./client";
import type { CurrentUser, SystemCapabilities, TokenResponse } from "@/types";

export const authApi = {
  async login(username: string, password: string): Promise<TokenResponse> {
    const { data } = await apiClient.post<TokenResponse>("/auth/login", { username, password });
    return data;
  },

  async me(): Promise<CurrentUser> {
    const { data } = await apiClient.get<CurrentUser>("/auth/me");
    return data;
  },

  async capabilities(): Promise<SystemCapabilities> {
    const { data } = await apiClient.get<SystemCapabilities>("/settings/capabilities");
    return data;
  },
};
