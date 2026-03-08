import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { FifotecaService } from "@/client"
import { Badge } from "@/components/ui/badge"
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

export interface ManualMatchRequestReceived {
  request_id: string
  request_type: string
  requester_display_name: string
  requester_team_name?: string
  responder_team_name?: string
  requester_score?: number
  responder_score?: number
  rating_difference?: number
  match_id?: string
  current_requester_score?: number
  current_responder_score?: number
  new_requester_score?: number
  new_responder_score?: number
  expires_at: string
}

export function ManualMatchRequestDialog() {
  const queryClient = useQueryClient()
  const { lastGlobalMessage } = useGlobalWS()
  const [pendingRequest, setPendingRequest] =
    useState<ManualMatchRequestReceived | null>(null)
  const [timeRemaining, setTimeRemaining] = useState<string>("")

  // Listen for incoming manual match requests
  useEffect(() => {
    if (lastGlobalMessage?.type === "manual_match_request_received") {
      const payload =
        lastGlobalMessage.payload as unknown as ManualMatchRequestReceived
      setPendingRequest(payload)
    }

    if (lastGlobalMessage?.type === "manual_match_request_accepted") {
      // Refresh data when our request was accepted
      queryClient.invalidateQueries({ queryKey: ["fifoteca", "matches"] })
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      toast.success("Request accepted!", {
        description: "The match has been added to your history.",
      })
    }

    if (lastGlobalMessage?.type === "manual_match_request_declined") {
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      toast.info("Request declined", {
        description: "Your manual match request was declined.",
      })
    }
  }, [lastGlobalMessage, queryClient])

  // Update time remaining countdown
  useEffect(() => {
    if (!pendingRequest) return

    const updateTimer = () => {
      const expiresAt = new Date(pendingRequest.expires_at)
      const now = new Date()
      const diff = expiresAt.getTime() - now.getTime()

      if (diff <= 0) {
        setTimeRemaining("Expired")
        setPendingRequest(null)
        return
      }

      const hours = Math.floor(diff / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

      if (hours > 0) {
        setTimeRemaining(`${hours}h ${minutes}m`)
      } else {
        setTimeRemaining(`${minutes}m`)
      }
    }

    updateTimer()
    const interval = setInterval(updateTimer, 60000) // Update every minute

    return () => clearInterval(interval)
  }, [pendingRequest])

  // Accept mutation
  const acceptMutation = useMutation({
    mutationFn: () =>
      FifotecaService.acceptManualMatchRequest({
        id: pendingRequest!.request_id,
      }),
    onSuccess: () => {
      toast.success("Request accepted")
      queryClient.invalidateQueries({ queryKey: ["fifoteca", "matches"] })
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      setPendingRequest(null)
    },
    onError: (error: Error) => {
      toast.error("Failed to accept", { description: error.message })
    },
  })

  // Decline mutation
  const declineMutation = useMutation({
    mutationFn: () =>
      FifotecaService.declineManualMatchRequest({
        id: pendingRequest!.request_id,
      }),
    onSuccess: () => {
      toast.info("Request declined")
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      setPendingRequest(null)
    },
    onError: (error: Error) => {
      toast.error("Failed to decline", { description: error.message })
    },
  })

  const handleAccept = useCallback(() => {
    acceptMutation.mutate()
  }, [acceptMutation])

  const handleDecline = useCallback(() => {
    declineMutation.mutate()
  }, [declineMutation])

  const isLoading = acceptMutation.isPending || declineMutation.isPending

  const getRequestTypeLabel = (type: string) => {
    switch (type) {
      case "create":
        return "New Match"
      case "edit":
        return "Edit Match"
      case "delete":
        return "Delete Match"
      default:
        return type
    }
  }

  const getRequestTypeBadgeColor = (type: string) => {
    switch (type) {
      case "create":
        return "bg-green-500"
      case "edit":
        return "bg-yellow-500"
      case "delete":
        return "bg-red-500"
      default:
        return "bg-gray-500"
    }
  }

  return (
    <Dialog
      open={!!pendingRequest}
      onOpenChange={(open) => {
        if (!open && !isLoading) {
          setPendingRequest(null)
        }
      }}
    >
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle>Manual Match Request</DialogTitle>
            {pendingRequest && (
              <Badge
                className={`${getRequestTypeBadgeColor(pendingRequest.request_type)} text-white`}
              >
                {getRequestTypeLabel(pendingRequest.request_type)}
              </Badge>
            )}
          </div>
          <DialogDescription>
            {pendingRequest?.requester_display_name} wants to{" "}
            {pendingRequest?.request_type === "create"
              ? "add a manual match"
              : pendingRequest?.request_type === "edit"
                ? "edit a match result"
                : "delete a match"}{" "}
            ({timeRemaining} remaining)
          </DialogDescription>
        </DialogHeader>

        {pendingRequest && (
          <div className="py-4 space-y-4">
            {pendingRequest.request_type === "create" && (
              <>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Your team:</span>
                    <p className="font-medium">
                      {pendingRequest.responder_team_name}
                    </p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Their team:</span>
                    <p className="font-medium">
                      {pendingRequest.requester_team_name}
                    </p>
                  </div>
                </div>
                <div className="flex justify-center items-center p-3 bg-muted rounded-lg">
                  <span className="text-2xl font-mono font-bold">
                    {pendingRequest.responder_score} -{" "}
                    {pendingRequest.requester_score}
                  </span>
                </div>
                {pendingRequest.rating_difference !== undefined && (
                  <div className="text-center text-sm text-muted-foreground">
                    Rating difference: {pendingRequest.rating_difference}
                  </div>
                )}
              </>
            )}

            {pendingRequest.request_type === "edit" && (
              <>
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Current score:</p>
                  <div className="flex justify-center items-center p-2 bg-muted rounded-lg">
                    <span className="text-lg font-mono">
                      {pendingRequest.current_responder_score} -{" "}
                      {pendingRequest.current_requester_score}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">
                    Proposed new score:
                  </p>
                  <div className="flex justify-center items-center p-3 bg-muted rounded-lg">
                    <span className="text-2xl font-mono font-bold">
                      {pendingRequest.new_responder_score} -{" "}
                      {pendingRequest.new_requester_score}
                    </span>
                  </div>
                </div>
              </>
            )}

            {pendingRequest.request_type === "delete" && (
              <div className="text-center p-4 bg-red-50 dark:bg-red-950 rounded-lg">
                <p className="text-red-600 dark:text-red-400">
                  This will permanently delete the match record and reverse all
                  stats.
                </p>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={handleDecline}
            disabled={isLoading}
          >
            {declineMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Decline
          </Button>
          <Button
            onClick={handleAccept}
            disabled={isLoading}
            variant={
              pendingRequest?.request_type === "delete"
                ? "destructive"
                : "default"
            }
          >
            {acceptMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Accept
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
