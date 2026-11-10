/**
 * The shape a French or German dictionary takes from its English source: the same keys, each
 * with a string, so a missing or an extra key fails the type check.
 */
export type Translation<T> = { readonly [K in keyof T]: string };
