import { apiClient } from "./client";
import type { AuditLogEntry, RuntimeConfig, RuntimeConfigUpdate } from "@/types";

export const settingsApi = {
  async get(): Promise<RuntimeConfig> {
    const { data } = await apiClient.get<RuntimeConfig>("/settings");
    return data;
  },

  async update(payload: RuntimeConfigUpdate): Promise<RuntimeConfig> {
    const { data } = await apiClient.put<RuntimeConfig>("/settings", payload);
    return data;
  },

  async reset(): Promise<RuntimeConfig> {
    const { data } = await apiClient.post<RuntimeConfig>("/settings/reset");
    return data;
  },

  async auditLog(limit = 200): Promise<AuditLogEntry[]> {
    const { data } = await apiClient.get<AuditLogEntry[]>("/auth/audit-log", { params: { limit } });
    return data;
  },
};
