// TypeScript mirrors of the backend's Pydantic response schemas.
// Update these together with backend/app/schemas.

export interface Sector {
  id: number;
  name: string;
  style: string;
  grade_min: string;
  grade_max: string;
  crag_id: number;
  approach_notes: string | null;
  approach_minutes: number | null; // one way; null = unknown
  crag: {
    id: number;
    name: string;
    region: string;
  };
}

// schemas/search.py
export interface ParsedFilters {
  understood: boolean;
  min_grade: string;
  max_grade: string;
  max_distance_km: number;
  style: string | null;
}

export interface NaturalSearchResponse {
  parsed_filters: ParsedFilters;
  results: Sector[];
}

export interface SimilarMatch {
  sector: Sector;
  similarity: number;
  reason: string | null;
}

export interface SimilarSearchResponse {
  results: SimilarMatch[];
}

// schemas/group.py
export type SearchMode = "scored" | "strict";
export type FitMode = "overlap" | "cover";

export interface MemberInput {
  name: string;
  grade_min: string | null;
  grade_max: string | null;
  max_distance_km: number | null;
  max_approach_minutes: number | null;
  styles: string[];
}

export interface Member extends MemberInput {
  id: number;
}

export interface Group {
  name: string;
  share_code: string;
  members: Member[];
}

export interface MemberMisfit {
  name: string;
  reason: string;
}

export interface GroupSectorMatch {
  sector: Sector;
  distance_km: number;
  fit_count: number;
  member_count: number;
  fits: string[];
  misfits: MemberMisfit[];
}

export interface MergedFilters {
  grade_min: string;
  grade_max: string;
  max_distance_km: number | null; // null = no limit
  max_approach_minutes: number | null; // null = no limit
  styles: string[] | null; // null = any style
}

export interface GroupSearchResponse {
  mode: SearchMode;
  fit: FitMode;
  member_count: number;
  common_ground: boolean;
  message: string | null;
  filters: MergedFilters | null;
  results: GroupSectorMatch[];
}

// schemas/stay.py
export interface StayRead {
  id: number;
  name: string;
  type: string;
  latitude: number;
  longitude: number;
  price_range: string | null;
  source: "curated" | "osm";
  url: string | null;
}

export interface NearbyStay {
  stay: StayRead;
  distance_km: number;
}

export interface BookingLinks {
  airbnb: string;
  booking: string;
}

export interface GroupStaysResponse {
  sector_id: number;
  sector_name: string;
  crag_name: string;
  guests: number;
  checkin: string; // "YYYY-MM-DD"
  checkout: string; // "YYYY-MM-DD"
  stays: NearbyStay[];
  links: BookingLinks;
}

// schemas/planner.py
export interface PlannerSector {
  sector_id: number;
  sector_name: string;
  crag_name: string;
  style: string;
  grade_min: string;
  grade_max: string;
  approach_minutes: number | null;
  distance_km: number;
}

export interface PlannerPlan {
  sector: PlannerSector;
  checkin: string; // "YYYY-MM-DD"
  checkout: string; // "YYYY-MM-DD"
  nights: number;
  guests: number;
  stays: NearbyStay[];
  links: BookingLinks;
}

export interface TraceStep {
  node: string;
  changed: string[];
}

export interface Rejection {
  sector_id: number;
  reason: string;
}

export type PlannerRunStatus = "waiting_for_approval" | "planned" | "no_plan";

export interface PlannerRun {
  run_id: string;
  share_code: string;
  status: PlannerRunStatus;
  checkin: string; // "YYYY-MM-DD"
  nights: number;
  guests: number | null;
  proposal: PlannerSector | null;
  plan: PlannerPlan | null;
  message: string | null;
  rejections: Rejection[];
  trace: TraceStep[];
  created_at: string;
}

export interface PlannerRunStart {
  checkin?: string; // left out = next Saturday
  nights: number;
  guests?: number; // left out = one per member
}

export interface PlannerAnswer {
  approved: boolean;
  reason?: string | null;
  sector_id?: number; // the proposal being answered
}
