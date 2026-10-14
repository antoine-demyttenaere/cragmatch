// The one place that knows the share-link format, so old and new links match:
// http://localhost:5173/?group=ABCD2345

export function groupCodeFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get("group");
}

// Keeps the address bar a shareable link. replaceState (not pushState) so
// opening or leaving a group doesn't add history entries.
export function syncGroupCodeToUrl(code: string | null): void {
  const url = new URL(window.location.href);
  if (code) {
    url.searchParams.set("group", code);
  } else {
    url.searchParams.delete("group");
  }
  window.history.replaceState(null, "", url);
}

export function shareLinkFor(code: string): string {
  return `${window.location.origin}${window.location.pathname}?group=${encodeURIComponent(code)}`;
}
