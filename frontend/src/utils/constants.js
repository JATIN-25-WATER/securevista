export const ALERT_TYPE_NAMES = {
  restricted_zone_entry: 'RESTRICTED ZONE ENTRY',
  after_hours_presence: 'AFTER-HOURS PRESENCE',
  loitering: 'LOITERING DETECTED',
  camera_offline: 'CAMERA OFFLINE',
  camera_frozen: 'CAMERA FROZEN',
  camera_blackout: 'CAMERA BLACKOUT',
};

export const getAlertTitle = (eventType) => {
  return ALERT_TYPE_NAMES[eventType] || eventType?.toUpperCase().replace(/_/g, ' ') || 'SECURITY ALERT';
};

export const getAlertSeverityClass = (eventType, impactScore = 0.5) => {
  if (['restricted_zone_entry', 'camera_offline', 'camera_blackout'].includes(eventType) || impactScore >= 0.8) {
    return 'bg-red-500/20 text-red-400 border-red-500/50';
  }
  if (['after_hours_presence', 'loitering', 'camera_frozen'].includes(eventType) || impactScore >= 0.5) {
    return 'bg-amber-500/20 text-amber-400 border-amber-500/50';
  }
  return 'bg-blue-500/20 text-blue-400 border-blue-500/50';
};
