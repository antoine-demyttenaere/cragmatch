import type { Sector } from "./types";


interface SectorCardProps {
  sector: Sector;
}

function SectorCard({ sector }: SectorCardProps) {
  return (   
    <li>
      {sector.name} ({sector.crag.name}) - {sector.crag.region} — {sector.style} — {sector.grade_min} to {sector.grade_max}
    </li>
  );
}

export default SectorCard;
