import { useEffect, useRef } from "react"
import { getToken } from "./api"

export interface LiveEvent {
  type: "observation" | "camera_status" | "incident" | "scene_warning"
  [key: string]: unknown
}

/** Subscribes to the live event feed (observations, camera health, incidents)
 * and invokes onEvent for each message. Reconnects automatically on drop. */
export function useLiveFeed(onEvent: (event: LiveEvent) => void) {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    let socket: WebSocket | null = null
    let closedByCleanup = false
    let retryTimer: ReturnType<typeof setTimeout>

    function connect() {
      const token = getToken()
      if (!token) {
        // No token yet (e.g. right after logout, or a race with login) --
        // keep retrying on the same cadence as a dropped connection would,
        // otherwise this give up silently and never reconnect even once a
        // token becomes available, since onclose never fires without a socket.
        retryTimer = setTimeout(connect, 2000)
        return
      }
      const protocol = window.location.protocol === "https:" ? "wss" : "ws"
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/live?token=${encodeURIComponent(token)}`)
      socket.onmessage = (event) => {
        try {
          handlerRef.current(JSON.parse(event.data))
        } catch {
          /* ignore malformed message */
        }
      }
      socket.onclose = () => {
        if (!closedByCleanup) {
          retryTimer = setTimeout(connect, 2000)
        }
      }
    }

    connect()
    return () => {
      closedByCleanup = true
      clearTimeout(retryTimer)
      socket?.close()
    }
  }, [])
}
