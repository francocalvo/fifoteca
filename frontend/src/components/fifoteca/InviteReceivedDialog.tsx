import { useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useGlobalWS } from "@/contexts/GlobalWebSocketContext"

export function InviteReceivedDialog() {
  const { pendingInvite, setPendingInvite, sendMessage } = useGlobalWS()
  const navigate = useNavigate()
  const [countdown, setCountdown] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Start countdown when invite appears
  useEffect(() => {
    if (pendingInvite) {
      setCountdown(pendingInvite.expires_in)
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
      setCountdown(0)
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [pendingInvite])

  const handleAccept = useCallback(() => {
    if (!pendingInvite) return
    sendMessage("accept_invite", { invite_id: pendingInvite.invite_id })
    const roomCode = pendingInvite.room_code
    setPendingInvite(null)
    navigate({
      to: "/fifoteca/game/$roomCode",
      params: { roomCode },
    })
  }, [pendingInvite, sendMessage, setPendingInvite, navigate])

  const handleDecline = useCallback(() => {
    if (!pendingInvite) return
    sendMessage("decline_invite", { invite_id: pendingInvite.invite_id })
    setPendingInvite(null)
  }, [pendingInvite, sendMessage, setPendingInvite])

  return (
    <Dialog
      open={!!pendingInvite}
      onOpenChange={(open) => {
        if (!open) handleDecline()
      }}
    >
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Game Invite</DialogTitle>
          <DialogDescription>
            {pendingInvite?.inviter_display_name ?? "Someone"} invited you to
            play! ({countdown}s)
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleDecline}>
            Decline
          </Button>
          <Button onClick={handleAccept} disabled={countdown <= 0}>
            Accept
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
