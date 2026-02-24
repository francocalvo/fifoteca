import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { H2HStats, ResultType } from "@/lib/analytics"

interface H2HSummaryProps {
  stats: H2HStats
  opponentName: string
}

function H2HBar({
  wins,
  losses,
  draws,
  total,
}: {
  wins: number
  losses: number
  draws: number
  total: number
}) {
  if (total === 0) return null
  const wPct = (wins / total) * 100
  const dPct = (draws / total) * 100
  const lPct = (losses / total) * 100

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-green-600 font-medium">{wins} W</span>
        <span className="text-yellow-600 font-medium">{draws} D</span>
        <span className="text-red-600 font-medium">{losses} L</span>
      </div>
      <div className="flex h-4 w-full overflow-hidden rounded-full">
        {wPct > 0 && (
          <div
            className="bg-green-500 transition-all"
            style={{ width: `${wPct}%` }}
          />
        )}
        {dPct > 0 && (
          <div
            className="bg-yellow-500 transition-all"
            style={{ width: `${dPct}%` }}
          />
        )}
        {lPct > 0 && (
          <div
            className="bg-red-500 transition-all"
            style={{ width: `${lPct}%` }}
          />
        )}
      </div>
    </div>
  )
}

function RecentForm({ form }: { form: ResultType[] }) {
  if (form.length === 0) return null

  const colorMap: Record<ResultType, string> = {
    W: "bg-green-500",
    L: "bg-red-500",
    D: "bg-yellow-500",
  }

  return (
    <div className="flex items-center gap-1">
      <span className="text-sm text-muted-foreground mr-1">Recent:</span>
      {form.map((r, i) => (
        <div
          key={i}
          className={`h-6 w-6 rounded-sm flex items-center justify-center text-xs font-bold text-white ${colorMap[r]}`}
        >
          {r}
        </div>
      ))}
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function formatRecord(w: number, d: number, l: number) {
  const total = w + d + l
  const rate = total > 0 ? Math.round((w / total) * 100) : 0
  return `${w}-${d}-${l} (${rate}%)`
}

export function H2HSummary({ stats, opponentName }: H2HSummaryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">You vs {opponentName}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <H2HBar
          wins={stats.wins}
          losses={stats.losses}
          draws={stats.draws}
          total={stats.totalMatches}
        />

        <div className="space-y-2">
          <StatRow
            label="Overall record"
            value={formatRecord(stats.wins, stats.draws, stats.losses)}
          />
          <StatRow
            label="As favorite"
            value={formatRecord(
              stats.winsAsFavorite,
              stats.drawsAsFavorite,
              stats.lossesAsFavorite,
            )}
          />
          <StatRow
            label="As underdog"
            value={formatRecord(
              stats.winsAsUnderdog,
              stats.drawsAsUnderdog,
              stats.lossesAsUnderdog,
            )}
          />
          <StatRow
            label="Current streak"
            value={`${stats.currentStreak.count}${stats.currentStreak.type}`}
          />
          <StatRow label="Avg rating diff" value={`${stats.avgRatingDiff}`} />
          <StatRow label="Avg score diff" value={`${stats.avgScoreDiff}`} />
        </div>

        <RecentForm form={stats.recentForm} />
      </CardContent>
    </Card>
  )
}
