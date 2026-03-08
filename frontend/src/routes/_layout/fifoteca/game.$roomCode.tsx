import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Loader2, WifiOff } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import {
  type FifaLeaguePublic,
  type FifaTeamPublic,
  FifotecaService,
} from "@/client"
import { MutualSuperspinDialog } from "@/components/fifoteca/MutualSuperspinDialog"
import { SuperspinRequestDialog } from "@/components/fifoteca/SuperspinRequestDialog"
import { RatingComparison } from "@/components/fifoteca/RatingComparison"
import { SpinDisplay } from "@/components/fifoteca/SpinDisplay"
import { TeamCard } from "@/components/fifoteca/TeamCard"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import useCustomToast from "@/hooks/useCustomToast"
import useFifotecaPlayer from "@/hooks/useFifotecaPlayer"
import useGameRoom, { type WSMessage } from "@/hooks/useGameRoom"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_layout/fifoteca/game/$roomCode")({
  component: FifotecaGamePage,
  head: () => ({
    meta: [
      {
        title: "Game - Fifoteca",
      },
    ],
  }),
})

// Spin animation state — only tracks whether the slot is currently animating.
// The actual selected value always comes from the React Query cache (source of truth).

function FifotecaGamePage() {
  const { roomCode } = Route.useParams()
  const normalizedRoomCode = roomCode.trim().toUpperCase()
  const navigate = useNavigate()
  const { showErrorToast } = useCustomToast()

  // Ref to track if we've already navigated to match page
  const navigatedToMatchRef = useRef(false)
  // Ref to track if we've already handled room expiry
  const handledExpiryRef = useRef(false)

  // Player profile
  const { player: currentPlayer, isLoading: playerLoading } =
    useFifotecaPlayer()

  // Animation state for spin displays (local UI state — spinning flag only)
  const [myLeagueSpinning, setMyLeagueSpinning] = useState(false)
  const [myTeamSpinning, setMyTeamSpinning] = useState(false)
  const [opponentLeagueSpinning, setOpponentLeagueSpinning] = useState(false)
  const [opponentTeamSpinning, setOpponentTeamSpinning] = useState(false)

  // Mutual superspin dialog state
  const [mutualSuperspinDialogOpen, setMutualSuperspinDialogOpen] =
    useState(false)

  // Superspin request dialog state
  const [superspinRequestDialogOpen, setSuperspinRequestDialogOpen] =
    useState(false)

  // Timer refs for animation cleanup
  const myLeagueTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const myTeamTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const opponentLeagueTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  )
  const opponentTeamTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  )

  // Clear all animation timers
  const clearAllTimers = useCallback(() => {
    if (myLeagueTimerRef.current) clearTimeout(myLeagueTimerRef.current)
    if (myTeamTimerRef.current) clearTimeout(myTeamTimerRef.current)
    if (opponentLeagueTimerRef.current)
      clearTimeout(opponentLeagueTimerRef.current)
    if (opponentTeamTimerRef.current) clearTimeout(opponentTeamTimerRef.current)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => clearAllTimers()
  }, [clearAllTimers])

  // Ref to keep player ID current for the WS callback
  const myPlayerIdRef = useRef(currentPlayer?.id)
  myPlayerIdRef.current = currentPlayer?.id

  // Handle all WS messages via callback (fires for every message, no batching).
  // This avoids the lastJsonMessage batching issue where rapid back-to-back
  // messages (e.g. spin_result + turn_changed) can be collapsed into a single
  // React render, causing the spin_result to be skipped entirely.
  const onWsMessage = useCallback((message: WSMessage) => {
    const currentPlayerId = myPlayerIdRef.current

    if (message.type === "spin_result") {
      const payload = message.payload as {
        player_id: string
        type: "league" | "team"
      }

      const isMySpin = payload.player_id === currentPlayerId
      const duration = 3200 // Animation duration in ms

      if (payload.type === "league") {
        if (isMySpin) {
          setMyLeagueSpinning(true)
          myLeagueTimerRef.current = setTimeout(() => {
            setMyLeagueSpinning(false)
          }, duration)
        } else {
          setOpponentLeagueSpinning(true)
          opponentLeagueTimerRef.current = setTimeout(() => {
            setOpponentLeagueSpinning(false)
          }, duration)
        }
      } else if (payload.type === "team") {
        if (isMySpin) {
          setMyTeamSpinning(true)
          myTeamTimerRef.current = setTimeout(() => {
            setMyTeamSpinning(false)
          }, duration)
        } else {
          setOpponentTeamSpinning(true)
          opponentTeamTimerRef.current = setTimeout(() => {
            setOpponentTeamSpinning(false)
          }, duration)
        }
      }
    }

    if (message.type === "mutual_superspin_proposed") {
      const payload = message.payload as { proposer_id: string }
      if (payload.proposer_id !== currentPlayerId) {
        setMutualSuperspinDialogOpen(true)
      }
    }

    if (
      message.type === "mutual_superspin_accepted" ||
      message.type === "mutual_superspin_declined"
    ) {
      setMutualSuperspinDialogOpen(false)
    }

    if (message.type === "superspin_request_proposed") {
      const payload = message.payload as { proposer_id: string }
      if (payload.proposer_id !== currentPlayerId) {
        setSuperspinRequestDialogOpen(true)
      }
    }

    if (
      message.type === "superspin_request_accepted" ||
      message.type === "superspin_request_declined"
    ) {
      setSuperspinRequestDialogOpen(false)
    }
  }, [])

  // WebSocket connection
  const {
    sendAction,
    isConnected,
    gameState,
    readyState,
    isReconnecting,
    isRoomExpired,
  } = useGameRoom(normalizedRoomCode, onWsMessage)

  // Fetch all leagues for SpinDisplay
  const { data: leagues = [], isLoading: leaguesLoading } = useQuery({
    queryKey: ["fifoteca", "leagues"],
    queryFn: () => FifotecaService.readLeagues(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  // Derived state from game snapshot
  const room = gameState?.room
  const playerStates = gameState?.player_states

  // Determine my player ID and opponent player ID
  const myPlayerId = currentPlayer?.id
  const opponentPlayerId = useMemo(() => {
    if (!room || !myPlayerId) return null
    return room.player1_id === myPlayerId ? room.player2_id : room.player1_id
  }, [room, myPlayerId])

  // Get player states
  const myState = useMemo(
    () => playerStates?.find((s) => s.player_id === myPlayerId),
    [playerStates, myPlayerId],
  )
  const opponentState = useMemo(
    () => playerStates?.find((s) => s.player_id === opponentPlayerId),
    [playerStates, opponentPlayerId],
  )

  // Is it my turn?
  const isMyTurn = room?.current_turn_player_id === myPlayerId

  // Phase detection
  const isLeaguePhase = room?.status === "SPINNING_LEAGUES"
  const isTeamPhase = room?.status === "SPINNING_TEAMS"
  const isSpinPhase = isLeaguePhase || isTeamPhase
  const isRatingReview = room?.status === "RATING_REVIEW"

  // Fetch teams for each player's selected league
  const { data: myTeams = [] } = useQuery({
    queryKey: ["fifoteca", "league-teams", myState?.current_league_id],
    queryFn: () =>
      FifotecaService.readLeagueTeams({ id: myState!.current_league_id! }),
    enabled: !!myState?.current_league_id,
    staleTime: 5 * 60 * 1000,
  })

  // Resolve selected league/team objects from game state (enriched by backend)
  const mySelectedLeague = useMemo(
    () =>
      myState?.current_league
        ? ({
            id: myState.current_league.id,
            name: myState.current_league.name,
            country: myState.current_league.country,
          } as FifaLeaguePublic)
        : null,
    [myState?.current_league],
  )
  const opponentSelectedLeague = useMemo(
    () =>
      opponentState?.current_league
        ? ({
            id: opponentState.current_league.id,
            name: opponentState.current_league.name,
            country: opponentState.current_league.country,
          } as FifaLeaguePublic)
        : null,
    [opponentState?.current_league],
  )

  const mySelectedTeam = useMemo(
    () =>
      myState?.current_team
        ? ({
            id: myState.current_team.id,
            name: myState.current_team.name,
            league_id: myState.current_team.league_id,
            attack_rating: myState.current_team.attack_rating,
            midfield_rating: myState.current_team.midfield_rating,
            defense_rating: myState.current_team.defense_rating,
            overall_rating: myState.current_team.overall_rating,
          } as FifaTeamPublic)
        : null,
    [myState?.current_team],
  )
  const opponentSelectedTeam = useMemo(
    () =>
      opponentState?.current_team
        ? ({
            id: opponentState.current_team.id,
            name: opponentState.current_team.name,
            league_id: opponentState.current_team.league_id,
            attack_rating: opponentState.current_team.attack_rating,
            midfield_rating: opponentState.current_team.midfield_rating,
            defense_rating: opponentState.current_team.defense_rating,
            overall_rating: opponentState.current_team.overall_rating,
          } as FifaTeamPublic)
        : null,
    [opponentState?.current_team],
  )

  // Close dialog when leaving spin phases
  useEffect(() => {
    if (!isSpinPhase && mutualSuperspinDialogOpen) {
      setMutualSuperspinDialogOpen(false)
    }
  }, [isSpinPhase, mutualSuperspinDialogOpen])

  // Navigate to match page when room enters match-related phases
  useEffect(() => {
    if (!room || !room.match_id) return

    const matchStatuses = ["MATCH_IN_PROGRESS", "SCORE_SUBMITTED", "COMPLETED"]
    if (matchStatuses.includes(room.status) && !navigatedToMatchRef.current) {
      navigatedToMatchRef.current = true
      navigate({
        to: "/fifoteca/match/$matchId",
        params: { matchId: room.match_id },
        search: { roomCode: normalizedRoomCode },
      })
    }
  }, [room, navigate, normalizedRoomCode])

  // Handle room expiry - show toast and redirect to home
  useEffect(() => {
    if (isRoomExpired && !handledExpiryRef.current) {
      handledExpiryRef.current = true
      showErrorToast("This room has expired")
      navigate({ to: "/fifoteca" })
    }
  }, [isRoomExpired, navigate, showErrorToast])

  // Action handlers
  const handleSpinLeague = useCallback(() => {
    if (!isConnected || !isMyTurn) return
    sendAction("spin_league", {})
  }, [isConnected, isMyTurn, sendAction])

  const handleLockLeague = useCallback(() => {
    if (!isConnected || !isMyTurn || !myState?.current_league_id) return
    sendAction("lock_league", {})
  }, [isConnected, isMyTurn, myState?.current_league_id, sendAction])

  const handleSpinTeam = useCallback(() => {
    if (!isConnected || !isMyTurn) return
    sendAction("spin_team", {})
  }, [isConnected, isMyTurn, sendAction])

  const handleLockTeam = useCallback(() => {
    if (!isConnected || !isMyTurn || !myState?.current_team_id) return
    sendAction("lock_team", {})
  }, [isConnected, isMyTurn, myState?.current_team_id, sendAction])

  // Special spin action handlers
  const handleUseSuperspin = useCallback(() => {
    if (!isConnected) return
    sendAction("use_superspin", {})
  }, [isConnected, sendAction])

  const handleUseParitySpin = useCallback(() => {
    if (!isConnected) return
    sendAction("use_parity_spin", {})
  }, [isConnected, sendAction])

  const handleReadyToPlay = useCallback(() => {
    if (!isConnected) return
    sendAction("ready_to_play", {})
  }, [isConnected, sendAction])

  const handleProposeMutualSuperspin = useCallback(() => {
    if (!isConnected) return
    sendAction("propose_mutual_superspin", {})
  }, [isConnected, sendAction])

  const handleAcceptMutualSuperspin = useCallback(() => {
    sendAction("accept_mutual_superspin", {})
    setMutualSuperspinDialogOpen(false)
  }, [sendAction])

  const handleDeclineMutualSuperspin = useCallback(() => {
    sendAction("decline_mutual_superspin", {})
    setMutualSuperspinDialogOpen(false)
  }, [sendAction])

  const handleProposeSuperspinRequest = useCallback(() => {
    if (!isConnected) return
    sendAction("propose_superspin_request", {})
  }, [isConnected, sendAction])

  const handleAcceptSuperspinRequest = useCallback(() => {
    sendAction("accept_superspin_request", {})
    setSuperspinRequestDialogOpen(false)
  }, [sendAction])

  const handleDeclineSuperspinRequest = useCallback(() => {
    sendAction("decline_superspin_request", {})
    setSuperspinRequestDialogOpen(false)
  }, [sendAction])

  // Convert leagues to SpinDisplay items format
  const leagueItems = useMemo(
    () => leagues.map((l) => ({ id: l.id, name: l.name })),
    [leagues],
  )

  // Convert teams to SpinDisplay items format
  const myTeamItems = useMemo(
    () => myTeams.map((t) => ({ id: t.id, name: t.name })),
    [myTeams],
  )
  // Opponent team items: empty since we don't need to animate their spins
  // with the full list — the selectedOverride from WS handles the display
  const opponentTeamItems = useMemo(
    () => [] as { id: string; name: string }[],
    [],
  )

  // Selected items always come from the React Query cache (source of truth).
  // No local override — this prevents stale selectedOverride from masking
  // correct cache values.

  // Connection status display
  const connectionStatus = useMemo(() => {
    switch (readyState) {
      case 1: // OPEN
        return { text: "Connected", variant: "default" as const }
      case 0: // CONNECTING
        return { text: "Connecting...", variant: "secondary" as const }
      case 2: // CLOSING
      case 3: // CLOSED
        return { text: "Disconnected", variant: "destructive" as const }
      default:
        return { text: "Unknown", variant: "outline" as const }
    }
  }, [readyState])

  // Rating review data
  const ratingReview = gameState?.rating_review
  const canUseParitySpin =
    ratingReview?.parity_available_to_id === myPlayerId &&
    myState &&
    !myState.parity_spin_used
  const canUseSuperspin =
    isRatingReview &&
    myState &&
    myState.has_superspin &&
    !myState.superspin_used

  // Player display names
  const myDisplayName = currentPlayer?.display_name ?? "You"
  const opponentDisplayName = opponentState?.display_name ?? "Opponent"

  // Determine which team in rating review is mine (p1/p2 follow player_states DB order, not "me vs opponent")
  const myTeamIsP1 = room?.player1_id === myPlayerId

  // Loading states
  if (playerLoading || leaguesLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // No game state yet
  if (!gameState) {
    return (
      <div className="flex flex-col gap-6 items-center justify-center min-h-[50vh]">
        <p className="text-muted-foreground">Waiting for game state...</p>
        <Badge variant={connectionStatus.variant}>
          {connectionStatus.text}
        </Badge>
      </div>
    )
  }

  // Rating Review phase
  if (isRatingReview) {
    return (
      <div className="flex flex-col gap-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Rating Review</h1>
            <p className="text-muted-foreground">
              Room: <span className="font-mono">{normalizedRoomCode}</span>
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-center">
            <Badge variant={connectionStatus.variant}>
              {connectionStatus.text}
            </Badge>
            {myState?.has_superspin && !myState?.superspin_used && (
              <Badge variant="default" className="bg-amber-500">
                Your Superspin
              </Badge>
            )}
            {opponentState?.has_superspin && !opponentState?.superspin_used && (
              <Badge
                variant="secondary"
                className="border-amber-500 text-amber-500"
              >
                Opponent Superspin
              </Badge>
            )}
          </div>
        </div>

        {/* Rating Comparison */}
        {ratingReview && (
          <RatingComparison
            team1={ratingReview.p1_team}
            team1Label={myTeamIsP1 ? myDisplayName : opponentDisplayName}
            team2={ratingReview.p2_team}
            team2Label={myTeamIsP1 ? opponentDisplayName : myDisplayName}
            difference={ratingReview.difference}
            protectionAwardedToId={ratingReview.protection_awarded_to_id}
            superspinAvailableToId={
              ratingReview.superspin_available_to_id ?? null
            }
            myPlayerId={myPlayerId}
          />
        )}

        {/* Action buttons */}
        <div className="flex flex-col gap-3">
          {canUseSuperspin && (
            <Button
              variant="default"
              className="w-full bg-amber-500 hover:bg-amber-600"
              onClick={handleUseSuperspin}
              disabled={!isConnected}
            >
              Use Superspin (±5 rating)
            </Button>
          )}
          {canUseParitySpin && (
            <Button
              variant="outline"
              onClick={handleUseParitySpin}
              disabled={!isConnected}
              className="w-full"
            >
              Use Parity Spin
            </Button>
          )}
          <Button
            onClick={handleReadyToPlay}
            disabled={!isConnected}
            className="w-full"
          >
            Ready to Play
          </Button>
          {!myState?.has_superspin && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleProposeSuperspinRequest}
              disabled={
                !isConnected ||
                room?.superspin_request_proposer_id != null
              }
              className="w-full text-muted-foreground"
            >
              Request Superspin
            </Button>
          )}
        </div>

        {/* Mutual Superspin Dialog */}
        <MutualSuperspinDialog
          open={mutualSuperspinDialogOpen}
          proposerName="Opponent"
          onAccept={handleAcceptMutualSuperspin}
          onDecline={handleDeclineMutualSuperspin}
          onOpenChange={setMutualSuperspinDialogOpen}
        />

        {/* Superspin Request Dialog */}
        <SuperspinRequestDialog
          open={superspinRequestDialogOpen}
          proposerName={opponentDisplayName}
          onAccept={handleAcceptSuperspinRequest}
          onDecline={handleDeclineSuperspinRequest}
          onOpenChange={setSuperspinRequestDialogOpen}
        />
      </div>
    )
  }

  // Not in spin phase - show status
  if (!isSpinPhase) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Fifoteca</h1>
            <p className="text-muted-foreground">
              Room: <span className="font-mono">{normalizedRoomCode}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={connectionStatus.variant}>
              {connectionStatus.text}
            </Badge>
          </div>
        </div>
        <Card>
          <CardContent className="py-8">
            <p className="text-center text-lg text-muted-foreground">
              {room?.status === "MATCH_IN_PROGRESS" && "Match in progress..."}
              {room?.status === "COMPLETED" && "Game completed!"}
              {room?.status === "WAITING" && "Waiting for opponent..."}
              {!room?.status && "Unknown game state"}
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Spin Phase</h1>
          <p className="text-muted-foreground">
            Room: <span className="font-mono">{normalizedRoomCode}</span>
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-center">
          <Badge variant={connectionStatus.variant}>
            {connectionStatus.text}
          </Badge>
          <Badge variant={isMyTurn ? "default" : "secondary"}>
            {isMyTurn ? "Your turn" : "Opponent's turn"}
          </Badge>
          {myState?.has_superspin && !myState?.superspin_used && (
            <Badge variant="default" className="bg-amber-500">
              Your Superspin
            </Badge>
          )}
          {opponentState?.has_superspin && !opponentState?.superspin_used && (
            <Badge
              variant="secondary"
              className="border-amber-500 text-amber-500"
            >
              Opponent Superspin
            </Badge>
          )}
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* My panel */}
        <PlayerPanel
          title={myDisplayName}
          isPlayer
          leagueItems={leagueItems}
          teamItems={myTeamItems}
          leagueSpinning={myLeagueSpinning}
          teamSpinning={myTeamSpinning}
          selectedLeague={mySelectedLeague}
          selectedTeam={mySelectedTeam}
          playerState={myState}
          isLeaguePhase={isLeaguePhase}
          isTeamPhase={isTeamPhase}
          isMyTurn={isMyTurn}
          isConnected={isConnected}
          onSpinLeague={handleSpinLeague}
          onLockLeague={handleLockLeague}
          onSpinTeam={handleSpinTeam}
          onLockTeam={handleLockTeam}
        />

        {/* Opponent panel */}
        <PlayerPanel
          title={opponentDisplayName}
          isPlayer={false}
          leagueItems={leagueItems}
          teamItems={opponentTeamItems}
          leagueSpinning={opponentLeagueSpinning}
          teamSpinning={opponentTeamSpinning}
          selectedLeague={opponentSelectedLeague}
          selectedTeam={opponentSelectedTeam}
          playerState={opponentState}
          isLeaguePhase={isLeaguePhase}
          isTeamPhase={isTeamPhase}
          isMyTurn={false}
          isConnected={isConnected}
          onSpinLeague={() => {}}
          onLockLeague={() => {}}
          onSpinTeam={() => {}}
          onLockTeam={() => {}}
        />
      </div>

      {/* Special spin actions */}
      {canUseSuperspin && (
        <div className="flex justify-center">
          <Button
            variant="default"
            className="bg-amber-500 hover:bg-amber-600"
            onClick={handleUseSuperspin}
            disabled={!isConnected || !isMyTurn}
          >
            Use Superspin (±5 rating)
          </Button>
        </div>
      )}

      {/* Propose Mutual Superspin - available during spin phases */}
      {isSpinPhase && (
        <div className="flex justify-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleProposeMutualSuperspin}
            disabled={!isConnected}
            className="text-muted-foreground"
          >
            Propose Mutual Superspin
          </Button>
          {!myState?.has_superspin && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleProposeSuperspinRequest}
              disabled={
                !isConnected ||
                room?.superspin_request_proposer_id != null
              }
              className="text-muted-foreground"
            >
              Request Superspin
            </Button>
          )}
        </div>
      )}

      {/* Mutual Superspin Dialog */}
      <MutualSuperspinDialog
        open={mutualSuperspinDialogOpen}
        proposerName="Opponent"
        onAccept={handleAcceptMutualSuperspin}
        onDecline={handleDeclineMutualSuperspin}
        onOpenChange={setMutualSuperspinDialogOpen}
      />

      {/* Superspin Request Dialog */}
      <SuperspinRequestDialog
        open={superspinRequestDialogOpen}
        proposerName={opponentDisplayName}
        onAccept={handleAcceptSuperspinRequest}
        onDecline={handleDeclineSuperspinRequest}
        onOpenChange={setSuperspinRequestDialogOpen}
      />
    </div>
  )
}

