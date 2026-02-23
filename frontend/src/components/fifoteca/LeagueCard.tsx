import { Globe } from "lucide-react"
import type { FifaLeaguePublic } from "@/client/types.gen"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface LeagueCardProps {
  /** League data */
  league: FifaLeaguePublic
  /** Whether this card is locked/selected */
  locked?: boolean
  /** Optional label for the display */
  label?: string
  /** Additional CSS classes */
  className?: string
}

/**
 * LeagueCard displays league information.
 * Shows league name and country with optional locked state.
 */
export function LeagueCard({
  league,
  locked = false,
  label,
  className,
}: LeagueCardProps) {
  const { name, country } = league

  return (
    <Card
      className={cn(
        "transition-all duration-300",
        locked && "bg-muted/50 border-primary/50",
        className,
      )}
    >
      {label && (
        <div className="px-4 pt-4">
          <span className="text-sm font-medium text-muted-foreground">
            {label}
          </span>
        </div>
      )}
      <CardContent className={cn("py-6", label && "pt-2")}>
        <div className="flex items-center gap-3">
          <Globe
            className={cn(
              "h-5 w-5 text-muted-foreground",
              locked && "text-primary",
            )}
          />
          <div>
            <div
              className={cn("font-semibold text-lg", locked && "text-primary")}
            >
              {name}
            </div>
            <div className="text-sm text-muted-foreground">{country}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
