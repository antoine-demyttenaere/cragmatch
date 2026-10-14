// "40 min walk-in", shared by the search cards and the planner's sector card.
export function walkInLabel(minutes: number | null): string {
  return minutes !== null ? `${minutes} min walk-in` : "Walk-in unknown";
}

// Straight-line distance from Barcelona, rounded to whole km.
export function distanceLabel(km: number): string {
  return `${Math.round(km)} km from Barcelona`;
}
