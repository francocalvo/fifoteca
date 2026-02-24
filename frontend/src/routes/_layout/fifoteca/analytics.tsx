import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { BarChart3, Users } from "lucide-react"
import { Suspense, useMemo, useState } from "react"

import { FifotecaService } from "@/client"
import {
  AnalyticsMatchHistory,
  H2HSummary,
  OpponentSelector,
  SpreadAnalytics,
} from "@/components/fifoteca"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  computeH2H,
  computeSpreadBuckets,
  filterByOpponent,
} from "@/lib/analytics"

export const Route = createFileRoute("/_layout/fifoteca/analytics")({
  component: AnalyticsPage,
  head: () => ({
    meta: [
      {
        title: "Analytics - Fifoteca",
      },
    ],
  }),
})

function getMatchesQueryOptions() {
  return {
    queryFn: () => FifotecaService.listMatches(),
    queryKey: ["fifoteca", "matches"],
  }
}

function getPlayersQueryOptions() {
  return {
    queryFn: () => FifotecaService.listPlayers(),
    queryKey: ["fifoteca", "players"],
  }
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-[200px] w-full rounded-lg" />
      <Skeleton className="h-[300px] w-full rounded-lg" />
      <Skeleton className="h-[300px] w-full rounded-lg" />
    </div>
  )
}

function AnalyticsContent({ opponentId }: { opponentId: string }) {
  const { data: matches } = useSuspenseQuery(getMatchesQueryOptions())
  const { data: players } = useSuspenseQuery(getPlayersQueryOptions())

  const opponentName = useMemo(
    () => players.find((p) => p.id === opponentId)?.display_name ?? "Opponent",
    [players, opponentId],
  )

  const filteredMatches = useMemo(
    () => filterByOpponent(matches.data, opponentId),
    [matches.data, opponentId],
  )

  const h2hStats = useMemo(() => computeH2H(filteredMatches), [filteredMatches])

  const spreadBuckets = useMemo(
    () => computeSpreadBuckets(filteredMatches),
    [filteredMatches],
  )

  if (filteredMatches.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <div className="rounded-full bg-muted p-4 mb-4">
            <Users className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">No matches yet</h3>
          <p className="text-muted-foreground">
            No matches played against {opponentName} yet.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <H2HSummary stats={h2hStats} opponentName={opponentName} />
      <AnalyticsMatchHistory matches={filteredMatches} />
      <SpreadAnalytics buckets={spreadBuckets} />
    </div>
  )
}

function AnalyticsPage() {
  const [selectedOpponentId, setSelectedOpponentId] = useState<
    string | undefined
  >(undefined)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <BarChart3 className="h-6 w-6" />
          Analytics
        </h1>
        <p className="text-muted-foreground">
          Select an opponent to view head-to-head statistics
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <OpponentSelector
            value={selectedOpponentId}
            onChange={setSelectedOpponentId}
          />
        </CardHeader>
      </Card>

      {selectedOpponentId ? (
        <Suspense fallback={<AnalyticsSkeleton />}>
          <AnalyticsContent opponentId={selectedOpponentId} />
        </Suspense>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="rounded-full bg-muted p-4 mb-4">
              <Users className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">Select an opponent</h3>
            <p className="text-muted-foreground">
              Choose an opponent to view head-to-head statistics, match history,
              and spread analytics.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
