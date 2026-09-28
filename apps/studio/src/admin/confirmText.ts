/**
 * The typed confirmation that guards disabling "Companies may interact" when companies already
 * interact: the action stays disabled until the text reads `disable`, ignoring case and
 * surrounding spaces.
 */

export const DISABLE_WORD = 'disable';

export const isDisableConfirmed = (typed: string): boolean => typed.trim().toLowerCase() === DISABLE_WORD;
