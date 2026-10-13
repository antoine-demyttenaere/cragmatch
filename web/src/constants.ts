// Same order as the backend's GRADE_ORDER (app/services/grades.py):
// 1-5 are a number with an optional "+"; 6-9 have a letter a/b/c and an optional "+".
export const GRADES: string[] = [];
for (let n = 1; n <= 5; n++) {
  GRADES.push(`${n}`, `${n}+`);
}
for (let n = 6; n <= 9; n++) {
  for (const letter of ["a", "b", "c"]) {
    GRADES.push(`${n}${letter}`, `${n}${letter}+`);
  }
}

export const STYLES = ["sport", "boulder", "trad", "multi-pitch"] as const;
export type ClimbingStyle = (typeof STYLES)[number];

export const STAY_TYPES = ["campsite", "hostel", "refuge", "guesthouse", "apartment"] as const;
export type StayType = (typeof STAY_TYPES)[number];

export const BARCELONA = { lat: 41.3874, lon: 2.1686 };

// "multi-pitch" -> "Multi-pitch". Unknown values fall back to a capitalised string.
export const STYLE_LABELS: Record<string, string> = {
  sport: "Sport",
  boulder: "Boulder",
  trad: "Trad",
  "multi-pitch": "Multi-pitch",
};

export const STAY_TYPE_LABELS: Record<string, string> = {
  campsite: "Campsite",
  hostel: "Hostel",
  refuge: "Refuge",
  guesthouse: "Guesthouse",
  apartment: "Apartment",
};

export function styleLabel(style: string): string {
  return STYLE_LABELS[style] ?? style;
}

export function stayTypeLabel(type: string): string {
  return STAY_TYPE_LABELS[type] ?? type;
}
