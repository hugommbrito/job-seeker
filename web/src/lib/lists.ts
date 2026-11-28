/** "Toronto, Ottawa ,," -> ["Toronto", "Ottawa"]: how the forms take short lists. */
export function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function toggle<T>(list: readonly T[], item: T, on: boolean): T[] {
  return on ? [...list.filter((existing) => existing !== item), item] : list.filter((x) => x !== item);
}
