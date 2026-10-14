import type { FitMode, Member, SearchMode } from "../../api/types";
import { styleLabel } from "../../constants";

export interface MemberLabels {
  grades: string;
  distance: string;
  walkIn: string;
  styles: string[]; // empty = any style
}

// An empty preference means "any", so say that instead of showing a blank.
export function describeMember(member: Member): MemberLabels {
  const hasGrades = member.grade_min !== null && member.grade_max !== null;
  return {
    grades: hasGrades ? `${member.grade_min} to ${member.grade_max}` : "Any grade",
    distance: member.max_distance_km !== null ? `Up to ${member.max_distance_km} km` : "Any distance",
    walkIn: member.max_approach_minutes !== null ? `Up to ${member.max_approach_minutes} min walk-in` : "Any walk-in",
    styles: member.styles.map(styleLabel),
  };
}

export const MODE_HELP: Record<SearchMode, string> = {
  scored: "Every sector, best fit first, with who it doesn't suit and why.",
  strict: "Only sectors that suit everyone.",
};

export const FIT_HELP: Record<FitMode, string> = {
  overlap: "A sector fits someone when some of its routes are in their grade range.",
  cover: "A sector fits someone only when its grades cover their whole range.",
};
