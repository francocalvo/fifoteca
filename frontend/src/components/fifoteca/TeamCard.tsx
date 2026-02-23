import type { FifaTeamPublic } from "@/client/types.gen"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface TeamCardProps {
  /** Team data */
  team: FifaTeamPublic
  /** Optional league name for display */
  leagueName?: string
  /** Whether this card is for the current player */
  isPlayer?: boolean
  /** Additional CSS classes */
  className?: string
}

/**
 * TeamCard displays team information with ratings breakdown.
 * Shows team name, league (if provided), and ratings for ATT/MID/DEF/Overall.
 */
export function TeamCard({
  team,
  leagueName,
  isPlayer = false,
  className,
}: TeamCardProps) {
  const {
    name,
    attack_rating,
    midfield_rating,
    defense_rating,
    overall_rating,
  } = team

  const ratings = [
    { label: "ATT", value: attack_rating, color: "text-red-500" },
    { label: "MID", value: midfield_rating, color: "text-green-500" },
    { label: "DEF", value: defense_rating, color: "text-blue-500" },
  ]

  return (
    <Card
      className={cn(
        "transition-all duration-200",
        isPlayer && "border-primary/50 bg-primary/5",
        className,
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <CardTitle className="text-lg">{name}</CardTitle>
          {isPlayer && (
            <Badge variant="secondary" className="text-xs">
              You
            </Badge>
          )}
        </div>
        {leagueName && (
          <p className="text-sm text-muted-foreground">{leagueName}</p>
        )}
      </CardHeader>
      <CardContent>
        {/* Ratings row */}
        <div className="flex items-center justify-between">
          <div className="flex gap-3">
            {ratings.map(({ label, value, color }) => (
              <div key={label} className="text-center">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className={cn("font-semibold", color)}>{value}</div>
              </div>
            ))}
          </div>
          {/* Overall rating */}
          <div className="text-center">
            <div className="text-xs text-muted-foreground">OVR</div>
            <div className="text-xl font-bold text-primary">
              {overall_rating}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
