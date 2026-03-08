import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { FifotecaService } from "@/client"
import type { FifotecaMatchHistoryPublic } from "@/client"
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

interface EditMatchDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  match: FifotecaMatchHistoryPublic | null
}

export function EditMatchDialog({
  open,
  onOpenChange,
  match,
}: EditMatchDialogProps) {
  const queryClient = useQueryClient()

  const [myScore, setMyScore] = useState<string>("")
  const [opponentScore, setOpponentScore] = useState<string>("")

  // Reset form when match changes or dialog opens
  useEffect(() => {
    if (match && open) {
      setMyScore(match.my_score?.toString() ?? "")
      setOpponentScore(match.opponent_score?.toString() ?? "")
    }
  }, [match, open])

  const editMutation = useMutation({
    mutationFn: () =>
      FifotecaService.createEditRequest({
        requestBody: {
          match_id: match!.id,
          new_my_score: parseInt(myScore, 10),
          new_opponent_score: parseInt(opponentScore, 10),
        },
      }),
    onSuccess: () => {
      toast.success("Edit request sent", {
        description: `Waiting for ${match?.opponent_display_name} to accept.`,
      })
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      onOpenChange(false)
    },
    onError: (error: Error) => {
      toast.error("Failed to create edit request", {
        description: error.message,
      })
    },
  })

  const handleSubmit = useCallback(() => {
    if (myScore === "" || opponentScore === "") {
      toast.error("Please fill in both scores")
      return
    }
    editMutation.mutate()
  }, [myScore, opponentScore, editMutation])

  const hasChanged =
    match &&
    (parseInt(myScore, 10) !== match.my_score ||
      parseInt(opponentScore, 10) !== match.opponent_score)

  const isValid =
    myScore !== "" &&
    opponentScore !== "" &&
    parseInt(myScore, 10) >= 0 &&
    parseInt(opponentScore, 10) >= 0 &&
    hasChanged

  if (!match) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Edit Match Result</DialogTitle>
          <DialogDescription>
            Request a score change for this match against{" "}
            {match.opponent_display_name}. They will need to accept before the
            change takes effect.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Match Info */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Your team:</span>
              <p className="font-medium">{match.my_team_name}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Opponent team:</span>
              <p className="font-medium">{match.opponent_team_name}</p>
            </div>
          </div>

          {/* Current Score */}
          <div className="p-3 bg-muted rounded-lg text-center">
            <span className="text-xs text-muted-foreground">Current Score</span>
            <p className="text-lg font-mono font-medium">
              {match.my_score} - {match.opponent_score}
            </p>
          </div>

          {/* New Score Input */}
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="myScore">Your Score</Label>
              <Input
                id="myScore"
                type="number"
                min="0"
                value={myScore}
                onChange={(e) => setMyScore(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="opponentScore">Opponent Score</Label>
              <Input
                id="opponentScore"
                type="number"
                min="0"
                value={opponentScore}
                onChange={(e) => setOpponentScore(e.target.value)}
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || editMutation.isPending}
          >
            {editMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Send Edit Request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