// Player panel component
interface PlayerPanelProps {
  title: string
  isPlayer: boolean
  leagueItems: Array<{ id: string; name: string }>
  teamItems: Array<{ id: string; name: string }>
  leagueSpinning: boolean
  teamSpinning: boolean
  selectedLeague: FifaLeaguePublic | null
  selectedTeam: FifaTeamPublic | null
  playerState?: {
    league_spins_remaining: number
    team_spins_remaining: number
    league_locked: boolean
    team_locked: boolean
    current_league_id: string | null
    current_team_id: string | null
  } | null
  isLeaguePhase: boolean
  isTeamPhase: boolean
  isMyTurn: boolean
  isConnected: boolean
  onSpinLeague: () => void
  onLockLeague: () => void
  onSpinTeam: () => void
  onLockTeam: () => void
}

function PlayerPanel({
  title,
  isPlayer,
  leagueItems,
  teamItems,
  leagueSpinning,
  teamSpinning,
  selectedLeague,
  selectedTeam,
  playerState,
  isLeaguePhase,
  isTeamPhase,
  isMyTurn,
  isConnected,
  onSpinLeague,
  onLockLeague,
  onSpinTeam,
  onLockTeam,
}: PlayerPanelProps) {
  const leagueLocked = playerState?.league_locked ?? false
  const teamLocked = playerState?.team_locked ?? false
  const leagueSpinsRemaining = playerState?.league_spins_remaining ?? 0
  const teamSpinsRemaining = playerState?.team_spins_remaining ?? 0
  const hasLeagueSelection = !!playerState?.current_league_id
  const hasTeamSelection = !!playerState?.current_team_id

  // Can spin/lock in current phase?
  const canAct = isMyTurn && isConnected

  // League phase buttons
  const canSpinLeague =
    canAct && isLeaguePhase && !leagueLocked && leagueSpinsRemaining > 0
  const canLockLeague =
    canAct && isLeaguePhase && !leagueLocked && hasLeagueSelection

  // Team phase buttons
  const canSpinTeam =
    canAct && isTeamPhase && !teamLocked && teamSpinsRemaining > 0
  const canLockTeam = canAct && isTeamPhase && !teamLocked && hasTeamSelection

  return (
    <Card className={cn(isPlayer && "border-primary/50 bg-primary/5")}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{title}</CardTitle>
          {isPlayer && (
            <Badge variant="default" className="text-xs">
              You
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* League display */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">League</span>
            {!leagueLocked && isLeaguePhase && (
              <span className="text-xs text-muted-foreground">
                Spins: {leagueSpinsRemaining}
              </span>
            )}
            {leagueLocked && (
              <Badge variant="outline" className="text-xs">
                Locked
              </Badge>
            )}
          </div>
          {leagueItems.length > 0 ? (
            <SpinDisplay
              items={leagueItems}
              spinning={leagueSpinning}
              selectedItem={
                selectedLeague
                  ? { id: selectedLeague.id, name: selectedLeague.name }
                  : null
              }
              locked={leagueLocked}
              label="League"
            />
          ) : (
            <div className="text-sm text-muted-foreground">
              Loading leagues...
            </div>
          )}
        </div>

        {/* Team display - only show during team phase or when team is already locked */}
        {(isTeamPhase || teamLocked) && (
          <>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Team</span>
                {!teamLocked && isTeamPhase && (
                  <span className="text-xs text-muted-foreground">
                    Spins: {teamSpinsRemaining}
                  </span>
                )}
                {teamLocked && (
                  <Badge variant="outline" className="text-xs">
                    Locked
                  </Badge>
                )}
              </div>
              {teamItems.length > 0 || selectedTeam ? (
                <SpinDisplay
                  items={
                    teamItems.length > 0
                      ? teamItems
                      : selectedTeam
                        ? [{ id: selectedTeam.id, name: selectedTeam.name }]
                        : []
                  }
                  spinning={teamSpinning}
                  selectedItem={
                    selectedTeam
                      ? { id: selectedTeam.id, name: selectedTeam.name }
                      : null
                  }
                  locked={teamLocked}
                  label="Team"
                />
              ) : (
                <div className="text-sm text-muted-foreground">
                  Loading teams...
                </div>
              )}
            </div>

            {/* Show selected team card if team is selected */}
            {selectedTeam && !teamSpinning && (
              <TeamCard
                team={selectedTeam}
                leagueName={selectedLeague?.name}
                isPlayer={isPlayer}
              />
            )}
          </>
        )}

        {/* Action buttons (only for my panel) */}
        {isPlayer && isLeaguePhase && !leagueLocked && (
          <div className="flex gap-2 pt-2">
            <Button
              variant="outline"
              onClick={onSpinLeague}
              disabled={!canSpinLeague}
              className="flex-1"
            >
              Spin League
            </Button>
            <Button
              onClick={onLockLeague}
              disabled={!canLockLeague}
              className="flex-1"
            >
              Lock League
            </Button>
          </div>
        )}

        {isPlayer && isTeamPhase && !teamLocked && (
          <div className="flex gap-2 pt-2">
            <Button
              variant="outline"
              onClick={onSpinTeam}
              disabled={!canSpinTeam}
              className="flex-1"
            >
              Spin Team
            </Button>
            <Button
              onClick={onLockTeam}
              disabled={!canLockTeam}
              className="flex-1"
            >
              Lock Team
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
