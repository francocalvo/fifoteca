import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Check, Copy, Users, Wifi, WifiOff } from "lucide-react"
import { useEffect, useRef } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import useFifotecaPlayer from "@/hooks/useFifotecaPlayer"
import useGameRoom from "@/hooks/useGameRoom"

export const Route = createFileRoute("/_layout/fifoteca/lobby/$roomCode")({
  component: FifotecaLobbyPage,
  head: () => ({
    meta: [
      {
        title: "Lobby - Fifoteca",
      },
    ],
  }),
})

function FifotecaLobbyPage() {
  const { roomCode } = Route.useParams()
  const navigate = useNavigate()
  const { player } = useFifotecaPlayer()
  const [copiedText, copy] = useCopyToClipboard()
  const { showErrorToast } = useCustomToast()
  const hasNavigatedRef = useRef(false)
  const handledExpiryRef = useRef(false)

  // Normalize room code for display and cache consistency
  const normalizedRoomCode = roomCode.trim().toUpperCase()
  const isCopied = copiedText === normalizedRoomCode

  // Connect to WebSocket for real-time updates
  const { isConnected, gameState, lastMessage, isReconnecting, isRoomExpired } =
    useGameRoom(normalizedRoomCode)

  // Derive state from game snapshot
  const room = gameState?.room
  const hasPlayer2 = Boolean(room?.player2_id)
  const roomStatus = room?.status

  // Determine if this is Player 1 or Player 2 for the current user
  const isPlayer1 = room?.player1_id === player?.id
  const isPlayer2 = room?.player2_id === player?.id

  // Get opponent's player state for display (if available)
  const playerStates = gameState?.player_states || []
  const player1State = playerStates.find(
    (s) => s.player_id === room?.player1_id,
  )
  const player2State = playerStates.find(
    (s) => s.player_id === room?.player2_id,
  )

  // Auto-navigate to game when both players connected AND room is ready for spinning
  useEffect(() => {
    // Guard against multiple navigations
    if (hasNavigatedRef.current) return

    // Check conditions for auto-navigation
    const isReadyForGame =
      hasPlayer2 && roomStatus === "SPINNING_LEAGUES" && normalizedRoomCode

    if (isReadyForGame) {
      hasNavigatedRef.current = true
      navigate({
        to: "/fifoteca/game/$roomCode",
        params: { roomCode: normalizedRoomCode },
      })
    }
  }, [hasPlayer2, roomStatus, normalizedRoomCode, navigate])

  // Also navigate when we receive a player_connected message that indicates game is ready
  // This handles the race condition where message arrives before cache is fully updated
  useEffect(() => {
    if (hasNavigatedRef.current) return

    if (
      lastMessage?.type === "player_connected" &&
      roomStatus === "SPINNING_LEAGUES" &&
      hasPlayer2
    ) {
      hasNavigatedRef.current = true
      navigate({
        to: "/fifoteca/game/$roomCode",
        params: { roomCode: normalizedRoomCode },
      })
    }
  }, [lastMessage, roomStatus, hasPlayer2, normalizedRoomCode, navigate])

  // Handle room expiry - show toast and redirect to home
  useEffect(() => {
    if (isRoomExpired && !handledExpiryRef.current) {
      handledExpiryRef.current = true
      showErrorToast("This room has expired")
      navigate({ to: "/fifoteca" })
    }
  }, [isRoomExpired, navigate, showErrorToast])

  return (
    <div className="flex flex-col gap-6 max-w-md mx-auto">
      {/* Reconnecting banner */}
      {isReconnecting && (
        <Alert variant="destructive" className="animate-pulse">
          <WifiOff className="h-4 w-4" />
          <AlertDescription className="font-medium">
            Reconnecting...
          </AlertDescription>
        </Alert>
      )}

      {/* Header */}
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight">Game Lobby</h1>
        <p className="text-muted-foreground">
          Share the room code with your opponent
        </p>
      </div>

      {/* Room Code Card */}
      <Card>
        <CardHeader className="text-center">
          <CardTitle>Room Code</CardTitle>
          <CardDescription>
            Click to copy and share with your friend
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center gap-2">
            <span className="text-4xl font-mono font-bold tracking-widest">
              {normalizedRoomCode}
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => copy(normalizedRoomCode)}
              className="size-10"
            >
              {isCopied ? (
                <Check className="size-5 text-green-500" />
              ) : (
                <Copy className="size-5" />
              )}
              <span className="sr-only">Copy room code</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Connection Status */}
      <div className="flex items-center justify-center gap-2">
        {isConnected ? (
          <>
            <Wifi className="size-4 text-green-500" />
            <span className="text-sm text-muted-foreground">Connected</span>
          </>
        ) : (
          <>
            <WifiOff className="size-4 text-red-500" />
            <span className="text-sm text-muted-foreground">Connecting...</span>
          </>
        )}
      </div>

      {/* Players Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Users className="size-5" />
            <CardTitle>Players</CardTitle>
          </div>
          <CardDescription>
            {hasPlayer2
              ? "Both players connected! Game starting..."
              : "Waiting for opponent to join..."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3">
            {/* Player 1 - always shown */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-3">
                <div className="size-8 rounded-full bg-primary/10 flex items-center justify-center">
                  <span className="text-sm font-bold text-primary">P1</span>
                </div>
                <div>
                  <div className="font-medium">
                    {isPlayer1
                      ? "You"
                      : player1State?.player_id
                        ? `Player 1`
                        : "Player 1"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {isPlayer1 && "(Host)"}
                  </div>
                </div>
              </div>
              <Badge variant="secondary">Ready</Badge>
            </div>

            {/* Player 2 - or waiting */}
            {hasPlayer2 ? (
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted">
                <div className="flex items-center gap-3">
                  <div className="size-8 rounded-full bg-primary/10 flex items-center justify-center">
                    <span className="text-sm font-bold text-primary">P2</span>
                  </div>
                  <div>
                    <div className="font-medium">
                      {isPlayer2
                        ? "You"
                        : player2State?.player_id
                          ? "Player 2"
                          : "Player 2"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {!isPlayer1 && !isPlayer2 && "Opponent"}
                    </div>
                  </div>
                </div>
                <Badge variant="secondary">Ready</Badge>
              </div>
            ) : (
              <div className="flex items-center justify-between p-3 rounded-lg border-2 border-dashed border-muted-foreground/25">
                <div className="flex items-center gap-3">
                  <div className="size-8 rounded-full bg-muted flex items-center justify-center">
                    <span className="text-sm font-bold text-muted-foreground">
                      P2
                    </span>
                  </div>
                  <div className="text-muted-foreground">
                    Waiting for opponent...
                  </div>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Room Status */}
      {roomStatus && (
        <div className="text-center">
          <Badge variant="outline" className="font-mono text-xs">
            Status: {roomStatus}
          </Badge>
        </div>
      )}
    </div>
  )
}
