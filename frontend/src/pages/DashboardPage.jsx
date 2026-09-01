import React, { useState, useEffect, useCallback } from 'react';
import { Camera, AlertTriangle, ShieldCheck, RefreshCw, Radio } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useAlerts } from '../context/AlertContext';
import { CameraCard } from '../components/CameraCard';

export const DashboardPage = () => {
  const { token } = useAuth();
  const { alerts, refetchAlerts } = useAlerts();
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const fetchCameras = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch('/cameras', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        throw new Error('Failed to load camera list');
      }
      const data = await res.json();
      setCameras(data);
      setError('');
    } catch (err) {
      setError(err.message || 'Error connecting to camera management API');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    fetchCameras();
  }, [fetchCameras]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchCameras();
    refetchAlerts();
  };

  const activeCamerasCount = cameras.filter((c) => c.status === 'active').length;
  const unackAlertsCount = alerts.filter((a) => !a.acknowledged).length;

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-white tracking-wide">SURVEILLANCE DASHBOARD</h1>
          <p className="text-slate-400 text-sm">Real-time dynamic multi-camera security control center</p>
        </div>

        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="self-start md:self-auto py-2.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium text-sm flex items-center gap-2 transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh All</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-xs font-mono text-slate-500 uppercase block">Total Cameras</span>
            <span className="text-2xl font-bold text-white mt-1 block">{cameras.length}</span>
          </div>
          <div className="p-3 bg-blue-500/10 text-blue-400 rounded-xl border border-blue-500/20">
            <Camera className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-xs font-mono text-slate-500 uppercase block">Active Streams</span>
            <span className="text-2xl font-bold text-emerald-400 mt-1 block">{activeCamerasCount}</span>
          </div>
          <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
            <Radio className="w-6 h-6 animate-pulse" />
          </div>
        </div>

        <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-xs font-mono text-slate-500 uppercase block">Total Alerts</span>
            <span className="text-2xl font-bold text-white mt-1 block">{alerts.length}</span>
          </div>
          <div className="p-3 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/20">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between">
          <div>
            <span className="text-xs font-mono text-slate-500 uppercase block">Unacknowledged</span>
            <span className={`text-2xl font-bold mt-1 block ${unackAlertsCount > 0 ? 'text-red-500 animate-pulse' : 'text-slate-400'}`}>
              {unackAlertsCount}
            </span>
          </div>
          <div className="p-3 bg-red-500/10 text-red-500 rounded-xl border border-red-500/20">
            <ShieldCheck className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Main Cameras Grid */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 font-mono">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-red-500" />
          Loading dynamic camera feeds from backend...
        </div>
      ) : error ? (
        <div className="p-6 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-center">
          {error}
        </div>
      ) : cameras.length === 0 ? (
        <div className="p-12 bg-slate-900 border border-slate-800 rounded-2xl text-center space-y-3">
          <Camera className="w-12 h-12 text-slate-700 mx-auto" />
          <h3 className="text-lg font-bold text-white">No Cameras Configured</h3>
          <p className="text-slate-400 text-sm max-w-md mx-auto">
            No active cameras found in the backend database. Add a camera using the API or check backend camera seed data.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameras.map((camera) => (
            <CameraCard
              key={camera.id}
              camera={camera}
              alerts={alerts}
              onStatusChange={fetchCameras}
            />
          ))}
        </div>
      )}
    </div>
  );
};
