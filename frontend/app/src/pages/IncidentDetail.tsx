import { useCallback, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ArrowLeft, FileVideo, Loader2, ShieldAlert } from "lucide-react"
import { api, getToken } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { useLiveFeed, type LiveEvent } from "@/lib/ws"
import { HEURISTIC_WARNING_TYPES, INCIDENT_TYPE_LABEL } from "@/lib/incidentLabels"
import type { EvidencePackage, Incident, SOP } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"

const DISPOSITION_OPTIONS: { value: "true_positive" | "false_positive" | "uncertain"; label: string }[] = [
  { value: "true_positive", label: "True positive" },
  { value: "false_positive", label: "False positive" },
  { value: "uncertain", label: "Uncertain" },
]

const NEXT_ACTIONS: Record<Incident["status"], { action: string; label: string }[]> = {
  new: [{ action: "acknowledge", label: "Acknowledge" }, { action: "investigate", label: "Start Investigating" }, { action: "resolve", label: "Resolve" }],
  acknowledged: [{ action: "investigate", label: "Start Investigating" }, { action: "escalate", label: "Escalate" }, { action: "resolve", label: "Resolve" }],
  investigating: [{ action: "escalate", label: "Escalate" }, { action: "resolve", label: "Resolve" }],
  escalated: [{ action: "resolve", label: "Resolve" }],
  resolved: [],
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [note, setNote] = useState("")
  const [disposition, setDisposition] = useState<"true_positive" | "false_positive" | "uncertain" | null>(null)
  const token = getToken()

  const incidentQuery = useQuery({
    queryKey: ["incident", id],
    queryFn: () => api.get<Incident>(`/incidents/${id}`),
    enabled: !!id,
  })
  const sopsQuery = useQuery({ queryKey: ["sops"], queryFn: () => api.get<SOP[]>("/config/sops") })
  const evidenceQuery = useQuery({
    queryKey: ["evidence", id],
    queryFn: () => api.get<EvidencePackage[]>(`/evidence/incident/${id}`),
    enabled: !!id,
  })

  const handleEvent = useCallback(
    (event: LiveEvent) => {
      if (event.type === "incident" && event.incident_id === id) {
        queryClient.invalidateQueries({ queryKey: ["incident", id] })
      }
    },
    [id, queryClient]
  )
  useLiveFeed(handleEvent)

  const actionMutation = useMutation({
    mutationFn: (action: string) =>
      api.post<Incident>(`/incidents/${id}/action`, {
        action,
        note: note || undefined,
        disposition: action === "resolve" ? disposition ?? undefined : undefined,
      }),
    onSuccess: () => {
      toast.success("Incident updated")
      setNote("")
      setDisposition(null)
      queryClient.invalidateQueries({ queryKey: ["incident", id] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const captureMutation = useMutation({
    mutationFn: () => api.post<EvidencePackage>(`/evidence/${id}/capture`),
    onSuccess: () => {
      toast.success("Evidence package captured")
      queryClient.invalidateQueries({ queryKey: ["evidence", id] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (incidentQuery.isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading incident…</div>
  if (incidentQuery.isError || !incidentQuery.data) return <div className="p-4 text-sm text-destructive">Incident not found.</div>

  const incident = incidentQuery.data
  const sop = sopsQuery.data?.find((s) => s.incident_type === incident.type)
  const canAccessOriginal = user?.role === "admin" || user?.role === "supervisor"

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4">
      <Button variant="ghost" size="sm" className="w-fit" onClick={() => navigate(-1)}>
        <ArrowLeft className="h-4 w-4" /> Back
      </Button>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
          <div>
            <div className="flex items-center gap-2">
              <CardTitle className="text-base">{INCIDENT_TYPE_LABEL[incident.type] ?? incident.type}</CardTitle>
              {HEURISTIC_WARNING_TYPES.has(incident.type) && <Badge variant="warning">Heuristic warning</Badge>}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Opened {new Date(incident.opened_at).toLocaleString()}</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Badge className="capitalize">{incident.status}</Badge>
            {incident.disposition && <Badge variant="secondary" className="capitalize">{incident.disposition.replace(/_/g, " ")}</Badge>}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-muted-foreground">Potential impact</p>
              <p className="text-2xl font-semibold">{Math.round(incident.impact_score)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Evidence confidence</p>
              <p className="text-2xl font-semibold">{Math.round(incident.confidence_score)}</p>
            </div>
          </div>

          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <ShieldAlert className="h-3.5 w-3.5" /> Why was this raised?
            </p>
            <p className="text-sm">{incident.explanation?.narrative}</p>
          </div>

          {sop && (
            <div className="rounded-md border border-border p-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Standard Operating Procedure — {sop.title}</p>
              <p className="whitespace-pre-line text-sm">{sop.steps_text}</p>
            </div>
          )}

          {NEXT_ACTIONS[incident.status].length > 0 && (
            <div className="flex flex-col gap-2">
              <Textarea placeholder="Optional note for this action…" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
              {NEXT_ACTIONS[incident.status].some((a) => a.action === "resolve") && (
                <div className="flex flex-col gap-1.5">
                  <p className="text-xs text-muted-foreground">Disposition (optional, only applied when resolving)</p>
                  <Select value={disposition ?? undefined} onValueChange={(v) => setDisposition(v as typeof disposition)}>
                    <SelectTrigger className="w-56"><SelectValue placeholder="Not set" /></SelectTrigger>
                    <SelectContent>
                      {DISPOSITION_OPTIONS.map((opt) => <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                {NEXT_ACTIONS[incident.status].map(({ action, label }) => (
                  <Button
                    key={action}
                    size="sm"
                    variant={action === "resolve" ? "default" : "outline"}
                    disabled={actionMutation.isPending}
                    onClick={() => actionMutation.mutate(action)}
                  >
                    {actionMutation.isPending && actionMutation.variables === action && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {label}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Evidence</CardTitle>
          <Button size="sm" variant="outline" disabled={captureMutation.isPending} onClick={() => captureMutation.mutate()}>
            {captureMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileVideo className="h-3.5 w-3.5" />}
            Capture evidence
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {(evidenceQuery.data ?? []).map((pkg) => (
            <div key={pkg.id} className="flex flex-col gap-2 rounded-md border border-border p-3">
              <video controls className="w-full rounded" src={`/api/evidence/${pkg.id}/preview?token=${encodeURIComponent(token ?? "")}`} />
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Redacted preview · sha256 {pkg.sha256.slice(0, 12)}…</span>
                <span>{new Date(pkg.created_at).toLocaleString()}</span>
              </div>
              {canAccessOriginal && (
                <a
                  className="text-xs text-primary underline underline-offset-2"
                  href={`/api/evidence/${pkg.id}/original?token=${encodeURIComponent(token ?? "")}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  View original (unredacted) clip — role-protected
                </a>
              )}
            </div>
          ))}
          {(evidenceQuery.data ?? []).length === 0 && <p className="text-sm text-muted-foreground">No evidence captured yet.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-3">
            {incident.events.map((ev) => (
              <li key={ev.id} className="flex flex-col gap-0.5 border-l-2 border-border pl-3">
                <span className="text-sm font-medium capitalize">{ev.action.replace(/_/g, " ")}</span>
                <span className="text-xs text-muted-foreground">{new Date(ev.ts).toLocaleString()}</span>
                {ev.note && <span className="text-xs">{ev.note}</span>}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      <Separator />
    </div>
  )
}
