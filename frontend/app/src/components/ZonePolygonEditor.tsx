import { useRef, useState, type MouseEvent } from "react"
import { Button } from "@/components/ui/button"
import { getToken } from "@/lib/api"

export default function ZonePolygonEditor({
  cameraId,
  initialPolygon,
  onChange,
}: {
  cameraId: string | null
  initialPolygon: [number, number][]
  onChange: (polygon: [number, number][]) => void
}) {
  const [points, setPoints] = useState<[number, number][]>(initialPolygon)
  const imgRef = useRef<HTMLImageElement>(null)
  const token = getToken()

  function handleClick(e: MouseEvent<HTMLDivElement>) {
    const el = imgRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height))
    const next: [number, number][] = [...points, [Number(x.toFixed(4)), Number(y.toFixed(4))]]
    setPoints(next)
    onChange(next)
  }

  function undo() {
    const next = points.slice(0, -1)
    setPoints(next)
    onChange(next)
  }

  function clear() {
    setPoints([])
    onChange([])
  }

  if (!cameraId) {
    return <p className="text-sm text-muted-foreground">Select a camera to draw a zone on its live view.</p>
  }

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0] * 100} ${p[1] * 100}`).join(" ")

  return (
    <div className="flex flex-col gap-2">
      <div className="relative w-full cursor-crosshair select-none overflow-hidden rounded-md border border-border bg-black" onClick={handleClick}>
        <img
          ref={imgRef}
          src={`/api/stream/${cameraId}/snapshot?token=${encodeURIComponent(token ?? "")}&t=${Date.now()}`}
          alt="camera snapshot"
          className="block w-full"
          draggable={false}
        />
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
          {points.length > 0 && (
            <path d={`${pathD} ${points.length > 2 ? "Z" : ""}`} className="fill-primary/20 stroke-primary" strokeWidth="0.4" vectorEffect="non-scaling-stroke" />
          )}
          {points.map((p, i) => (
            <circle key={i} cx={p[0] * 100} cy={p[1] * 100} r="0.8" className="fill-primary" />
          ))}
        </svg>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" variant="outline" onClick={undo} disabled={points.length === 0}>Undo point</Button>
        <Button type="button" size="sm" variant="outline" onClick={clear} disabled={points.length === 0}>Clear</Button>
        <span className="text-xs text-muted-foreground">{points.length} point(s) · click the image to add a vertex, needs 3+</span>
      </div>
    </div>
  )
}
