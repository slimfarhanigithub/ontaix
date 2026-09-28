/**
 * Role names as the portal shows them and as the API names them.
 */
import type { RoleName } from '../api/types';

/** The roles a group can be given, in the reference's order (`ROLE_NAMES`, line 1016). */
export const ROLE_NAMES = ['Owner', 'Builder', 'Governor', 'Member', 'Administrator', 'Auditor'];

export const roleLabel = (r: RoleName): string => r.charAt(0).toUpperCase() + r.slice(1);

export const roleName = (label: string): RoleName => label.toLowerCase() as RoleName;

/** Distinct role labels in first-seen order, the reference's effective roles column. */
export const distinctRoles = (roles: { role: RoleName }[]): string[] => [...new Set(roles.map((r) => roleLabel(r.role)))];
