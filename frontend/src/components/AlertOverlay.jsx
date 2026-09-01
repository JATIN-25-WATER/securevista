import React from 'react';
import { ShieldAlert, Volume2, VolumeX, CheckCircle, Clock, Camera, Target, AlertTriangle } from 'lucide-react';
import { useAlerts } from '../context/AlertContext';
import { getAlertTitle } from '../utils/constants';

export const AlertOverlay = () => {
  const { activePopupAlert, acknowledgeAlert, sirenMuted, toggleSirenMute, audioUnlocked, unlockAudio } = useAlerts();

  if (!activePopupAlert) return null;

  const handleAcknowledge = async () => {
    await acknowledgeAlert(activePopupAlert.id);
  };

  const alertTitle = getAlertTitle(activePopupAlert.event_type);
  const confidencePct = activePopupAlert.confidence_score
    ? `${(activePopupAlert.confidence_score * 100).toFixed(0)}%`
    : 'N/A';
  const timeFormatted = activePopupAlert.timestamp
    ? new Date(activePopupAlert.timestamp).toLocaleTimeString()
    : 'Just now';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-fade-in" onClick={unlockAudio}>
      <div className="w-full max-w-2xl bg-slate-900 border-2 border-red-600 rounded-2xl shadow-[0_0_80px_rgba(239,68,68,0.6)] alert-flash overflow-hidden text-white">
        {/* Banner Header */}
        <div className="bg-red-600/30 border-b border-red-500/50 p-4 px-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-8 h-8 text-red-500 animate-pulse" />
            <div>
              <span className="text-xs font-mono font-bold tracking-widest text-red-400 uppercase">HIGH SEVERITY SECURITY EVENT</span>
              <h2 className="text-xl font-black text-white tracking-wide">
                🚨 ALERT FROM {activePopupAlert.camera_name || `CAMERA ${activePopupAlert.camera_id}`}
              </h2>
            </div>
          </div>
          <button
            onClick={toggleSirenMute}
            className="p-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-2 text-xs font-semibold"
            title={sirenMuted ? 'Unmute Siren' : 'Mute Siren'}
          >
            {sirenMuted ? <VolumeX className="w-5 h-5 text-slate-400" /> : <Volume2 className="w-5 h-5 text-red-400 animate-bounce" />}
            <span>{sirenMuted ? 'MUTED' : 'SIREN ACTIVE'}</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          <div className="text-center py-2 border-b border-slate-800">
            <h3 className="text-3xl font-black text-red-500 tracking-wider mb-2">{alertTitle}</h3>
            <p className="text-slate-300 text-base">{activePopupAlert.explanation || 'Security rule breach detected by surveillance pipeline.'}</p>
          </div>

          {/* Alert Metadata Grid */}
          <div className="grid grid-cols-2 gap-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800 font-mono text-sm">
            <div className="flex items-center gap-3 text-slate-300">
              <Camera className="w-5 h-5 text-slate-500" />
              <div>
                <span className="text-xs text-slate-500 block font-sans">Camera</span>
                <span className="font-semibold text-white">{activePopupAlert.camera_name || `Camera ${activePopupAlert.camera_id}`}</span>
              </div>
            </div>

            <div className="flex items-center gap-3 text-slate-300">
              <Target className="w-5 h-5 text-slate-500" />
              <div>
                <span className="text-xs text-slate-500 block font-sans">Detection</span>
                <span className="font-semibold text-white">Person (ID: {activePopupAlert.track_id})</span>
              </div>
            </div>

            <div className="flex items-center gap-3 text-slate-300">
              <AlertTriangle className="w-5 h-5 text-slate-500" />
              <div>
                <span className="text-xs text-slate-500 block font-sans">Confidence</span>
                <span className="font-semibold text-emerald-400">{confidencePct}</span>
              </div>
            </div>

            <div className="flex items-center gap-3 text-slate-300">
              <Clock className="w-5 h-5 text-slate-500" />
              <div>
                <span className="text-xs text-slate-500 block font-sans">Time</span>
                <span className="font-semibold text-white">{timeFormatted}</span>
              </div>
            </div>
          </div>

          {/* Siren Active Indicator */}
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-3 flex items-center justify-center gap-3 text-red-400 font-semibold text-sm">
            <Volume2 className="w-5 h-5 animate-pulse" />
            <span>🔊 SIREN ACTIVE — ACTION REQUIRED BY RESPONDER</span>
          </div>

          {!audioUnlocked && (
            <div className="text-center">
              <button
                onClick={unlockAudio}
                className="text-xs text-amber-400 underline hover:text-amber-300 font-mono"
              >
                Click here to enable siren audio if muted by browser
              </button>
            </div>
          )}

          {/* Acknowledge Button */}
          <button
            onClick={handleAcknowledge}
            className="w-full py-4 rounded-xl bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white font-bold text-lg tracking-wider uppercase shadow-lg shadow-red-900/50 transition-all transform hover:scale-[1.01] active:scale-[0.99] flex items-center justify-center gap-3 border border-red-500/50"
          >
            <CheckCircle className="w-6 h-6" />
            <span>ACKNOWLEDGE ALERT</span>
          </button>
        </div>
      </div>
    </div>
  );
};
