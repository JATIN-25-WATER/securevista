import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Plus, Trash2 } from "lucide-react"
import { api } from "@/lib/api"
import type { Camera, SOP, Schedule, Zone } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import ZonePolygonEditor from "@/components/ZonePolygonEditor"

const DAYS: { key: string; label: string }[] = [
  { key: "mon", label: "Mon" }, { key: "tue", label: "Tue" }, { key: "wed", label: "Wed" },
  { key: "thu", label: "Thu" }, { key: "fri", label: "Fri" }, { key: "sat", label: "Sat" }, { key: "sun", label: "Sun" },
]

export default function Configuration() {
  return (
    <div className="mx-auto max-w-5xl p-4">
      <Tabs defaultValue="cameras">
        <TabsList>
          <TabsTrigger value="cameras">Cameras</TabsTrigger>
          <TabsTrigger value="zones">Zones</TabsTrigger>
          <TabsTrigger value="schedules">Schedules</TabsTrigger>
          <TabsTrigger value="sops">SOPs</TabsTrigger>
        </TabsList>
        <TabsContent value="cameras"><CamerasTab /></TabsContent>
        <TabsContent value="zones"><ZonesTab /></TabsContent>
        <TabsContent value="schedules"><SchedulesTab /></TabsContent>
        <TabsContent value="sops"><SopsTab /></TabsContent>
      </Tabs>
    </div>
  )
}

