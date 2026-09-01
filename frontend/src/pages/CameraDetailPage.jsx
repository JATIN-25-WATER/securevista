import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Play, Square, AlertTriangle, ShieldCheck, Clock, CheckCircle2, User, Camera as CameraIcon, Info } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useAlerts } from '../context/AlertContext';
import { getAlertTitle, getAlertSeverityClass } from '../utils/constants';

export const CameraDetailPage = () => {
  const { id } = useParams();
  const cameraId = parseInt(id, 10);
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const { alerts, acknowledgeAlert } = useAlerts();

  const [camera, setCamera] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const canControl = true;

  const fetchCamera = useCallback(async () => {
    if (!token || isNaN(cameraId)) return;
    try {
      const res = await fetch(`/cameras/${cameraId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        throw new Error(`Camera ${cameraId} not found`);
      }
      const data = await res.json();
      setCamera(data);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [cameraId, token]);

  useEffect(() => {
    fetchCamera();
  }, [fetchCamera]);

  const handleStart = async () => {
    setActionLoading(true);
    try {
      const res = await fetch(`/cameras/${cameraId}/start`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) fetchCamera();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    try {
      const res = await fetch(`/cameras/${cameraId}/stop`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) fetchCamera();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(false);
    }
  };

  // STRICT CAMERA FILTER: Show ONLY alerts for THIS camera_id!
  const cameraAlerts = alerts.filter((a) => a.camera_id === cameraId);
  const unackAlerts = cameraAlerts.filter((a) => !a.acknowledged);
  const isOnline = camera?.status === 'active';

  const streamUrl = `/stream/${cameraId}?token=${encodeURIComponent(token)}`;

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono">
        Loading camera details for Camera #{cameraId}...
      </div>
    );
  }

  if (error || !camera) {
    return (
      <div className="p-8 max-w-4xl mx-auto space-y-4">
        <button onClick={() => navigate('/cameras')} className="text-slate-400 hover:text-white flex items-center gap-2 text-sm font-medium">
          <ArrowLeft className="w-4 h-4" /> Back to Cameras
        </button>
        <div className="p-6 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-center font-bold">
          {error || 'Camera not found'}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Navigation & Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/cameras')}
            className="p-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 transition-colors"
            title="Back to camera list"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-black text-white tracking-wide">{camera.name}</h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-slate-800 text-slate-400 border border-slate-700">
                ID: {camera.id}
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">Source: {camera.source_uri}</p>
          </div>
        </div>

        {/* Controls & Status Badge */}
        <div className="flex items-center gap-3">
          <span
            className={`px-3 py-1.5 rounded-full text-xs font-bold flex items-center gap-2 ${
              isOnline
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border border-slate-700'
            }`}
          >
            <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'}`} />
            {isOnline ? 'LIVE STREAM ACTIVE' : 'CAMERA OFFLINE'}
          </span>

          {canControl && (
            <>
              {!isOnline ? (
                <button
                  onClick={handleStart}
                  disabled={actionLoading}
                  className="py-2 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm flex items-center gap-2 transition-all shadow-lg shadow-emerald-900/20"
                >
                  <Play className="w-4 h-4 fill-current" />
                  <span>Start Camera</span>
                </button>
              ) : (
                <button
                  onClick={handleStop}
                  disabled={actionLoading}
                  className="py-2 px-4 rounded-xl bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/40 font-semibold text-sm flex items-center gap-2 transition-all"
                >
                  <Square className="w-4 h-4 fill-current" />
                  <span>Stop Pipeline</span>
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Main Grid: Video Stream Left, Per-Camera Alerts Right */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Live Video Stream & Detection Info */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
            <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                <CameraIcon className="w-4 h-4 text-red-500" />
                <span>CAMERA FEED: {camera.name.toUpperCase()} (ID: {camera.id})</span>
              </div>
              {isOnline && (
                <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  AI DETECTION ACTIVE
                </span>
              )}
            </div>

            <div className="relative aspect-video bg-black flex items-center justify-center">
              {isOnline ? (
                <img
                  src={streamUrl}
                  alt={camera.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="text-center p-12 space-y-3">
                  <Square className="w-12 h-12 text-slate-700 mx-auto" />
                  <p className="text-slate-400 font-medium">Camera Pipeline Stopped</p>
                  <p className="text-xs text-slate-600 max-w-sm">
                    Click "Start Camera" to initialize video source ingestion, YOLO detection, and zone analysis.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Camera Detection & Analytics Panel */}
          <div className="p-6 bg-slate-900 border border-slate-800 rounded-2xl space-y-4">
            <h3 className="font-bold text-white flex items-center gap-2">
              <Info className="w-5 h-5 text-blue-400" />
              <span>Camera #{camera.id} Pipeline Capabilities & Detection Info</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
                <span className="text-slate-500 block">Object Detection</span>
                <span className="text-emerald-400 font-bold">YOLOv8 Person Model</span>
              </div>
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
                <span className="text-slate-500 block">Tracker Module</span>
                <span className="text-blue-400 font-bold">Centroid Tracker</span>
              </div>
              <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-1">
                <span className="text-slate-500 block">Zone Rule Engine</span>
                <span className="text-amber-400 font-bold">Polygon Zone Analyzer</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: STRICT Camera-Specific Alerts List */}
        <div className="space-y-6">
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-500" />
                <h3 className="font-bold text-white">Camera #{camera.id} Alerts</h3>
              </div>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700">
                {cameraAlerts.length} Total
              </span>
            </div>

            {/* Warning if unacknowledged alerts exist for THIS camera */}
            {unackAlerts.length > 0 && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-xs font-semibold flex items-center justify-between animate-pulse">
                <span>{unackAlerts.length} Active Unacknowledged Alert(s)</span>
              </div>
            )}

            {/* List of Camera-Specific Alerts */}
            {cameraAlerts.length === 0 ? (
              <div className="py-12 text-center text-slate-500 space-y-2">
                <ShieldCheck className="w-10 h-10 text-slate-700 mx-auto" />
                <p className="text-sm font-medium">No alerts recorded for Camera #{camera.id}</p>
              </div>
            ) : (
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                {cameraAlerts.map((alert) => {
                  const severityClass = getAlertSeverityClass(alert.event_type, alert.impact_score);
                  return (
                    <div
                      key={alert.id}
                      className={`p-4 rounded-xl border bg-slate-950/70 space-y-2 transition-all ${
                        !alert.acknowledged ? 'border-red-500/60 shadow-[0_0_15px_rgba(239,68,68,0.15)]' : 'border-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase border ${severityClass}`}>
                          {getAlertTitle(alert.event_type)}
                        </span>
                        <span className="text-[11px] font-mono text-slate-500">
                          {new Date(alert.timestamp).toLocaleTimeString()}
                        </span>
                      </div>

                      <p className="text-xs text-slate-300">{alert.explanation}</p>

                      <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono pt-2 border-t border-slate-900">
                        <span>Conf: {((alert.confidence_score || 0) * 100).toFixed(0)}%</span>

                        {alert.acknowledged ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>Ack by {alert.acknowledged_by_username || 'User'}</span>
                          </span>
                        ) : (
                          <button
                            onClick={() => acknowledgeAlert(alert.id)}
                            className="px-2.5 py-1 bg-red-600 hover:bg-red-500 text-white font-bold rounded text-[10px] uppercase transition-colors"
                          >
                            Acknowledge
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
