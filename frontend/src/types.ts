export interface Sector {
  id: number;
  name: string;
  style: string;
  grade_min: string;
  grade_max: string;
  crag_id: number;
  approach_notes: string | null;
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
