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
