import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import type {
  AuditLogEntry,
  AuditVerifyResult,
  FalsePositiveAnalytics,
  ModelPassport,
  ReplayScenario,
  ReplaySimulateResult,
  ScorecardRun,
  VerifyResult,
} from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export default function Governance() {
  return (
    <div className="mx-auto max-w-4xl p-4">
      <Tabs defaultValue="verifier">
        <TabsList>
          <TabsTrigger value="verifier">Evidence Verifier</TabsTrigger>
          <TabsTrigger value="audit">Audit Records</TabsTrigger>
          <TabsTrigger value="passport">Model Passport</TabsTrigger>
          <TabsTrigger value="analytics">Policy &amp; Analytics</TabsTrigger>
        </TabsList>
        <TabsContent value="verifier"><VerifierTab /></TabsContent>
        <TabsContent value="audit"><AuditTab /></TabsContent>
        <TabsContent value="passport"><PassportTab /></TabsContent>
        <TabsContent value="analytics"><AnalyticsTab /></TabsContent>
      </Tabs>
    </div>
  )
}

function VerifierTab() {
  const [evidenceId, setEvidenceId] = useState("")
  const [result, setResult] = useState<VerifyResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const publicKeyQuery = useQuery({ queryKey: ["public-key"], queryFn: () => api.get<{ public_key_pem: string }>("/evidence/public-key") })

  async function verify() {
    setError(null)
    setResult(null)
    try {
      setResult(await api.get<VerifyResult>(`/evidence/${evidenceId}/verify`))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verification failed")
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader><CardTitle className="text-sm">Verify an evidence package</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Input placeholder="Evidence package ID" value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)} />
            <Button onClick={verify} disabled={!evidenceId}>Verify</Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {result && (
            <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm">
              <VerifyRow ok={result.sha256_matches} label="SHA-256 hash matches stored value" />
              <VerifyRow ok={result.signature_valid} label="Ed25519 signature valid" />
              <p className="break-all text-xs text-muted-foreground">Computed: {result.computed_sha256}</p>
              <p className="break-all text-xs text-muted-foreground">Stored: {result.stored_sha256}</p>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Verification public key</CardTitle></CardHeader>
        <CardContent>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-muted/40 p-3 text-[11px]">{publicKeyQuery.data?.public_key_pem ?? "Loading…"}</pre>
          <p className="mt-2 text-xs text-muted-foreground">Anyone can independently verify an evidence package's signature offline using this Ed25519 public key. This confirms the package hasn't been altered since signing — it is not a claim of court-certified evidence.</p>
        </CardContent>
      </Card>
    </div>
  )
}

function VerifyRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      {ok ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-destructive" />}
      <span>{label}</span>
    </div>
  )
}

