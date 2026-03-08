import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Clock, Loader2, Trash2, X } from "lucide-react"
import { useCallback } from "react"
import { toast } from "sonner"

import { FifotecaService } from "@/client"
import type { ManualMatchRequestPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"

function formatTimeRemaining(expiresAt: string): string {
  const expiry = new Date(expiresAt)
  const now = new Date()
  const diff = expiry.getTime() - now.getTime()

  if (diff <= 0) return "Expired"

  const hours = Math.floor(diff / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function getRequestTypeBadge(type: string) {
  switch (type) {
    case "create":
      return (
        <Badge className="bg-green-500 hover:bg-green-600 text-white">
          New Match
        </Badge>
      )
    case "edit":
      return (
        <Badge className="bg-yellow-500 hover:bg-yellow-600 text-white">
          Edit
        </Badge>
      )
    case "delete":
      return (
        <Badge className="bg-red-500 hover:bg-red-600 text-white">Delete</Badge>
      )
    default:
      return <Badge variant="secondary">{type}</Badge>
  }
}

interface RequestItemProps {
  request: ManualMatchRequestPublic
  isIncoming: boolean
  onAccept?: () => void
  onDecline?: () => void
  onCancel?: () => void
  isLoading?: boolean
}

function RequestItem({
  request,
  isIncoming,
  onAccept,
  onDecline,
  onCancel,
  isLoading,
}: RequestItemProps) {
  return (
    <div className="flex items-center justify-between py-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {getRequestTypeBadge(request.request_type)}
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatTimeRemaining(request.expires_at)}
          </span>
        </div>
        <p className="text-sm font-medium truncate">
          {isIncoming
            ? `From: ${request.requester_display_name}`
            : `To: ${request.responder_display_name}`}
        </p>
        {request.request_type === "create" && (
          <p className="text-xs text-muted-foreground">
            {request.requester_team_name} vs {request.responder_team_name} (
            {request.requester_score} - {request.responder_score})
          </p>
        )}
        {request.request_type === "edit" && (
          <p className="text-xs text-muted-foreground">
            {request.current_requester_score} - {request.current_responder_score}{" "}
            &rarr; {request.new_requester_score} - {request.new_responder_score}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1 ml-2">
        {isIncoming ? (
          <>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-100"
              onClick={onAccept}
              disabled={isLoading}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-100"
              onClick={onDecline}
              disabled={isLoading}
            >
              <X className="h-4 w-4" />
            </Button>
          </>
        ) : (
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={onCancel}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        )}
      </div>
    </div>
  )
}

export function PendingRequestsCard() {
  const queryClient = useQueryClient()

  const { data: requests, isLoading: isLoadingRequests } = useQuery({
    queryKey: ["fifoteca", "manual-match-requests"],
    queryFn: () => FifotecaService.listManualMatchRequests(),
    refetchInterval: 60000, // Refresh every minute to update time remaining
  })

  const acceptMutation = useMutation({
    mutationFn: (id: string) =>
      FifotecaService.acceptManualMatchRequest({ id }),
    onSuccess: () => {
      toast.success("Request accepted")
      queryClient.invalidateQueries({ queryKey: ["fifoteca", "matches"] })
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
    },
    onError: (error: Error) => {
      toast.error("Failed to accept", { description: error.message })
    },
  })

  const declineMutation = useMutation({
    mutationFn: (id: string) =>
      FifotecaService.declineManualMatchRequest({ id }),
    onSuccess: () => {
      toast.info("Request declined")
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
    },
    onError: (error: Error) => {
      toast.error("Failed to decline", { description: error.message })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (id: string) =>
      FifotecaService.cancelManualMatchRequest({ id }),
    onSuccess: () => {
      toast.info("Request cancelled")
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
    },
    onError: (error: Error) => {
      toast.error("Failed to cancel", { description: error.message })
    },
  })

  const handleAccept = useCallback(
    (id: string) => {
      acceptMutation.mutate(id)
    },
    [acceptMutation],
  )

  const handleDecline = useCallback(
    (id: string) => {
      declineMutation.mutate(id)
    },
    [declineMutation],
  )

  const handleCancel = useCallback(
    (id: string) => {
      cancelMutation.mutate(id)
    },
    [cancelMutation],
  )

  const hasRequests =
    (requests?.incoming?.length ?? 0) > 0 ||
    (requests?.outgoing?.length ?? 0) > 0

  if (isLoadingRequests) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Pending Requests</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!hasRequests) {
    return null
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          Pending Requests
          {hasRequests && (
            <Badge variant="secondary">
              {(requests?.incoming?.length ?? 0) +
                (requests?.outgoing?.length ?? 0)}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Incoming Requests */}
        {requests?.incoming && requests.incoming.length > 0 && (
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">
              Incoming ({requests.incoming.length})
            </p>
            <div className="divide-y">
              {requests.incoming.map((req) => (
                <RequestItem
                  key={req.id}
                  request={req}
                  isIncoming
                  onAccept={() => handleAccept(req.id)}
                  onDecline={() => handleDecline(req.id)}
                  isLoading={
                    acceptMutation.isPending || declineMutation.isPending
                  }
                />
              ))}
            </div>
          </div>
        )}

        {requests?.incoming &&
          requests.incoming.length > 0 &&
          requests?.outgoing &&
          requests.outgoing.length > 0 && <Separator />}

        {/* Outgoing Requests */}
        {requests?.outgoing && requests.outgoing.length > 0 && (
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-2">
              Outgoing ({requests.outgoing.length})
            </p>
            <div className="divide-y">
              {requests.outgoing.map((req) => (
                <RequestItem
                  key={req.id}
                  request={req}
                  isIncoming={false}
                  onCancel={() => handleCancel(req.id)}
                  isLoading={cancelMutation.isPending}
                />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
