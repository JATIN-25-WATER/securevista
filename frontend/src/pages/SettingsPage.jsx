import React from 'react';
import { Settings, Shield, Volume2, Key, Database, UserCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useAlerts } from '../context/AlertContext';

export const SettingsPage = () => {
  const { user } = useAuth();
  const { sirenMuted, toggleSirenMute, audioUnlocked, unlockAudio, sirenManager } = useAlerts();

  const handleTestSiren = () => {
    unlockAudio();
    sirenManager.startSiren();
    setTimeout(() => {
      sirenManager.stopSiren();
    }, 2500);
  };

  return (
    <div className="p-8 space-y-8 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-black text-white tracking-wide flex items-center gap-3">
          <Settings className="w-7 h-7 text-red-500" />
          <span>SYSTEM & ALARM CONFIGURATION</span>
        </h1>
        <p className="text-slate-400 text-sm">Configure security audio sirens, connection preferences, and view account roles</p>
      </div>

      <div className="space-y-6">
        {/* Siren Audio Settings */}
        <div className="p-6 bg-slate-900 border border-slate-800 rounded-2xl space-y-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <Volume2 className="w-5 h-5 text-red-500" />
            <h2 className="text-lg font-bold text-white">Security Siren Audio Controls</h2>
          </div>

          <div className="space-y-4 text-sm text-slate-300">
            <div className="flex items-center justify-between p-4 bg-slate-950 rounded-xl border border-slate-800">
              <div>
                <span className="font-semibold text-white block">Real-time Alert Siren Mute</span>
                <span className="text-xs text-slate-500">Temporarily mute looping audio siren when security alerts occur</span>
              </div>
              <button
                onClick={toggleSirenMute}
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                  sirenMuted
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30'
                }`}
              >
                {sirenMuted ? 'SIREN IS MUTED' : 'SIREN IS ACTIVE'}
              </button>
            </div>

            <div className="flex items-center justify-between p-4 bg-slate-950 rounded-xl border border-slate-800">
              <div>
                <span className="font-semibold text-white block">Test Siren Sound</span>
                <span className="text-xs text-slate-500">Play a 2.5 second sample siren audio test</span>
              </div>
              <button
                onClick={handleTestSiren}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-xl text-xs border border-slate-700 transition-colors"
              >
                🔊 Play Test Siren
              </button>
            </div>
          </div>
        </div>

        {/* User Account & Role Matrix */}
        <div className="p-6 bg-slate-900 border border-slate-800 rounded-2xl space-y-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <Shield className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-bold text-white">Logged-in User Role & Permissions</h2>
          </div>

          <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3 font-mono text-sm">
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Username:</span>
              <span className="text-white font-bold">{user?.username}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Assigned Role:</span>
              <span className="px-2.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 font-bold uppercase text-xs">
                {user?.role}
              </span>
            </div>
            <div className="flex justify-between items-center pt-2 border-t border-slate-900 text-xs">
              <span className="text-slate-500">Capabilities:</span>
              <span className="text-slate-300">
                {user?.role === 'admin'
                  ? 'Full Camera CRUD, Pipeline Controls, Alert Acknowledgement'
                  : user?.role === 'operator'
                  ? 'View Cameras, Start/Stop Pipeline, Alert Acknowledgement'
                  : 'View Cameras, Receive Live Alerts, Alert Acknowledgement'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
