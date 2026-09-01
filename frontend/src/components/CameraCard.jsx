import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Square, AlertTriangle, Radio, ExternalLink, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getAlertTitle } from '../utils/constants';

export const CameraCard = ({ camera, alerts = [], onStatusChange }) => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [loadingAction, setLoadingAction] = useState(false);
  const [imgError, setImgError] = useState(false);

  const canControl = true;

  // Filter alerts for this camera
  const cameraAlerts = alerts.filter((a) => a.camera_id === camera.id);
  const unackCount = cameraAlerts.filter((a) => !a.acknowledged).length;
  const lastAlert = cameraAlerts.length > 0 ? cameraAlerts[0] : null;

  const streamUrl = `/stream/${camera.id}?token=${encodeURIComponent(token)}`;

  const handleStart = async (e) => {
    e.stopPropagation();
    setLoadingAction(true);
    try {
      const res = await fetch(`/cameras/${camera.id}/start`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok && onStatusChange) {
        onStatusChange();
        setImgError(false);
      }
    } catch (err) {
      console.error('Failed to start camera:', err);
    } finally {
      setLoadingAction(false);
    }
  };

  const handleStop = async (e) => {
    e.stopPropagation();
    setLoadingAction(true);
    try {
      const res = await fetch(`/cameras/${camera.id}/stop`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok && onStatusChange) {
        onStatusChange();
      }
    } catch (err) {
      console.error('Failed to stop camera:', err);
    } finally {
      setLoadingAction(false);
    }
  };

  const isOnline = camera.status === 'active';

  return (
    <div
      onClick={() => navigate(`/cameras/${camera.id}`)}
      className={`bg-slate-900 border rounded-xl overflow-hidden hover:border-slate-600 transition-all cursor-pointer group flex flex-col justify-between ${
        unackCount > 0 ? 'border-red-500/60 shadow-[0_0_20px_rgba(239,68,68,0.2)]' : 'border-slate-800'
      }`}
    >
      {/* Card Header */}
      <div className="p-4 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-white group-hover:text-red-400 transition-colors text-base truncate">
              {camera.name}
            </h3>
            <span className="text-xs text-slate-500 font-mono">#{camera.id}</span>
          </div>
          <p className="text-xs text-slate-500 truncate max-w-[200px]">{camera.source_uri}</p>
        </div>

        {/* Status & Unack Badge */}
        <div className="flex items-center gap-2">
          {unackCount > 0 && (
            <span className="px-2 py-0.5 text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/40 rounded-full animate-pulse flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {unackCount}
            </span>
          )}

          <span
            className={`px-2.5 py-1 text-xs font-semibold rounded-full flex items-center gap-1.5 ${
              isOnline
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border border-slate-700'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'}`} />
            {isOnline ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Video Feed Area */}
      <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
        {isOnline && !imgError ? (
          <img
            src={streamUrl}
            alt={camera.name}
            onError={() => setImgError(true)}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="text-center p-6 space-y-2">
            <Radio className="w-10 h-10 text-slate-700 mx-auto animate-pulse" />
            <p className="text-slate-500 text-sm font-medium">
              {isOnline ? 'Connecting Stream...' : 'Camera Stream Stopped'}
            </p>
          </div>
        )}

        {/* Live HUD Overlay on Video */}
        {isOnline && (
          <div className="absolute top-2 left-2 bg-black/60 backdrop-blur-sm px-2.5 py-1 rounded text-[11px] font-mono text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            REC 1080p
          </div>
        )}
      </div>

      {/* Footer Details & Controls */}
      <div className="p-4 bg-slate-950/60 space-y-3">
        {/* Last Alert Summary */}
        <div className="text-xs">
          <span className="text-slate-500 font-mono uppercase block text-[10px]">Last Alert</span>
          {lastAlert ? (
            <div className="flex items-center justify-between text-slate-300 mt-0.5">
              <span className="font-semibold text-red-400 truncate">{getAlertTitle(lastAlert.event_type)}</span>
              <span className="text-slate-500 text-[10px]">
                {new Date(lastAlert.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-slate-500 mt-0.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>No active threats</span>
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-800">
          <div className="flex items-center gap-2">
            {canControl && (
              <>
                {!isOnline ? (
                  <button
                    onClick={handleStart}
                    disabled={loadingAction}
                    className="py-1.5 px-3 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/40 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Start</span>
                  </button>
                ) : (
                  <button
                    onClick={handleStop}
                    disabled={loadingAction}
                    className="py-1.5 px-3 rounded-lg bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/40 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                  >
                    <Square className="w-3.5 h-3.5 fill-current" />
                    <span>Stop</span>
                  </button>
                )}
              </>
            )}
          </div>

          <span className="text-xs text-slate-400 group-hover:text-white font-medium flex items-center gap-1">
            <span>Details</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </span>
        </div>
      </div>
    </div>
  );
};
