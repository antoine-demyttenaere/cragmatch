export interface Sector {
  id: number;
  name: string;
  style: string;
  grade_min: string;
  grade_max: string;
  crag_id: number;
  crag: {
    id: number;
    name: string;
    region: string;
  };
}
