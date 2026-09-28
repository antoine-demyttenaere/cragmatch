import type { Sector } from "./types";


interface SectorCardProps {
  sector: Sector;
  // Only set for results of the "describe the vibe" (similarity) search.
  similarity?: number;
  reason?: string | null;
}

function SectorCard({ sector, similarity, reason }: SectorCardProps) {
  return (
    <li>
      {sector.name} ({sector.crag.name}) - {sector.crag.region} — {sector.style} — {sector.grade_min} to {sector.grade_max}
      {similarity !== undefined && <> — match {Math.round(similarity * 100)}%</>}
      {reason && <div style={{ fontStyle: "italic" }}>{reason}</div>}
    </li>
  );
}

export default SectorCard;
