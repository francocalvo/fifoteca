import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import type { ColumnDef } from "@tanstack/react-table"
import { History, Minus, Trophy } from "lucide-react"
import { Suspense } from "react"

import { type FifotecaMatchHistoryPublic, FifotecaService } from "@/client"
import { DataTable } from "@/components/Common/DataTable"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// Date formatting helper
function formatDate(dateString: string | null): string {
  if (!dateString) return "-"
  const date = new Date(dateString)
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function getPlayerQueryOptions() {
  return {
    queryFn: () => FifotecaService.createOrGetPlayerProfile(),
    queryKey: ["fifoteca", "player", "me"],
  }
}

function getMatchesQueryOptions() {
  return {
    queryFn: () => FifotecaService.listMatches(),
    queryKey: ["fifoteca", "matches"],
  }
}

export const Route = createFileRoute("/_layout/fifoteca/history")({
  component: FifotecaHistoryPage,
  head: () => ({
    meta: [
      {
        title: "History - Fifoteca",
      },
    ],
  }),
})

// W/L/D badge component
function ResultBadge({ result }: { result: string }) {
  switch (result) {
    case "win":
      return (
        <Badge className="bg-green-500 hover:bg-green-600 text-white">W</Badge>
      )
    case "loss":
      return <Badge className="bg-red-500 hover:bg-red-600 text-white">L</Badge>
    case "draw":
      return (
        <Badge className="bg-yellow-500 hover:bg-yellow-600 text-white">
          D
        </Badge>
      )
    default:
      return <Badge variant="secondary">-</Badge>
  }
}

// Rating difference display
function RatingDifference({ diff }: { diff: number }) {
  if (diff === 0) return <span className="text-muted-foreground">0</span>
  if (diff > 0) return <span className="text-green-600">+{diff}</span>
  return <span className="text-red-600">{diff}</span>
}

// Stats header component
function StatsHeader() {
  const { data: player } = useSuspenseQuery(getPlayerQueryOptions())

  const { total_wins, total_losses, total_draws } = player
  const totalGames = total_wins + total_losses + total_draws
  const winPercentage =
    totalGames > 0 ? Math.round((total_wins / totalGames) * 100) : 0

  return (
    <div className="grid gap-4 md:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Wins</CardTitle>
          <Trophy className="h-4 w-4 text-green-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-600">{total_wins}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Losses</CardTitle>
          <Minus className="h-4 w-4 text-red-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-red-600">{total_losses}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Draws</CardTitle>
          <Minus className="h-4 w-4 text-yellow-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-yellow-600">
            {total_draws}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Win Rate</CardTitle>
          <Trophy className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{winPercentage}%</div>
        </CardContent>
      </Card>
    </div>
  )
}

// Table columns definition
const columns: ColumnDef<FifotecaMatchHistoryPublic>[] = [
  {
    accessorKey: "created_at",
    header: "Date",
    cell: ({ row }) => formatDate(row.getValue("created_at") as string | null),
  },
  {
    accessorKey: "opponent_display_name",
    header: "Opponent",
    cell: ({ row }) => (
      <span className="font-medium">
        {row.getValue("opponent_display_name") as string}
      </span>
    ),
  },
  {
    id: "teams",
    header: "Teams",
    cell: ({ row }) => {
      const myTeam = row.original.my_team_name
      const opponentTeam = row.original.opponent_team_name
      return (
        <span className="text-sm">
          <span className="font-medium">{myTeam}</span>
          <span className="text-muted-foreground mx-2">vs</span>
          <span>{opponentTeam}</span>
        </span>
      )
    },
  },
  {
    id: "score",
    header: "Score",
    cell: ({ row }) => {
      const myScore = row.original.my_score
      const opponentScore = row.original.opponent_score
      if (myScore === null || opponentScore === null) {
        return <span className="text-muted-foreground">-</span>
      }
      return (
        <span className="font-mono">
          {myScore} - {opponentScore}
        </span>
      )
    },
  },
  {
    accessorKey: "result",
    header: "Result",
    cell: ({ row }) => (
      <ResultBadge result={row.getValue("result") as string} />
    ),
  },
  {
    accessorKey: "rating_difference",
    header: "Rating",
    cell: ({ row }) => (
      <RatingDifference diff={row.getValue("rating_difference") as number} />
    ),
  },
]

// Match list content
function MatchListContent() {
  const { data: matches } = useSuspenseQuery(getMatchesQueryOptions())

  if (matches.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center text-center py-12">
        <div className="rounded-full bg-muted p-4 mb-4">
          <History className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">No matches yet</h3>
        <p className="text-muted-foreground">
          Play some matches to see your history here
        </p>
      </div>
    )
  }

  return <DataTable columns={columns} data={matches.data} />
}

// Match list with suspense
function MatchList() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-12">
          <div className="animate-pulse text-muted-foreground">
            Loading matches...
          </div>
        </div>
      }
    >
      <MatchListContent />
    </Suspense>
  )
}

// Stats with suspense
function Stats() {
  return (
    <Suspense
      fallback={
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <div className="h-4 w-16 bg-muted animate-pulse rounded" />
              </CardHeader>
              <CardContent>
                <div className="h-8 w-12 bg-muted animate-pulse rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
      }
    >
      <StatsHeader />
    </Suspense>
  )
}

function FifotecaHistoryPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Match History</h1>
        <p className="text-muted-foreground">
          View your past matches and statistics
        </p>
      </div>

      {/* Stats summary */}
      <Stats />

      {/* Match list */}
      <Card>
        <CardHeader>
          <CardTitle>Matches</CardTitle>
        </CardHeader>
        <CardContent>
          <MatchList />
        </CardContent>
      </Card>
    </div>
  )
}
