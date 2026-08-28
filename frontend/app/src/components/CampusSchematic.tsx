import { useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { Camera } from "@/lib/types"

// Simulated campus topology: fixed layout coordinates (percent of viewBox) for
// known demo camera names, with a fallback ring layout for any others so the
// schematic degrades gracefully instead of hardcoding assumptions.
const KNOWN_POSITIONS: Record<string, { x: number; y: number }> = {
  "Main Gate": { x: 50, y: 88 },
  "Library Court": { x: 24, y: 40 },
  "Rear Loading Dock": { x: 78, y: 30 },
}

const STATUS_COLOR: Record<Camera["status"], string> = {
  online: "fill-success stroke-success",
  starting: "fill-muted-foreground stroke-muted-foreground",
  offline: "fill-destructive stroke-destructive",
  frozen: "fill-warning stroke-warning",
  blackout: "fill-destructive stroke-destructive",
  blurred: "fill-warning stroke-warning",
  retired: "fill-muted-foreground stroke-muted-foreground",
}

function fallbackPosition(index: number, total: number) {
  const angle = (index / Math.max(total, 1)) * Math.PI * 1.4 + Math.PI * 0.15
  return { x: 50 + Math.cos(angle) * 32, y: 55 + Math.sin(angle) * 32 }
}

export default function CampusSchematic({ cameras, onSelect }: { cameras: Camera[]; onSelect?: (cameraId: string) => void }) {
  const [hovered, setHovered] = useState<string | null>(null)

  const positioned = useMemo(
    () =>
      cameras.map((cam, i) => ({
        camera: cam,
        pos: KNOWN_POSITIONS[cam.name] ?? fallbackPosition(i, cameras.length),
      })),
    [cameras]
  )

  return (
    <Card>
      <CardHeader className="py-2.5">
        <CardTitle>Campus Schematic</CardTitle>
      </CardHeader>
      <CardContent>
        <svg viewBox="0 0 100 100" className="w-full rounded-md border border-border bg-muted/20">
          <rect x="8" y="55" width="26" height="30" rx="1.5" className="fill-accent/60 stroke-border" strokeWidth="0.5" />
          <text x="21" y="72" textAnchor="middle" className="fill-muted-foreground text-[3px]">Library</text>

          <rect x="62" y="15" width="30" height="24" rx="1.5" className="fill-accent/60 stroke-border" strokeWidth="0.5" />
          <text x="77" y="29" textAnchor="middle" className="fill-muted-foreground text-[3px]">Loading Dock</text>

          <rect x="36" y="76" width="28" height="16" rx="1.5" className="fill-accent/40 stroke-border" strokeWidth="0.5" />
          <text x="50" y="86" textAnchor="middle" className="fill-muted-foreground text-[3px]">Main Gate</text>

          <path d="M 50 76 L 50 55 L 21 55" className="stroke-border" strokeWidth="0.6" fill="none" strokeDasharray="1.5,1.2" />
          <path d="M 50 55 L 77 55 L 77 39" className="stroke-border" strokeWidth="0.6" fill="none" strokeDasharray="1.5,1.2" />

          {positioned.map(({ camera, pos }) => (
            <g
              key={camera.id}
              transform={`translate(${pos.x} ${pos.y})`}
              className="cursor-pointer"
              onMouseEnter={() => setHovered(camera.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSelect?.(camera.id)}
            >
              {camera.status !== "online" && (
                <circle r="4" className={cn(STATUS_COLOR[camera.status], "fill-opacity-20 animate-pulse-ring")} strokeWidth="0.4" />
              )}
              <circle r="2.4" className={cn(STATUS_COLOR[camera.status], "fill-opacity-90")} strokeWidth="0.5" />
              {hovered === camera.id && (
                <text y="-4.5" textAnchor="middle" className="fill-foreground text-[3.2px] font-medium">
                  {camera.name}
                </text>
              )}
            </g>
          ))}
        </svg>
        <p className="mt-2 text-[10px] text-muted-foreground">Simulated campus topology for demo purposes. Pin color reflects live camera health.</p>
      </CardContent>
    </Card>
  )
}
