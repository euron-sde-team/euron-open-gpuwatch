import type { Role } from "./api/types";

export const ROLES: readonly Role[] = ["owner", "admin", "viewer"] as const;

const ROLE_LABEL: Record<Role, string> = { owner: "Owner", admin: "Admin", viewer: "Viewer" };

const ROLE_DESCRIPTION: Record<Role, string> = {
  owner: "Full control, including users and roles.",
  admin: "Manages hosts, rates, workload rules, alerts, channels and API keys.",
  viewer: "Read only: sees GPUs, history, costs, insights and alerts.",
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

export function roleLabel(role: string | null | undefined): string {
  return isRole(role) ? ROLE_LABEL[role] : "Unknown";
}

export function roleDescription(role: string | null | undefined): string {
  return isRole(role) ? ROLE_DESCRIPTION[role] : "";
}

/** Owners and admins change configuration; viewers only read. */
export function canWrite(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}

/** Only owners invite people, change roles or disable accounts. */
export function canManageUsers(role: string | null | undefined): boolean {
  return role === "owner";
}
