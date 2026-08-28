import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { INCIDENT_TYPE_LABEL } from "@/lib/incidentLabels"
import type { Incident } from "@/lib/types"

const STATUS_VARIANT: Record<Incident["status"], "destructive" | "warning" | "secondary" | "success"> = {
  new: "destructive",
  acknowledged: "warning",
  investigating: "warning",
  escalated: "destructive",
  resolved: "success",
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex-1">
      <div className="mb-0.5 flex justify-between text-[10px] text-muted-foreground">
        <span>{label}</span>
        <span>{Math.round(value)}</span>
      </div>
      <div className="h-1 rounded-full bg-muted">
        <div className="h-1 rounded-full bg-primary" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  )
}

export default function IncidentCard({ incident }: { incident: Incident }) {
  return (
    <Link to={`/incidents/${incident.id}`}>
      <Card className="transition-colors hover:border-primary/40 hover:bg-card-hover">
        <CardContent className="flex flex-col gap-2 p-3">
          <div className="flex items-start justify-between gap-2">
            <span className="text-sm font-medium leading-tight">{INCIDENT_TYPE_LABEL[incident.type] ?? incident.type}</span>
            <Badge variant={STATUS_VARIANT[incident.status]} className="shrink-0 capitalize">
              {incident.status}
            </Badge>
          </div>
          <p className="line-clamp-2 text-xs text-muted-foreground">{incident.explanation?.narrative}</p>
          <div className="flex gap-3">
            <ScoreBar label="Impact" value={incident.impact_score} />
            <ScoreBar label="Confidence" value={incident.confidence_score} />
          </div>
          <span className="text-[10px] text-muted-foreground">{new Date(incident.opened_at).toLocaleString()}</span>
        </CardContent>
      </Card>
    </Link>
  )
}
