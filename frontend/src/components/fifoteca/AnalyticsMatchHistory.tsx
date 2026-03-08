import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2, Pencil, Settings2, Trash2 } from "lucide-react"
import { useCallback, useMemo, useState } from "react"
import { toast } from "sonner"

import { FifotecaService } from "@/client"
import type { FifotecaMatchHistoryPublic } from "@/client"
import { EditMatchDialog } from "@/components/fifoteca/EditMatchDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { getRole } from "@/lib/analytics"

type SortKey =
  | "created_at"
  | "my_team_name"
  | "opponent_team_name"
  | "score"
  | "result"
  | "rating_difference"
type SortDir = "asc" | "desc"

function formatDate(dateString: string | null): string {
  if (!dateString) return "-"
  const date = new Date(dateString)
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

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

function RoleBadge({ match }: { match: FifotecaMatchHistoryPublic }) {
  const role = getRole(match)
  if (role === "favorite")
    return (
      <Badge variant="outline" className="text-green-600 border-green-300">
        Fav
      </Badge>
    )
  if (role === "underdog")
    return (
      <Badge variant="outline" className="text-red-600 border-red-300">
        Dog
      </Badge>
    )
  return (
    <Badge variant="outline" className="text-muted-foreground">
      Even
    </Badge>
  )
}

function getScoreDiff(m: FifotecaMatchHistoryPublic): number {
  if (m.my_score == null || m.opponent_score == null) return 0
  return m.my_score - m.opponent_score
}

function getResultOrder(result: string): number {
  if (result === "win") return 2
  if (result === "draw") return 1
  return 0
}

function SortHeader({
  label,
  sortKey,
  currentSort,
  currentDir,
  onSort,
}: {
  label: string
  sortKey: SortKey
  currentSort: SortKey
  currentDir: SortDir
  onSort: (key: SortKey) => void
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-3 h-8"
      onClick={() => onSort(sortKey)}
    >
      {label}
      {currentSort === sortKey ? (
        currentDir === "asc" ? (
          <ArrowUp className="ml-1 h-3 w-3" />
        ) : (
          <ArrowDown className="ml-1 h-3 w-3" />
        )
      ) : (
        <ArrowUpDown className="ml-1 h-3 w-3 opacity-50" />
      )}
    </Button>
  )
}

interface AnalyticsMatchHistoryProps {
  matches: FifotecaMatchHistoryPublic[]
}

export function AnalyticsMatchHistory({ matches }: AnalyticsMatchHistoryProps) {
  const queryClient = useQueryClient()
  const [sortKey, setSortKey] = useState<SortKey>("created_at")
  const [sortDir, setSortDir] = useState<SortDir>("desc")
  const [editMode, setEditMode] = useState(false)
  const [editingMatch, setEditingMatch] = useState<FifotecaMatchHistoryPublic | null>(null)
  const [deletingMatchId, setDeletingMatchId] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (matchId: string) =>
      FifotecaService.createDeleteRequest({
        requestBody: { match_id: matchId },
      }),
    onSuccess: (_, matchId) => {
      const match = matches.find((m) => m.id === matchId)
      toast.success("Delete request sent", {
        description: `Waiting for ${match?.opponent_display_name} to accept.`,
      })
      queryClient.invalidateQueries({
        queryKey: ["fifoteca", "manual-match-requests"],
      })
      setDeletingMatchId(null)
    },
    onError: (error: Error) => {
      toast.error("Failed to create delete request", {
        description: error.message,
      })
      setDeletingMatchId(null)
    },
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("desc")
    }
  }

  const handleEdit = useCallback((match: FifotecaMatchHistoryPublic) => {
    setEditingMatch(match)
  }, [])

  const handleDelete = useCallback(
    (matchId: string) => {
      setDeletingMatchId(matchId)
      deleteMutation.mutate(matchId)
    },
    [deleteMutation],
  )

  const sorted = useMemo(() => {
    const data = [...matches]
    const dir = sortDir === "asc" ? 1 : -1

    data.sort((a, b) => {
      switch (sortKey) {
        case "created_at":
          return dir * (a.created_at ?? "").localeCompare(b.created_at ?? "")
        case "my_team_name":
          return dir * a.my_team_name.localeCompare(b.my_team_name)
        case "opponent_team_name":
          return dir * a.opponent_team_name.localeCompare(b.opponent_team_name)
        case "score":
          return dir * (getScoreDiff(a) - getScoreDiff(b))
        case "result":
          return dir * (getResultOrder(a.result) - getResultOrder(b.result))
        case "rating_difference":
          return (
            dir *
            (a.my_team_rating -
              a.opponent_team_rating -
              (b.my_team_rating - b.opponent_team_rating))
          )
        default:
          return 0
      }
    })
    return data
  }, [matches, sortKey, sortDir])

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-lg">Match History</CardTitle>
          <Button
            variant={editMode ? "default" : "outline"}
            size="sm"
            onClick={() => setEditMode(!editMode)}
          >
            <Settings2 className="h-4 w-4 mr-1" />
            {editMode ? "Done" : "Edit"}
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>
                  <SortHeader
                    label="Date"
                    sortKey="created_at"
                    currentSort={sortKey}
                    currentDir={sortDir}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortHeader
                    label="My Team"
                    sortKey="my_team_name"
                    currentSort={sortKey}
                    currentDir={sortDir}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortHeader
                    label="Opp. Team"
                    sortKey="opponent_team_name"
                    currentSort={sortKey}
                    currentDir={sortDir}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortHeader
                    label="Score"
                    sortKey="score"
                    currentSort={sortKey}
                    currentDir={sortDir}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortHeader
                    label="Result"
                    sortKey="result"
                    currentSort={sortKey}
                    currentDir={sortDir}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortHeader
                    label="Rating Diff"
                    sortKey="rating_difference"
                    currentSort={sortKey}
                    currentDir={sortDir}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>Role</TableHead>
                {editMode && <TableHead className="w-[100px]">Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.length === 0 ? (
                <TableRow className="hover:bg-transparent">
                  <TableCell
                    colSpan={editMode ? 8 : 7}
                    className="h-32 text-center text-muted-foreground"
                  >
                    No matches found.
                  </TableCell>
                </TableRow>
              ) : (
                sorted.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{formatDate(m.created_at)}</TableCell>
                    <TableCell className="font-medium">
                      {m.my_team_name}
                    </TableCell>
                    <TableCell>{m.opponent_team_name}</TableCell>
                    <TableCell className="font-mono">
                      {m.my_score != null && m.opponent_score != null
                        ? `${m.my_score} - ${m.opponent_score}`
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <ResultBadge result={m.result} />
                    </TableCell>
                    <TableCell>
                      {(() => {
                        const signedDiff =
                          m.my_team_rating - m.opponent_team_rating
                        if (signedDiff > 0) {
                          return (
                            <span className="text-green-600">+{signedDiff}</span>
                          )
                        }
                        if (signedDiff < 0) {
                          return (
                            <span className="text-red-600">{signedDiff}</span>
                          )
                        }
                        return <span className="text-muted-foreground">0</span>
                      })()}
                    </TableCell>
                    <TableCell>
                      <RoleBadge match={m} />
                    </TableCell>
                    {editMode && (
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleEdit(m)}
                            title="Edit score"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-destructive hover:text-destructive"
                            onClick={() => handleDelete(m.id)}
                            disabled={deletingMatchId === m.id}
                            title="Delete match"
                          >
                            {deletingMatchId === m.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <EditMatchDialog
        open={!!editingMatch}
        onOpenChange={(open) => {
          if (!open) setEditingMatch(null)
        }}
        match={editingMatch}
      />
    </>
  )
}
