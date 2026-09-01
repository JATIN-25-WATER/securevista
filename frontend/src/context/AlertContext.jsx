import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from './AuthContext';
import { sirenManager } from '../utils/sirenAudio';

const AlertContext = createContext(null);

export const AlertProvider = ({ children }) => {
  const { user, token, isAuthenticated } = useAuth();
  const [alerts, setAlerts] = useState([]);
  const [activePopupAlert, setActivePopupAlert] = useState(null);
  const [sirenMuted, setSirenMuted] = useState(false);
  const [audioUnlocked, setAudioUnlocked] = useState(false);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Initial fetch of recent alerts
  const fetchAlerts = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch('/alerts?limit=100', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAlerts(data);
      }
    } catch (e) {
      console.warn('Failed to fetch initial alerts:', e);
    }
  }, [token]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Unlock browser audio context on first click/login
  const unlockAudio = useCallback(() => {
    sirenManager.unlock();
    setAudioUnlocked(true);
  }, []);

  // WebSocket Connection Lifecycle
  useEffect(() => {
    if (!isAuthenticated || !token) {
      if (wsRef.current) {
        wsRef.current.close();
      }
      return;
    }

    const connectWS = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/alerts/ws?token=${encodeURIComponent(token)}`;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('Real-time security WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);

          if (payload.type === 'NEW_ALERT') {
            const newAlert = payload.data;
            const camId = Number(newAlert.camera_id);

            // Camera-specific allowed alert types whitelist
            const allowedAlertsMap = {
              1: ['loitering', 'camera_offline', 'camera_frozen', 'camera_blackout'],
              2: ['loitering', 'camera_offline', 'camera_frozen', 'camera_blackout'],
              3: ['restricted_zone_entry'],
            };

            const allowedTypes = allowedAlertsMap[camId];
            if (allowedTypes && !allowedTypes.includes(newAlert.event_type)) {
              return;
            }

            // Enforce camera filtering per operator account
            if (user?.username === 'operator 1' && camId !== 1) return;
            if (user?.username === 'operator 2' && camId !== 2) return;
            if (user?.username === 'operator 3' && camId !== 3) return;

            setAlerts((prev) => [newAlert, ...prev.filter(a => a.id !== newAlert.id)]);
            
            // Set active popup alert for overlay & trigger siren
            if (!newAlert.acknowledged) {
              setActivePopupAlert(newAlert);
              if (!sirenMuted) {
                sirenManager.startSiren();
              }
            }
          } else if (payload.type === 'ALERT_ACKNOWLEDGED') {
            const { alert_id, acknowledged_by, acknowledged_at } = payload.data;
            setAlerts((prev) =>
              prev.map((a) =>
                a.id === alert_id
                  ? {
                      ...a,
                      acknowledged: true,
                      acknowledged_by_username: acknowledged_by,
                      acknowledged_at,
                    }
                  : a
              )
            );

            // If current popup alert was acknowledged, dismiss popup and stop siren
            setActivePopupAlert((current) => {
              if (current && current.id === alert_id) {
                sirenManager.stopSiren();
                return null;
              }
              return current;
            });
          }
        } catch (err) {
          console.error('Error handling WebSocket message:', err);
        }
      };

      ws.onclose = (e) => {
        console.log('WebSocket closed:', e.reason);
        reconnectTimeoutRef.current = setTimeout(connectWS, 3000);
      };

      ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
      };
    };

    connectWS();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isAuthenticated, token, sirenMuted]);

  // Acknowledge alert via API
  const acknowledgeAlert = async (alertId) => {
    try {
      const res = await fetch(`/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        sirenManager.stopSiren();
        setActivePopupAlert((current) => (current && current.id === alertId ? null : current));
        setAlerts((prev) =>
          prev.map((a) =>
            a.id === alertId
              ? {
                  ...a,
                  acknowledged: true,
                  acknowledged_by_username: data.acknowledged_by,
                  acknowledged_at: data.acknowledged_at,
                }
              : a
          )
        );
        return true;
      }
    } catch (e) {
      console.error('Failed to acknowledge alert:', e);
    }
    return false;
  };

  const toggleSirenMute = () => {
    if (sirenMuted) {
      setSirenMuted(false);
      if (activePopupAlert) {
        sirenManager.startSiren();
      }
    } else {
      setSirenMuted(true);
      sirenManager.stopSiren();
    }
  };

  const dismissPopup = () => {
    sirenManager.stopSiren();
    setActivePopupAlert(null);
  };

  return (
    <AlertContext.Provider
      value={{
        alerts,
        activePopupAlert,
        acknowledgeAlert,
        dismissPopup,
        sirenManager,
        sirenMuted,
        toggleSirenMute,
        audioUnlocked,
        unlockAudio,
        refetchAlerts: fetchAlerts,
      }}
    >
      {children}
    </AlertContext.Provider>
  );
};

export const useAlerts = () => {
  const context = useContext(AlertContext);
  if (!context) {
    throw new Error('useAlerts must be used within an AlertProvider');
  }
  return context;
};
