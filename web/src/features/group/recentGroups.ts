// The last few groups opened in this browser. Only the code and the group
// name are kept, no member data.

export interface RecentGroup {
  code: string;
  name: string;
}

const KEY = "cragmatch.recentGroups";
const MAX_RECENT = 5;

function isRecentGroup(value: unknown): value is RecentGroup {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.code === "string" && typeof entry.name === "string";
}

// Storage can be disabled, full, or edited by hand: that must never break the page.
export function readRecentGroups(): RecentGroup[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isRecentGroup).slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

function writeRecentGroups(groups: RecentGroup[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(groups));
  } catch {
    // Not saving a convenience list is fine.
  }
}

export function rememberGroup(group: RecentGroup): void {
  const others = readRecentGroups().filter((g) => g.code !== group.code);
  writeRecentGroups([group, ...others].slice(0, MAX_RECENT));
}

export function forgetGroup(code: string): void {
  writeRecentGroups(readRecentGroups().filter((g) => g.code !== code));
}
