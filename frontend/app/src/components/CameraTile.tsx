import { useState } from "react"
import { AlertTriangle, Eye, EyeOff, VideoOff, WifiOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { getToken } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { Camera } from "@/lib/types"

const STATUS_META: Record<Camera["status"], { label: string; variant: "success" | "destructive" | "warning" | "secondary"; icon?: typeof WifiOff }> = {
  online: { label: "Online", variant: "success" },
  starting: { label: "Starting…", variant: "secondary" },
  offline: { label: "Offline", variant: "destructive", icon: WifiOff },
  frozen: { label: "Frozen feed", variant: "warning", icon: VideoOff },
  blackout: { label: "Blackout / covered", variant: "destructive", icon: EyeOff },
  blurred: { label: "Severe blur", variant: "warning", icon: AlertTriangle },
  retired: { label: "Retired", variant: "secondary", icon: EyeOff },
}

export default function CameraTile({ camera }: { camera: Camera }) {
  const meta = STATUS_META[camera.status] ?? STATUS_META.starting
  const showVideo = camera.status !== "offline"
  const token = getToken()
  const [privacyBlur, setPrivacyBlur] = useState(false)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 py-2.5">
        <span className="truncate text-sm font-medium">{camera.name}</span>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            size="icon"
            variant={privacyBlur ? "default" : "ghost"}
            className="h-6 w-6"
            title={privacyBlur ? "Blurring people — click to show raw feed" : "Blur people on this feed"}
            onClick={() => setPrivacyBlur((v) => !v)}
          >
            {privacyBlur ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </Button>
          <Badge variant={meta.variant} className="gap-1">
            {meta.icon && <meta.icon className="h-3 w-3" />}
            {meta.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className={cn("relative aspect-video w-full bg-black")}>
          {showVideo ? (
            <img
              src={`/api/stream/${camera.id}/mjpeg?token=${encodeURIComponent(token ?? "")}&blur=${privacyBlur}`}
              alt={camera.name}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <WifiOff className="h-6 w-6" />
              <span className="text-xs">No signal</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
