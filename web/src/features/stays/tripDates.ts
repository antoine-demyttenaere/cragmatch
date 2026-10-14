// "2026-10-17" -> "Sat 17 Oct". Built from the parts so the browser's time
// zone can't shift the day.
export function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day)
    .toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })
    .replace(",", "");
}
