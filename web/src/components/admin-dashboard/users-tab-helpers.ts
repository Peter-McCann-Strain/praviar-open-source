export const USERS_PER_PAGE = 20;

export function formatRoleLabel(role: string) {
  return role.charAt(0).toUpperCase() + role.slice(1);
}
