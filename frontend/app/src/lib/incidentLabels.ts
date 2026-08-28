export const INCIDENT_TYPE_LABEL: Record<string, string> = {
  restricted_entry: "Restricted-zone entry",
  after_hours: "After-hours presence",
  loitering: "Loitering",
  camera_offline: "Camera offline",
  camera_frozen: "Frozen feed",
  camera_blackout: "Camera blackout",
  camera_blur: "Severe camera blur",
  fall_warning: "Fall/collapse warning",
  abandoned_object_warning: "Abandoned-object warning",
  fire_smoke_warning: "Fire/smoke visual warning",
}

export const HEURISTIC_WARNING_TYPES = new Set(["fall_warning", "abandoned_object_warning", "fire_smoke_warning"])