function AuditTab() {
  const logQuery = useQuery({ queryKey: ["audit-log"], queryFn: () => api.get<AuditLogEntry[]>("/audit?limit=200") })
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null)

  async function verifyChain() {
    try {
      setVerifyResult(await api.get<AuditVerifyResult>("/audit/verify"))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to verify audit chain")
    }
  }

  if (logQuery.isError) {
    return <p className="p-4 text-sm text-muted-foreground">Your role does not have access to the audit trail.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Button size="sm" variant="outline" onClick={verifyChain}><ShieldCheck className="h-4 w-4" /> Verify hash chain</Button>
        {verifyResult && (
          <Badge variant={verifyResult.valid ? "success" : "destructive"}>
            {verifyResult.valid ? `Chain intact (${verifyResult.total_entries} entries)` : `Broken at entry #${verifyResult.broken_at_id}`}
          </Badge>
        )}
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/40 text-muted-foreground">
            <tr>
              <th className="px-2 py-1.5">Time</th>
              <th className="px-2 py-1.5">Actor</th>
              <th className="px-2 py-1.5">Action</th>
              <th className="px-2 py-1.5">Hash</th>
            </tr>
          </thead>
          <tbody>
            {(logQuery.data ?? []).map((entry) => (
              <tr key={entry.id} className="border-t border-border">
                <td className="px-2 py-1.5 whitespace-nowrap">{new Date(entry.ts_iso).toLocaleString()}</td>
                <td className="px-2 py-1.5">{entry.actor}</td>
                <td className="px-2 py-1.5">{entry.action}</td>
                <td className="px-2 py-1.5 font-mono">{entry.hash.slice(0, 10)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PassportTab() {
  const passportQuery = useQuery({
    queryKey: ["passport"],
    queryFn: () => api.get<{ passport: ModelPassport; scorecard_runs: ScorecardRun[] }>("/passport"),
  })
  const passport = passportQuery.data?.passport
  const runs = passportQuery.data?.scorecard_runs ?? []

  if (!passport) return <p className="p-4 text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader><CardTitle className="text-sm">{passport.model_name} — {passport.model_version}</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p><span className="font-medium">Task: </span>{passport.task}</p>
          <p><span className="font-medium">Training data: </span>{passport.training_data}</p>
          <p><span className="font-medium">Tracking: </span>{passport.tracking}</p>
          <div>
            <p className="mb-1 font-medium">Known limitations</p>
            <ul className="list-inside list-disc text-muted-foreground">
              {passport.known_limitations.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
          <div>
            <p className="mb-1 font-medium">Explicitly excluded capabilities</p>
            <ul className="list-inside list-disc text-muted-foreground">
              {passport.excluded_capabilities.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Measured performance scorecard</CardTitle></CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No scenario replay runs recorded yet. Run the deterministic test suite to populate this.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr><th className="py-1">Scenario</th><th className="py-1">Precision</th><th className="py-1">Recall</th><th className="py-1">Avg latency</th><th className="py-1">Run at</th></tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="py-1.5">{r.scenario_id}</td>
                      <td className="py-1.5">{(r.precision * 100).toFixed(0)}%</td>
                      <td className="py-1.5">{(r.recall * 100).toFixed(0)}%</td>
                      <td className="py-1.5">{r.avg_latency_ms.toFixed(0)} ms</td>
                      <td className="py-1.5">{new Date(r.run_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function AnalyticsTab() {
  const { user } = useAuth()
  return (
    <div className="flex flex-col gap-4">
      {/* /api/replay/* is admin-only server-side; only admins can act on policy
          changes anyway, so hide it rather than show operators/supervisors a
          scenario dropdown that 403s empty with no explanation. */}
      {user?.role === "admin" && <PolicyReplayCard />}
      <FalsePositiveCard />
    </div>
  )
}

function PolicyReplayCard() {
  const [scenarioId, setScenarioId] = useState("")
  const [zoneId, setZoneId] = useState("")
  const [loiteringOverride, setLoiteringOverride] = useState("")
  const [result, setResult] = useState<ReplaySimulateResult | null>(null)

  const scenariosQuery = useQuery({ queryKey: ["replay-scenarios"], queryFn: () => api.get<ReplayScenario[]>("/replay/scenarios") })
  const scenario = scenariosQuery.data?.find((s) => s.id === scenarioId)

  const simulateMutation = useMutation({
    mutationFn: () =>
      api.post<ReplaySimulateResult>("/replay/simulate", {
        scenario_id: scenarioId,
        zone_overrides: zoneId && loiteringOverride
          ? { [zoneId]: { loitering_threshold_s: Number(loiteringOverride) } }
          : {},
      }),
    onSuccess: setResult,
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Policy replay &amp; threshold simulation</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Preview how a proposed loitering-threshold change would have played out against a deterministic
          scenario, without touching any live zone configuration.
        </p>
        <Select value={scenarioId} onValueChange={(v) => { setScenarioId(v); setZoneId(""); setResult(null) }}>
          <SelectTrigger><SelectValue placeholder="Select a scenario" /></SelectTrigger>
          <SelectContent>
            {(scenariosQuery.data ?? []).map((s) => <SelectItem key={s.id} value={s.id}>{s.id} — {s.description}</SelectItem>)}
          </SelectContent>
        </Select>
        {scenario && (
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">Zone</label>
              <Select value={zoneId} onValueChange={setZoneId}>
                <SelectTrigger className="w-56"><SelectValue placeholder="Select a zone" /></SelectTrigger>
                <SelectContent>
                  {scenario.zones.map((z) => <SelectItem key={z.id} value={z.id}>{z.name} (current: {z.loitering_threshold_s}s)</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-muted-foreground">Proposed loitering threshold (s)</label>
              <Input type="number" min={0} className="w-40" value={loiteringOverride} onChange={(e) => setLoiteringOverride(e.target.value)} />
            </div>
            <Button size="sm" disabled={!zoneId || !loiteringOverride || simulateMutation.isPending} onClick={() => simulateMutation.mutate()}>
              Simulate
            </Button>
          </div>
        )}
        {result && (
          <div className="grid grid-cols-2 gap-3 rounded-md border border-border p-3 text-sm">
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Baseline (current policy)</p>
              {Object.entries(result.baseline).length === 0 && <p className="text-xs text-muted-foreground">No events</p>}
              {Object.entries(result.baseline).map(([type, count]) => <p key={type}>{type}: {count}</p>)}
            </div>
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Proposed policy</p>
              {Object.entries(result.proposed).length === 0 && <p className="text-xs text-muted-foreground">No events</p>}
              {Object.entries(result.proposed).map(([type, count]) => <p key={type}>{type}: {count}</p>)}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function FalsePositiveCard() {
  const analyticsQuery = useQuery({ queryKey: ["false-positive-analytics"], queryFn: () => api.get<FalsePositiveAnalytics>("/incidents/analytics/false-positives") })
  const data = analyticsQuery.data

  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">False-positive analytics</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Based on the disposition a responder sets when resolving an incident — never inferred automatically.
          {data && ` ${data.total_dispositioned} incident(s) have a disposition recorded so far.`}
        </p>
        {data && Object.keys(data.by_type).length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-muted-foreground">
                <tr><th className="py-1">Incident type</th><th className="py-1">Resolved</th><th className="py-1">False positives</th><th className="py-1">Rate</th></tr>
              </thead>
              <tbody>
                {Object.entries(data.by_type).map(([type, bucket]) => (
                  <tr key={type} className="border-t border-border">
                    <td className="py-1.5">{type}</td>
                    <td className="py-1.5">{bucket.total}</td>
                    <td className="py-1.5">{bucket.false_positive}</td>
                    <td className="py-1.5">{(bucket.false_positive_rate * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No dispositioned incidents yet — set a disposition when resolving an incident to populate this.</p>
        )}
      </CardContent>
    </Card>
  )
}
