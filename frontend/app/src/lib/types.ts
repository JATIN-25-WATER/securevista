export type Role = "admin" | "operator" | "supervisor"

export interface CurrentUser {
  id: string
  username: string
  role: Role
  display_name: string
}

export interface Camera {
  id: string
  name: string
  source_type: "mp4" | "webcam" | "rtsp"
  uri: string
  loop: boolean
  status: "starting" | "online" | "offline" | "frozen" | "blackout" | "blurred" | "retired"
  consecutive_failures: number
  active: boolean
}

export interface Zone {
  id: string
  camera_id: string
  name: string
  polygon: [number, number][]
  restricted: boolean
  loitering_threshold_s: number
  after_hours_monitored: boolean
}

export interface Schedule {
  id: string
  scope: "camera" | "zone"
  scope_id: string
  business_hours: Record<string, [string, string][]>
}

export interface SOP {
  id: string
  incident_type: string
  title: string
  steps_text: string
}

export interface Observation {
  schema_version: number
  id: string
  camera_id: string
  zone_id: string | null
  track_id: number
  ts: string
  bbox: [number, number, number, number]
  event_type: string
  confidence: number
}

export interface IncidentEvent {
  id: string
  actor_id: string | null
  action: string
  ts: string
  note: string | null
}

export interface IncidentExplanation {
  rule: string
  camera: string
  zone: string | null
  observation_count: number
  first_observed: string
  last_observed: string
  avg_detector_confidence: number
  camera_health_at_scoring: string
  access_event_matched: boolean
  narrative: string
}

export type IncidentDisposition = "true_positive" | "false_positive" | "uncertain"

export interface Incident {
  id: string
  type: string
  status: "new" | "acknowledged" | "investigating" | "escalated" | "resolved"
  impact_score: number
  confidence_score: number
  explanation: IncidentExplanation
  camera_id: string | null
  zone_id: string | null
  opened_at: string
  updated_at: string
  closed_at: string | null
  disposition: IncidentDisposition | null
  events: IncidentEvent[]
}

export interface FalsePositiveBucket {
  total: number
  false_positive: number
  false_positive_rate: number
}

export interface FalsePositiveAnalytics {
  total_dispositioned: number
  by_type: Record<string, FalsePositiveBucket>
  by_camera_id: Record<string, FalsePositiveBucket>
}

export interface ReplayScenario {
  id: string
  description: string
  expected_event_types: string[]
  zones: { id: string; name: string; restricted: boolean; loitering_threshold_s: number; after_hours_monitored: boolean }[]
}

export interface ReplaySimulateResult {
  scenario_id: string
  description: string
  baseline: Record<string, number>
  proposed: Record<string, number>
}

export interface EvidencePackage {
  id: string
  incident_id: string
  redacted_preview_path: string
  sha256: string
  created_at: string
}

export interface VerifyResult {
  evidence_id: string
  sha256_matches: boolean
  signature_valid: boolean
  computed_sha256: string
  stored_sha256: string
}

export interface AuditLogEntry {
  id: number
  ts_iso: string
  actor: string
  action: string
  details: Record<string, unknown>
  prev_hash: string
  hash: string
}

export interface AuditVerifyResult {
  valid: boolean
  total_entries: number
  broken_at_id: number | null
}

export interface ModelPassport {
  model_name: string
  model_version: string
  task: string
  training_data: string
  tracking: string
  known_limitations: string[]
  excluded_capabilities: string[]
}

export interface ScorecardRun {
  id: string
  run_at: string
  scenario_id: string
  precision: number
  recall: number
  avg_latency_ms: number
  model_version: string
  notes: string | null
}

export interface AccessEvent {
  id: string
  ts: string
  badge_token: string
  zone_id: string | null
  simulated: boolean
}

export interface LiveTrackInfo {
  status: string
  tracks: Record<string, { bbox: [number, number, number, number] }>
}
