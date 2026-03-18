import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { FifotecaService } from "@/client"
import type { FifaLeaguePublic, FifaTeamPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface ManualMatchDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  opponentId: string
  opponentName: string
}

export function ManualMatchDialog({
  open,
  onOpenChange,
  opponentId,
  opponentName,
}: ManualMatchDialogProps) {
  const queryClient = useQueryClient()

  const [myLeagueId, setMyLeagueId] = useState<string>("")
  const [opponentLeagueId, setOpponentLeagueId] = useState<string>("")
  const [myTeamId, setMyTeamId] = useState<string>("")
  const [opponentTeamId, setOpponentTeamId] = useState<string>("")
  const [myScore, setMyScore] = useState<string>("")
  const [opponentScore, setOpponentScore] = useState<string>("")
  const [playedAt, setPlayedAt] = useState<string>("")

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setMyLeagueId("")
      setOpponentLeagueId("")
      setMyTeamId("")
      setOpponentTeamId("")
      setMyScore("")
      setOpponentScore("")
      setPlayedAt("")
    }
  }, [open])

  // Fetch leagues
  const { data: leagues } = useQuery({
    queryKey: ["fifoteca", "leagues"],
    queryFn: () => FifotecaService.readLeagues(),
    enabled: open,
  })

  // Fetch teams for my league
  const { data: myTeams } = useQuery({
    queryKey: ["fifoteca", "teams", myLeagueId],
    queryFn: () =>
      FifotecaService.readTeams({ leagueId: myLeagueId || undefined }),
    enabled: open && !!myLeagueId,
  })

  // Fetch teams for opponent league
  const { data: opponentTeams } = useQuery({
    queryKey: ["fifoteca", "teams", opponentLeagueId],
    queryFn: () =>
      FifotecaService.readTeams({ leagueId: opponentLeagueId || undefined }),
    enabled: open && !!opponentLeagueId,
  })

  // Get selected team objects
  const myTeam = useMemo(
    () => myTeams?.find((t) => t.id === myTeamId),
    [myTeams, myTeamId],
  )
  const opponentTeam = useMemo(
    () => opponentTeams?.find((t) => t.id === opponentTeamId),
    [opponentTeams, opponentTeamId],
  )

  // Calculate rating difference
  const ratingDifference = useMemo(() => {
    if (!myTeam || !opponentTeam) return null
    return Math.abs(myTeam.overall_rating - opponentTeam.overall_rating)
  }, [myTeam, opponentTeam])

  // Mutation for creating request
  const createMutation = useMutation({
    mutationFn: () =>
      FifotecaService.createManualMatchRequest({
        requestBody: {
          opponent_id: opponentId,
          my_team_id: myTeamId,
          opponent_team_id: opponentTeamId,
          my_score: parseInt(myScore, 10),
          opponent_score: parseInt(opponentScore, 10),
          played_at: playedAt
            ? new Date(playedAt + "T12:00:00").toISOString()
            : null,
        },
      }),
    onSuccess: () => {
      toast.success("Manual match request sent", {
        description: `Waiting for ${opponentName} to accept.`,
      })
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      onOpenChange(false)
    },
    onError: (error: Error) => {
      toast.error("Failed to create request", {
        description: error.message,
      })
    },
  })

  const handleSubmit = useCallback(() => {
    if (!myTeamId || !opponentTeamId || myScore === "" || opponentScore === "") {
      toast.error("Please fill in all fields")
      return
    }
    createMutation.mutate()
  }, [myTeamId, opponentTeamId, myScore, opponentScore, createMutation])

  const isValid =
    myTeamId &&
    opponentTeamId &&
    myScore !== "" &&
    opponentScore !== "" &&
    parseInt(myScore, 10) >= 0 &&
    parseInt(opponentScore, 10) >= 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Add Manual Match</DialogTitle>
          <DialogDescription>
            Create a match record against {opponentName}. They will need to
            accept before it&apos;s added.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Date */}
          <div className="grid gap-2">
            <Label htmlFor="playedAt">Date Played</Label>
            <Input
              id="playedAt"
              type="date"
              value={playedAt}
              onChange={(e) => setPlayedAt(e.target.value)}
            />
          </div>

          {/* Your League + Team */}
          <div className="grid gap-2">
            <Label>Your League</Label>
            <Select
              value={myLeagueId}
              onValueChange={(val) => {
                setMyLeagueId(val)
                setMyTeamId("")
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a league" />
              </SelectTrigger>
              <SelectContent>
                {leagues?.map((league: FifaLeaguePublic) => (
                  <SelectItem key={league.id} value={league.id}>
                    {league.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {myLeagueId && (
            <div className="grid gap-2">
              <Label>Your Team</Label>
              <Select value={myTeamId} onValueChange={setMyTeamId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select team" />
                </SelectTrigger>
                <SelectContent>
                  {myTeams?.map((team: FifaTeamPublic) => (
                    <SelectItem key={team.id} value={team.id}>
                      {team.name} ({team.overall_rating})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Opponent League + Team */}
          <div className="grid gap-2">
            <Label>{opponentName}&apos;s League</Label>
            <Select
              value={opponentLeagueId}
              onValueChange={(val) => {
                setOpponentLeagueId(val)
                setOpponentTeamId("")
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a league" />
              </SelectTrigger>
              <SelectContent>
                {leagues?.map((league: FifaLeaguePublic) => (
                  <SelectItem key={league.id} value={league.id}>
                    {league.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {opponentLeagueId && (
            <div className="grid gap-2">
              <Label>{opponentName}&apos;s Team</Label>
              <Select value={opponentTeamId} onValueChange={setOpponentTeamId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select team" />
                </SelectTrigger>
                <SelectContent>
                  {opponentTeams?.map((team: FifaTeamPublic) => (
                    <SelectItem key={team.id} value={team.id}>
                      {team.name} ({team.overall_rating})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Rating Difference */}
          {ratingDifference !== null && (
            <div className="flex items-center justify-center p-3 bg-muted rounded-lg">
              <span className="text-sm text-muted-foreground mr-2">
                Rating Difference:
              </span>
              <span
                className={`font-semibold ${
                  ratingDifference === 0
                    ? "text-muted-foreground"
                    : ratingDifference < 5
                      ? "text-green-600"
                      : ratingDifference < 15
                        ? "text-yellow-600"
                        : "text-red-600"
                }`}
              >
                {ratingDifference}
              </span>
            </div>
          )}

          {/* Score Input */}
          {myTeamId && opponentTeamId && (
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="myScore">Your Score</Label>
                <Input
                  id="myScore"
                  type="number"
                  min="0"
                  value={myScore}
                  onChange={(e) => setMyScore(e.target.value)}
                  placeholder="0"
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="opponentScore">{opponentName}&apos;s Score</Label>
                <Input
                  id="opponentScore"
                  type="number"
                  min="0"
                  value={opponentScore}
                  onChange={(e) => setOpponentScore(e.target.value)}
                  placeholder="0"
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || createMutation.isPending}
          >
            {createMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Send Request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
