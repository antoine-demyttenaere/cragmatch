import type { Sector } from "./types";


interface SectorCardProps {
  sector: Sector;
  // Only set for results of the "describe the vibe" (similarity) search.
  similarity?: number;
  reason?: string | null;
  // When set, shows a "Stays nearby" button.
  onShowStays?: (sector: Sector) => void;
}

function SectorCard({ sector, similarity, reason, onShowStays }: SectorCardProps) {
  return (
    <li>
      {sector.name} ({sector.crag.name}) - {sector.crag.region} — {sector.style} — {sector.grade_min} to {sector.grade_max}
      {similarity !== undefined && <> — match {Math.round(similarity * 100)}%</>}
      {onShowStays && (
        <button type="button" onClick={() => onShowStays(sector)} style={{ marginLeft: 8 }}>
          Stays nearby
        </button>
      )}
      {reason && <div style={{ fontStyle: "italic" }}>{reason}</div>}
    </li>
  );
}

export default SectorCard;
