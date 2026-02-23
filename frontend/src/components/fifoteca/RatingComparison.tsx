import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface TeamInfo {
  id: string
  name: string
  overall_rating: number
  attack_rating?: number
  midfield_rating?: number
  defense_rating?: number
  league_id?: string
}

interface RatingComparisonProps {
  /** Player 1's team (the current user's team if player1) */
  team1: TeamInfo | null | undefined
  /** Display name for player 1 */
  team1Label?: string
  /** Player 2's team (the opponent's team) */
  team2: TeamInfo | null | undefined
  /** Display name for player 2 */
  team2Label?: string
  /** The rating difference between teams */
  difference: number
  /** ID of the player who gets protection (if any) */
  protectionAwardedToId: string | null
  /** ID of the player who has superspin available (if any) */
  superspinAvailableToId: string | null
  /** The current player's ID */
  myPlayerId: string | undefined
}

/**
 * RatingComparison displays a side-by-side comparison of both teams' ratings
 * with color-coded difference indicator and protection status.
 */
export function RatingComparison({
  team1,
  team1Label,
  team2,
  team2Label,
  difference,
  protectionAwardedToId,
  superspinAvailableToId,
  myPlayerId,
}: RatingComparisonProps) {
  // Determine if the current player gets protection
  const iGetProtection = protectionAwardedToId === myPlayerId
  const opponentGetsProtection =
    protectionAwardedToId && protectionAwardedToId !== myPlayerId

  // Color coding based on difference thresholds
  const getDifferenceColor = (diff: number) => {
    const absDiff = Math.abs(diff)
    if (absDiff < 5) return "text-green-500"
    if (absDiff < 30) return "text-yellow-500"
    return "text-red-500"
  }

  // Format the difference with sign
  const formatDifference = (diff: number) => {
    if (diff > 0) return `+${diff}`
    if (diff < 0) return `${diff}`
    return "0"
  }

  const differenceColor = getDifferenceColor(difference)

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Rating Comparison</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Team comparison */}
        <div className="grid grid-cols-3 gap-4 items-center">
          {/* Team 1 */}
          <div className="text-center">
            {team1Label && (
              <p className="text-xs text-muted-foreground mb-1">{team1Label}</p>
            )}
            {team1 ? (
              <>
                <p className="font-medium truncate">{team1.name}</p>
                <p className="text-2xl font-bold text-primary">
                  {team1.overall_rating}
                </p>
              </>
            ) : (
              <p className="text-muted-foreground">Loading...</p>
            )}
          </div>

          {/* Difference */}
          <div className="text-center">
            <p className="text-sm text-muted-foreground mb-1">Difference</p>
            <p className={cn("text-2xl font-bold", differenceColor)}>
              {formatDifference(difference)}
            </p>
          </div>

          {/* Team 2 */}
          <div className="text-center">
            {team2Label && (
              <p className="text-xs text-muted-foreground mb-1">{team2Label}</p>
            )}
            {team2 ? (
              <>
                <p className="font-medium truncate">{team2.name}</p>
                <p className="text-2xl font-bold text-primary">
                  {team2.overall_rating}
                </p>
              </>
            ) : (
              <p className="text-muted-foreground">Loading...</p>
            )}
          </div>
        </div>

        {/* Superspin available */}
        {superspinAvailableToId && (
          <div className="pt-2 border-t">
            <div className="flex items-center justify-center gap-2">
              <Badge variant="default" className="bg-amber-500">
                Superspin Available
              </Badge>
              <span className="text-sm text-muted-foreground">
                {superspinAvailableToId === myPlayerId
                  ? "You have superspin for the next round"
                  : "Opponent has superspin for the next round"}
              </span>
            </div>
          </div>
        )}

        {/* Protection status */}
        {protectionAwardedToId && (
          <div className="pt-2 border-t">
            {iGetProtection ? (
              <div className="flex items-center justify-center gap-2">
                <Badge variant="default" className="bg-green-500">
                  Protection Active
                </Badge>
                <span className="text-sm text-muted-foreground">
                  You get protection for next game
                </span>
              </div>
            ) : opponentGetsProtection ? (
              <div className="flex items-center justify-center gap-2">
                <Badge variant="secondary">Opponent Protected</Badge>
                <span className="text-sm text-muted-foreground">
                  Opponent gets protection for next game
                </span>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
