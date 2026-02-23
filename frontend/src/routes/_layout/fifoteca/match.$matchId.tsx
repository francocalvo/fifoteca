import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Loader2 } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"
import { z } from "zod"

import { type FifaTeamPublic, FifotecaService } from "@/client"
import { RatingComparison } from "@/components/fifoteca/RatingComparison"
import { ScoreInput } from "@/components/fifoteca/ScoreInput"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import useFifotecaPlayer from "@/hooks/useFifotecaPlayer"
import useGameRoom from "@/hooks/useGameRoom"

// Search params validation
const searchSchema = z.object({
  roomCode: z.string().optional(),
})

export const Route = createFileRoute("/_layout/fifoteca/match/$matchId")({
  component: FifotecaMatchPage,
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      {
        title: "Match - Fifoteca",
      },
    ],
  }),
})

function FifotecaMatchPage() {
  const { matchId } = Route.useParams()
  const { roomCode } = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Ref to track if we've already navigated
  const navigatedRef = useRef(false)

  // Current player
  const { player: currentPlayer, isLoading: playerLoading } =
    useFifotecaPlayer()

  // WebSocket connection (only if roomCode is provided)
  const { sendAction, isConnected, lastMessage, readyState } =
    useGameRoom(roomCode)

  // Fetch match details
  const {
    data: match,
    isLoading: matchLoading,
    refetch: refetchMatch,
  } = useQuery({
    queryKey: ["fifoteca", "match", matchId],
    queryFn: () => FifotecaService.getMatch({ id: matchId }),
    refetchOnWindowFocus: false,
  })

  // Fetch teams for both players' leagues
  const { data: p1Teams = [] } = useQuery({
    queryKey: ["fifoteca", "teams", match?.player1_league_id],
    queryFn: () =>
      FifotecaService.readTeams({ leagueId: match?.player1_league_id }),
    enabled: !!match?.player1_league_id,
  })

  const { data: p2Teams = [] } = useQuery({
    queryKey: ["fifoteca", "teams", match?.player2_league_id],
    queryFn: () =>
      FifotecaService.readTeams({ leagueId: match?.player2_league_id }),
    enabled: !!match?.player2_league_id,
  })

  // Resolve team objects
  const p1Team = p1Teams.find((t) => t.id === match?.player1_team_id) as
    | FifaTeamPublic
    | undefined
  const p2Team = p2Teams.find((t) => t.id === match?.player2_team_id) as
    | FifaTeamPublic
    | undefined

  // Derived state
  const myPlayerId = currentPlayer?.id
  const isPlayer1 = match?.player1_id === myPlayerId
  const isSubmittedByMe = match?.submitted_by_id === myPlayerId
  const hasScoresSubmitted =
    match?.player1_score !== null && match?.player2_score !== null
  const isConfirmed = match?.confirmed
  const isAwaitingConfirmation = hasScoresSubmitted && !isConfirmed

  // Play again state
  const [playAgainRequested, setPlayAgainRequested] = useState(false)

  // WebSocket event handling
  useEffect(() => {
    if (!lastMessage) return

    // Refetch match on score_submitted or match_result
    if (
      lastMessage.type === "score_submitted" ||
      lastMessage.type === "match_result"
    ) {
      refetchMatch()
      // Invalidate player profile to get updated stats
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "player", "me"],
      })
    }

    // Handle play_again_ack - show waiting for opponent
    if (lastMessage.type === "play_again_ack") {
      setPlayAgainRequested(true)
    }

    // Handle state_sync - navigate back to game when room resets
    if (lastMessage.type === "state_sync" && roomCode) {
      const snapshot = lastMessage.payload as {
        room: { status: string; code: string }
      }
      if (
        snapshot.room.status === "SPINNING_LEAGUES" &&
        !navigatedRef.current
      ) {
        navigatedRef.current = true
        navigate({
          to: "/fifoteca/game/$roomCode",
          params: { roomCode: snapshot.room.code },
        })
      }
    }
  }, [lastMessage, refetchMatch, queryClient, roomCode, navigate])

  // Score submission mutation
  const submitScoreMutation = useMutation({
    mutationFn: (scores: { player1Score: number; player2Score: number }) =>
      FifotecaService.submitMatchScore({
        id: matchId,
        requestBody: {
          player1_score: scores.player1Score,
          player2_score: scores.player2Score,
        },
      }),
    onSuccess: () => {
      refetchMatch()
    },
  })

  // Score confirmation mutation
  const confirmMutation = useMutation({
    mutationFn: () => FifotecaService.confirmMatchResult({ id: matchId }),
    onSuccess: () => {
      refetchMatch()
      // Invalidate player profile to get updated stats
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "player", "me"],
      })
    },
  })

  // Action handlers
  const handleSubmitScore = useCallback(
    (player1Score: number, player2Score: number) => {
      submitScoreMutation.mutate({ player1Score, player2Score })
    },
    [submitScoreMutation],
  )

  const handleConfirm = useCallback(() => {
    confirmMutation.mutate()
  }, [confirmMutation])

  const handlePlayAgain = useCallback(() => {
    if (!isConnected || !roomCode) return
    sendAction("play_again", {})
    setPlayAgainRequested(true)
  }, [isConnected, roomCode, sendAction])

  const handleExit = useCallback(() => {
    // Try to send leave_room if connected
    if (isConnected && roomCode) {
      sendAction("leave_room", {})
    }
    // Navigate to home regardless
    navigate({ to: "/fifoteca" })
  }, [isConnected, roomCode, sendAction, navigate])

  // Connection status
  const connectionStatus = (() => {
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
  })()

  // Determine winner for confirmed matches
  const getResult = () => {
    if (
      !match ||
      !isConfirmed ||
      match.player1_score === null ||
      match.player2_score === null
    ) {
      return null
    }

    const p1Score = match.player1_score
    const p2Score = match.player2_score

    if (p1Score > p2Score) {
      return { winner: "player1" as const, isDraw: false }
    }
    if (p2Score > p1Score) {
      return { winner: "player2" as const, isDraw: false }
    }
    return { winner: null, isDraw: true }
  }

  const result = getResult()
  const iWon =
    result && !result.isDraw
      ? (result.winner === "player1" && isPlayer1) ||
        (result.winner === "player2" && !isPlayer1)
      : false

  // Loading states
  if (playerLoading || matchLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!match) {
    return (
      <div className="flex flex-col gap-6 items-center justify-center min-h-[50vh]">
        <p className="text-muted-foreground">Match not found</p>
        <Button onClick={() => navigate({ to: "/fifoteca" })}>
          Back to Home
        </Button>
      </div>
    )
  }

  // Render team comparison data for RatingComparison component
  const team1Info = p1Team
    ? {
        id: p1Team.id,
        name: p1Team.name,
        overall_rating: p1Team.overall_rating,
        attack_rating: p1Team.attack_rating,
        midfield_rating: p1Team.midfield_rating,
        defense_rating: p1Team.defense_rating,
      }
    : null

  const team2Info = p2Team
    ? {
        id: p2Team.id,
        name: p2Team.name,
        overall_rating: p2Team.overall_rating,
        attack_rating: p2Team.attack_rating,
        midfield_rating: p2Team.midfield_rating,
        defense_rating: p2Team.defense_rating,
      }
    : null

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Match</h1>
          <p className="text-muted-foreground">
            Round {match.round_number}
            {roomCode && (
              <span className="ml-2">
                Room: <span className="font-mono">{roomCode}</span>
              </span>
            )}
          </p>
        </div>
        {roomCode && (
          <div className="flex items-center gap-2">
            <Badge variant={connectionStatus.variant}>
              {connectionStatus.text}
            </Badge>
          </div>
        )}
      </div>

      {/* Team Comparison */}
      <RatingComparison
        team1={team1Info}
        team2={team2Info}
        difference={match.rating_difference}
        protectionAwardedToId={match.protection_awarded_to_id}
        superspinAvailableToId={null}
        myPlayerId={myPlayerId}
      />

      {/* State A: No scores submitted yet - show ScoreInput */}
      {!hasScoresSubmitted && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Enter Match Score</CardTitle>
          </CardHeader>
          <CardContent>
            <ScoreInput
              team1Name={team1Info?.name ?? "Player 1"}
              team2Name={team2Info?.name ?? "Player 2"}
              onSubmit={handleSubmitScore}
              isSubmitting={submitScoreMutation.isPending}
            />
          </CardContent>
        </Card>
      )}

      {/* State B: Scores submitted by opponent, awaiting my confirmation */}
      {isAwaitingConfirmation && !isSubmittedByMe && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Confirm Score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Proposed scores */}
            <div className="grid grid-cols-3 gap-4 items-center">
              <div className="text-center">
                <p className="text-sm text-muted-foreground">
                  {team1Info?.name ?? "Player 1"}
                </p>
                <p className="text-3xl font-bold">{match.player1_score}</p>
              </div>
              <div className="text-center text-muted-foreground">vs</div>
              <div className="text-center">
                <p className="text-sm text-muted-foreground">
                  {team2Info?.name ?? "Player 2"}
                </p>
                <p className="text-3xl font-bold">{match.player2_score}</p>
              </div>
            </div>

            <Button
              onClick={handleConfirm}
              className="w-full"
              disabled={confirmMutation.isPending}
            >
              {confirmMutation.isPending ? "Confirming..." : "Confirm Score"}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* State C: Scores submitted by me, waiting for opponent */}
      {isAwaitingConfirmation && isSubmittedByMe && (
        <Card>
          <CardContent className="py-6">
            <div className="text-center space-y-4">
              <p className="text-lg text-muted-foreground">
                Waiting for opponent to confirm...
              </p>
              <div className="grid grid-cols-3 gap-4 items-center">
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">
                    {team1Info?.name ?? "Player 1"}
                  </p>
                  <p className="text-3xl font-bold">{match.player1_score}</p>
                </div>
                <div className="text-center text-muted-foreground">vs</div>
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">
                    {team2Info?.name ?? "Player 2"}
                  </p>
                  <p className="text-3xl font-bold">{match.player2_score}</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* State D: Match confirmed - show result */}
      {isConfirmed && result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Match Result</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Result badge */}
            <div className="flex justify-center">
              {result.isDraw ? (
                <Badge variant="secondary" className="text-lg py-1 px-4">
                  Draw
                </Badge>
              ) : iWon ? (
                <Badge
                  variant="default"
                  className="text-lg py-1 px-4 bg-green-500"
                >
                  You Won!
                </Badge>
              ) : (
                <Badge variant="destructive" className="text-lg py-1 px-4">
                  You Lost
                </Badge>
              )}
            </div>

            {/* Final scores */}
            <div className="grid grid-cols-3 gap-4 items-center">
              <div className="text-center">
                <p className="text-sm text-muted-foreground">
                  {team1Info?.name ?? "Player 1"}
                </p>
                <p className="text-3xl font-bold">{match.player1_score}</p>
              </div>
              <div className="text-center text-muted-foreground">vs</div>
              <div className="text-center">
                <p className="text-sm text-muted-foreground">
                  {team2Info?.name ?? "Player 2"}
                </p>
                <p className="text-3xl font-bold">{match.player2_score}</p>
              </div>
            </div>

            {/* Player stats */}
            {currentPlayer && (
              <div className="pt-4 border-t">
                <p className="text-sm text-muted-foreground text-center mb-2">
                  Your Stats
                </p>
                <div className="flex justify-center gap-4">
                  <Badge variant="default" className="bg-green-500">
                    W: {currentPlayer.total_wins}
                  </Badge>
                  <Badge variant="destructive">
                    L: {currentPlayer.total_losses}
                  </Badge>
                  <Badge variant="secondary">
                    D: {currentPlayer.total_draws}
                  </Badge>
                </div>
              </div>
            )}

            {/* Post-match actions */}
            <div className="flex gap-3 pt-4">
              {roomCode ? (
                <>
                  <Button
                    variant="outline"
                    onClick={handlePlayAgain}
                    disabled={!isConnected || playAgainRequested}
                    className="flex-1"
                  >
                    {playAgainRequested
                      ? "Waiting for opponent..."
                      : "Play Again"}
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleExit}
                    className="flex-1"
                  >
                    Exit
                  </Button>
                </>
              ) : (
                <Button
                  onClick={() => navigate({ to: "/fifoteca" })}
                  className="w-full"
                >
                  Back to Home
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
