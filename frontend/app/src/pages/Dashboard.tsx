import { useCallback, useRef } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLiveFeed, type LiveEvent } from "@/lib/ws"
import type { Camera, Incident } from "@/lib/types"
import CameraTile from "@/components/CameraTile"
import IncidentCard from "@/components/IncidentCard"
import CampusSchematic from "@/components/CampusSchematic"
import { ScrollArea } from "@/components/ui/scroll-area"

export default function Dashboard() {
  const queryClient = useQueryClient()
  const tileRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.get<Camera[]>("/config/cameras"),
    refetchInterval: 8000,
  })
  const incidentsQuery = useQuery({
    queryKey: ["incidents", "open"],
    queryFn: () => api.get<Incident[]>("/incidents?limit=50"),
    refetchInterval: 8000,
  })

  const handleEvent = useCallback(
    (event: LiveEvent) => {
      if (event.type === "camera_status") {
        queryClient.invalidateQueries({ queryKey: ["cameras"] })
      }
      if (event.type === "incident") {
        queryClient.invalidateQueries({ queryKey: ["incidents"] })
      }
    },
    [queryClient]
  )
  useLiveFeed(handleEvent)

  const cameras = camerasQuery.data ?? []
  const incidents = (incidentsQuery.data ?? []).filter((i) => i.status !== "resolved")

  return (
    <div className="grid gap-4 p-4 lg:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map((cam) => (
            <div key={cam.id} ref={(el) => { tileRefs.current[cam.id] = el }}>
              <CameraTile camera={cam} />
            </div>
          ))}
          {cameras.length === 0 && (
            <p className="col-span-full text-sm text-muted-foreground">No cameras configured yet. Add one from Configuration.</p>
          )}
        </div>
        <CampusSchematic
          cameras={cameras}
          onSelect={(id) => tileRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "center" })}
        />
      </div>
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Open Incidents ({incidents.length})</h2>
        <ScrollArea className="h-[calc(100vh-7.5rem)] pr-2">
          <div className="flex flex-col gap-2">
            {incidents.map((incident) => (
              <IncidentCard key={incident.id} incident={incident} />
            ))}
            {incidents.length === 0 && <p className="text-sm text-muted-foreground">No open incidents.</p>}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