function CamerasTab() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: "", source_type: "mp4", uri: "", loop: true })

  const camerasQuery = useQuery({ queryKey: ["cameras"], queryFn: () => api.get<Camera[]>("/config/cameras") })
  const createMutation = useMutation({
    mutationFn: () => api.post<Camera>("/config/cameras", form),
    onSuccess: () => {
      toast.success("Camera added")
      setOpen(false)
      setForm({ name: "", source_type: "mp4", uri: "", loop: true })
      queryClient.invalidateQueries({ queryKey: ["cameras"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.del(`/config/cameras/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Cameras</CardTitle>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="h-4 w-4" /> Add Camera</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Add Camera</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Source type</Label>
                <Select value={form.source_type} onValueChange={(v) => setForm({ ...form, source_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="mp4">Staged MP4 (loops like a live feed)</SelectItem>
                    <SelectItem value="webcam">Webcam</SelectItem>
                    <SelectItem value="rtsp">RTSP stream</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{form.source_type === "webcam" ? "Device index (e.g. 0)" : form.source_type === "rtsp" ? "RTSP URL" : "File path"}</Label>
                <Input value={form.uri} onChange={(e) => setForm({ ...form, uri: e.target.value })} placeholder={form.source_type === "rtsp" ? "rtsp://…" : form.source_type === "webcam" ? "0" : "C:\\path\\to\\video.mp4"} />
              </div>
              {form.source_type === "mp4" && (
                <div className="flex items-center justify-between">
                  <Label>Loop (behave like a live feed)</Label>
                  <Switch checked={form.loop} onCheckedChange={(v) => setForm({ ...form, loop: v })} />
                </div>
              )}
              <Button disabled={!form.name || !form.uri || createMutation.isPending} onClick={() => createMutation.mutate()}>Save</Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {(camerasQuery.data ?? []).map((cam) => (
          <div key={cam.id} className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
            <div className="flex flex-col">
              <span className="font-medium">{cam.name}</span>
              <span className="text-xs text-muted-foreground">{cam.source_type} · {cam.uri}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="capitalize">{cam.status}</Badge>
              <Button size="icon" variant="ghost" onClick={() => deleteMutation.mutate(cam.id)}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function ZonesTab() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ camera_id: "", name: "", restricted: false, loitering_threshold_s: 30, after_hours_monitored: true, polygon: [] as [number, number][] })

  const camerasQuery = useQuery({ queryKey: ["cameras"], queryFn: () => api.get<Camera[]>("/config/cameras") })
  const zonesQuery = useQuery({ queryKey: ["zones"], queryFn: () => api.get<Zone[]>("/config/zones") })
  const cameraById = (id: string) => camerasQuery.data?.find((c) => c.id === id)

  const createMutation = useMutation({
    mutationFn: () => api.post<Zone>("/config/zones", form),
    onSuccess: () => {
      toast.success("Zone added")
      setOpen(false)
      setForm({ camera_id: "", name: "", restricted: false, loitering_threshold_s: 30, after_hours_monitored: true, polygon: [] })
      queryClient.invalidateQueries({ queryKey: ["zones"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.del(`/config/zones/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zones"] }),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Zones</CardTitle>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="h-4 w-4" /> Add Zone</Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Add Zone</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Camera</Label>
                <Select value={form.camera_id} onValueChange={(v) => setForm({ ...form, camera_id: v, polygon: [] })}>
                  <SelectTrigger><SelectValue placeholder="Select a camera" /></SelectTrigger>
                  <SelectContent>
                    {(camerasQuery.data ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <ZonePolygonEditor key={form.camera_id} cameraId={form.camera_id || null} initialPolygon={form.polygon} onChange={(p) => setForm({ ...form, polygon: p })} />
              <div className="flex flex-col gap-1.5">
                <Label>Zone name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="flex items-center justify-between">
                <Label>Restricted (unauthorized entry raises an incident)</Label>
                <Switch checked={form.restricted} onCheckedChange={(v) => setForm({ ...form, restricted: v })} />
              </div>
              <div className="flex items-center justify-between">
                <Label>Monitor for after-hours presence</Label>
                <Switch checked={form.after_hours_monitored} onCheckedChange={(v) => setForm({ ...form, after_hours_monitored: v })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Loitering threshold (seconds)</Label>
                <Input type="number" min={5} value={form.loitering_threshold_s} onChange={(e) => setForm({ ...form, loitering_threshold_s: Number(e.target.value) })} />
              </div>
              <Button disabled={!form.name || !form.camera_id || form.polygon.length < 3 || createMutation.isPending} onClick={() => createMutation.mutate()}>
                Save Zone
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {(zonesQuery.data ?? []).map((zone) => (
          <div key={zone.id} className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
            <div className="flex flex-col">
              <span className="font-medium">{zone.name}</span>
              <span className="text-xs text-muted-foreground">{cameraById(zone.camera_id)?.name ?? "Unknown camera"} · loiter ≥{zone.loitering_threshold_s}s</span>
            </div>
            <div className="flex items-center gap-2">
              {zone.restricted && <Badge variant="destructive">Restricted</Badge>}
              {zone.after_hours_monitored && <Badge variant="outline">After-hours</Badge>}
              <Button size="icon" variant="ghost" onClick={() => deleteMutation.mutate(zone.id)}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function SchedulesTab() {
  const queryClient = useQueryClient()
  const camerasQuery = useQuery({ queryKey: ["cameras"], queryFn: () => api.get<Camera[]>("/config/cameras") })
  const schedulesQuery = useQuery({ queryKey: ["schedules"], queryFn: () => api.get<Schedule[]>("/config/schedules") })

  const saveMutation = useMutation({
    mutationFn: (payload: { existing?: Schedule; camera_id: string; business_hours: Schedule["business_hours"] }) =>
      payload.existing
        ? api.put<Schedule>(`/config/schedules/${payload.existing.id}`, { scope: "camera", scope_id: payload.camera_id, business_hours: payload.business_hours })
        : api.post<Schedule>("/config/schedules", { scope: "camera", scope_id: payload.camera_id, business_hours: payload.business_hours }),
    onSuccess: () => {
      toast.success("Schedule saved")
      queryClient.invalidateQueries({ queryKey: ["schedules"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div className="flex flex-col gap-3">
      {(camerasQuery.data ?? []).map((cam) => {
        const existing = schedulesQuery.data?.find((s) => s.scope === "camera" && s.scope_id === cam.id)
        return <CameraScheduleCard key={cam.id} camera={cam} existing={existing} onSave={(hours) => saveMutation.mutate({ existing, camera_id: cam.id, business_hours: hours })} />
      })}
    </div>
  )
}

function CameraScheduleCard({ camera, existing, onSave }: { camera: Camera; existing?: Schedule; onSave: (hours: Schedule["business_hours"]) => void }) {
  const [hours, setHours] = useState<Schedule["business_hours"]>(existing?.business_hours ?? Object.fromEntries(DAYS.map((d) => [d.key, []])))

  function toggleDay(day: string, open: boolean) {
    setHours((h) => ({ ...h, [day]: open ? [["08:00", "20:00"]] : [] }))
  }
  function setTime(day: string, idx: 0 | 1, value: string) {
    setHours((h) => {
      const current = h[day]?.[0] ?? ["08:00", "20:00"]
      const updated: [string, string] = idx === 0 ? [value, current[1]] : [current[0], value]
      return { ...h, [day]: [updated] }
    })
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm">{camera.name}</CardTitle>
        <Button size="sm" variant="outline" onClick={() => onSave(hours)}>Save</Button>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {DAYS.map((d) => {
          const isOpen = (hours[d.key] ?? []).length > 0
          const range = hours[d.key]?.[0] ?? ["08:00", "20:00"]
          return (
            <div key={d.key} className="flex flex-col gap-1.5 rounded-md border border-border p-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">{d.label}</span>
                <Switch checked={isOpen} onCheckedChange={(v) => toggleDay(d.key, v)} />
              </div>
              {isOpen && (
                <div className="flex items-center gap-1">
                  <Input type="time" value={range[0]} onChange={(e) => setTime(d.key, 0, e.target.value)} className="h-7 text-xs" />
                  <span className="text-xs text-muted-foreground">–</span>
                  <Input type="time" value={range[1]} onChange={(e) => setTime(d.key, 1, e.target.value)} className="h-7 text-xs" />
                </div>
              )}
              {!isOpen && <span className="text-[10px] text-muted-foreground">Closed all day (after-hours)</span>}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function SopsTab() {
  const queryClient = useQueryClient()
  const sopsQuery = useQuery({ queryKey: ["sops"], queryFn: () => api.get<SOP[]>("/config/sops") })
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const saveMutation = useMutation({
    mutationFn: (sop: SOP) => api.put<SOP>(`/config/sops/${sop.id}`, { incident_type: sop.incident_type, title: sop.title, steps_text: drafts[sop.id] ?? sop.steps_text }),
    onSuccess: () => {
      toast.success("SOP saved")
      queryClient.invalidateQueries({ queryKey: ["sops"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div className="flex flex-col gap-3">
      {(sopsQuery.data ?? []).map((sop) => (
        <Card key={sop.id}>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm">{sop.title}</CardTitle>
            <Button size="sm" variant="outline" onClick={() => saveMutation.mutate(sop)}>Save</Button>
          </CardHeader>
          <CardContent>
            <Textarea
              rows={4}
              defaultValue={sop.steps_text}
              onChange={(e) => setDrafts((d) => ({ ...d, [sop.id]: e.target.value }))}
            />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
