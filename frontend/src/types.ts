// TypeScript mirrors of the backend's Pydantic response schemas.

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

export interface ParsedFilters {
  understood: boolean;
  min_grade: string;
  max_grade: string;
  max_distance_km: number;
  style: string | null;
}

// One result of POST /search/similar (mirrors SimilarMatch in schemas/search.py).
export interface SimilarMatch {
  sector: Sector;
  similarity: number;
  reason: string | null;
}


// --- Groups (schemas/group.py) --------------------------------------------

// What you send to add or replace a member.
export interface MemberInput {
  name: string;
  grade_min: string | null;
  grade_max: string | null;
  max_distance_km: number | null;
  max_approach_minutes: number | null;
  styles: string[]; // empty = any style
}

export interface Member extends MemberInput {
  id: number;
}

export interface Group {
  name: string;
  share_code: string;
  members: Member[];
}

export interface GroupSectorMatch {
  sector: Sector;
  distance_km: number;
  fit_count: number;
  member_count: number;
  fits: string[];
  misfits: { name: string; reason: string }[];
}

export interface GroupSearchResponse {
  mode: "strict" | "scored";
  fit: "overlap" | "cover";
  member_count: number;
  common_ground: boolean;
  message: string | null;
  filters: {
    grade_min: string;
    grade_max: string;
    max_distance_km: number | null;
    max_approach_minutes: number | null;
    styles: string[] | null;
  } | null;
  results: GroupSectorMatch[];
}


// --- Stays (schemas/stay.py) ----------------------------------------------

export interface Stay {
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
  stay: Stay;
  distance_km: number;
}

export interface GroupStaysResponse {
  sector_id: number;
  sector_name: string;
  crag_name: string;
  guests: number;
  checkin: string;  // "YYYY-MM-DD"
  checkout: string;
  stays: NearbyStay[];
  links: { airbnb: string; booking: string };
}
