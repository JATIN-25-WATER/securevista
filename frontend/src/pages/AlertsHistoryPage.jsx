import React, { useState, useEffect, useMemo } from 'react';
import { Bell, Filter, CheckCircle2, ShieldAlert, Camera, Clock, Check, Search, RefreshCw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useAlerts } from '../context/AlertContext';
import { getAlertTitle, getAlertSeverityClass, ALERT_TYPE_NAMES } from '../utils/constants';

export const AlertsHistoryPage = () => {
  const { token } = useAuth();
  const { alerts, acknowledgeAlert, refetchAlerts } = useAlerts();

  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState('ALL');
  const [selectedType, setSelectedType] = useState('ALL');
  const [selectedAckStatus, setSelectedAckStatus] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  // Fetch camera list for filter dropdown
  useEffect(() => {
    if (!token) return;
    fetch('/cameras', { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setCameras(data))
      .catch(() => {});
  }, [token]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await refetchAlerts();
    setRefreshing(false);
  };

  // Filtered alerts
  const filteredAlerts = useMemo(() => {
    return alerts.filter((alert) => {
      if (selectedCamera !== 'ALL' && alert.camera_id !== parseInt(selectedCamera, 10)) {
        return false;
      }
      if (selectedType !== 'ALL' && alert.event_type !== selectedType) {
        return false;
      }
      if (selectedAckStatus === 'UNACK' && alert.acknowledged) {
        return false;
      }
      if (selectedAckStatus === 'ACK' && !alert.acknowledged) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const title = getAlertTitle(alert.event_type).toLowerCase();
        const explanation = (alert.explanation || '').toLowerCase();
        const camName = (alert.camera_name || '').toLowerCase();
        if (!title.includes(q) && !explanation.includes(q) && !camName.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [alerts, selectedCamera, selectedType, selectedAckStatus, searchQuery]);

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-white tracking-wide flex items-center gap-3">
            <Bell className="w-7 h-7 text-red-500" />
            <span>SECURITY ALERTS HISTORY</span>
          </h1>
          <p className="text-slate-400 text-sm">Comprehensive real-time incident audit log and responder acknowledgement center</p>
        </div>

        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="self-start md:self-auto py-2.5 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-800 font-medium text-sm flex items-center gap-2 transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          <span>Refresh Logs</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="p-5 bg-slate-900 border border-slate-800 rounded-2xl space-y-4">
        <div className="flex items-center gap-2 text-xs font-mono uppercase text-slate-400 font-semibold">
          <Filter className="w-4 h-4 text-red-500" />
          <span>Filter Security Logs</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search explanation/camera..."
              className="w-full pl-9 pr-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white placeholder-slate-600 focus:outline-none focus:border-red-500/60 text-xs"
            />
          </div>

          {/* Camera Filter */}
          <select
            value={selectedCamera}
            onChange={(e) => setSelectedCamera(e.target.value)}
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-red-500/60 text-xs"
          >
            <option value="ALL">All Cameras ({cameras.length})</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} (ID: {c.id})
              </option>
            ))}
          </select>

          {/* Event Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-red-500/60 text-xs"
          >
            <option value="ALL">All Alert Types</option>
            {Object.entries(ALERT_TYPE_NAMES).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>

          {/* Acknowledged Status Filter */}
          <select
            value={selectedAckStatus}
            onChange={(e) => setSelectedAckStatus(e.target.value)}
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-white focus:outline-none focus:border-red-500/60 text-xs"
          >
            <option value="ALL">All Statuses</option>
            <option value="UNACK">Unacknowledged Only</option>
            <option value="ACK">Acknowledged Only</option>
          </select>
        </div>
      </div>

      {/* Alerts Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-950/80 border-b border-slate-800 text-[11px] font-mono text-slate-400 uppercase tracking-wider">
                <th className="p-4">Alert Event</th>
                <th className="p-4">Camera</th>
                <th className="p-4">Timestamp</th>
                <th className="p-4">Confidence</th>
                <th className="p-4">Impact</th>
                <th className="p-4">Status</th>
                <th className="p-4">Acknowledged By</th>
                <th className="p-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-sm">
              {filteredAlerts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-12 text-center text-slate-500 font-mono">
                    No matching security alerts found.
                  </td>
                </tr>
              ) : (
                filteredAlerts.map((alert) => {
                  const severityClass = getAlertSeverityClass(alert.event_type, alert.impact_score);
                  return (
                    <tr
                      key={alert.id}
                      className={`hover:bg-slate-800/40 transition-colors ${
                        !alert.acknowledged ? 'bg-red-500/5' : ''
                      }`}
                    >
                      {/* Alert Event */}
                      <td className="p-4">
                        <div className="space-y-1">
                          <span className={`inline-block px-2.5 py-0.5 text-xs font-bold rounded uppercase border ${severityClass}`}>
                            {getAlertTitle(alert.event_type)}
                          </span>
                          <p className="text-xs text-slate-300 line-clamp-1">{alert.explanation}</p>
                        </div>
                      </td>

                      {/* Camera */}
                      <td className="p-4 font-mono text-xs text-slate-300">
                        <div className="flex items-center gap-1.5">
                          <Camera className="w-3.5 h-3.5 text-slate-500" />
                          <span>{alert.camera_name || `Cam #${alert.camera_id}`}</span>
                        </div>
                      </td>

                      {/* Timestamp */}
                      <td className="p-4 font-mono text-xs text-slate-400 whitespace-nowrap">
                        {new Date(alert.timestamp).toLocaleString()}
                      </td>

                      {/* Confidence */}
                      <td className="p-4 font-mono text-xs text-emerald-400">
                        {((alert.confidence_score || 0) * 100).toFixed(0)}%
                      </td>

                      {/* Impact */}
                      <td className="p-4 font-mono text-xs text-slate-300">
                        {((alert.impact_score || 0) * 100).toFixed(0)}%
                      </td>

                      {/* Status Badge */}
                      <td className="p-4">
                        {alert.acknowledged ? (
                          <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 inline-flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            ACKNOWLEDGED
                          </span>
                        ) : (
                          <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/40 inline-flex items-center gap-1 animate-pulse">
                            <ShieldAlert className="w-3 h-3" />
                            ACTIVE ALERT
                          </span>
                        )}
                      </td>

                      {/* Acknowledged By & Time */}
                      <td className="p-4 text-xs font-mono text-slate-400">
                        {alert.acknowledged ? (
                          <div>
                            <span className="text-white font-semibold block">{alert.acknowledged_by_username || 'Operator'}</span>
                            <span className="text-[10px] text-slate-500">
                              {alert.acknowledged_at ? new Date(alert.acknowledged_at).toLocaleTimeString() : ''}
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>

                      {/* Action Button */}
                      <td className="p-4 text-right">
                        {!alert.acknowledged ? (
                          <button
                            onClick={() => acknowledgeAlert(alert.id)}
                            className="py-1.5 px-3 rounded-lg bg-red-600 hover:bg-red-500 text-white font-bold text-xs uppercase tracking-wider transition-all shadow-md shadow-red-900/30 flex items-center gap-1 ml-auto"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>Acknowledge</span>
                          </button>
                        ) : (
                          <span className="text-xs text-slate-600 font-mono">Completed</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
