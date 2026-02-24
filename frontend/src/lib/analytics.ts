import type { FifotecaMatchHistoryPublic } from "@/client"

export type Role = "favorite" | "underdog" | "even"
export type ResultType = "W" | "L" | "D"

export interface H2HStats {
  totalMatches: number
  wins: number
  losses: number
  draws: number
  winRate: number
  winsAsFavorite: number
  lossesAsFavorite: number
  drawsAsFavorite: number
  winsAsUnderdog: number
  lossesAsUnderdog: number
  drawsAsUnderdog: number
  currentStreak: { count: number; type: ResultType }
  avgRatingDiff: number
  avgScoreDiff: number
  recentForm: ResultType[]
}

export interface SpreadBucket {
  label: string
  range: [number, number]
  favoriteWinPct: number
  drawPct: number
  underdogWinPct: number
  sampleSize: number
}

const BUCKETS: { label: string; range: [number, number] }[] = [
  { label: "0-4", range: [0, 4] },
  { label: "5-9", range: [5, 9] },
  { label: "10-19", range: [10, 19] },
  { label: "20-29", range: [20, 29] },
  { label: "30+", range: [30, Infinity] },
]

export function filterByOpponent(
  matches: FifotecaMatchHistoryPublic[],
  opponentId: string,
): FifotecaMatchHistoryPublic[] {
  return matches.filter((m) => m.opponent_id === opponentId)
}

export function getRole(match: FifotecaMatchHistoryPublic): Role {
  if (match.my_team_rating > match.opponent_team_rating) return "favorite"
  if (match.my_team_rating < match.opponent_team_rating) return "underdog"
  return "even"
}

function resultToType(result: string): ResultType {
  if (result === "win") return "W"
  if (result === "loss") return "L"
  return "D"
}

export function computeH2H(matches: FifotecaMatchHistoryPublic[]): H2HStats {
  const totalMatches = matches.length
  let wins = 0
  let losses = 0
  let draws = 0
  let winsAsFavorite = 0
  let lossesAsFavorite = 0
  let drawsAsFavorite = 0
  let winsAsUnderdog = 0
  let lossesAsUnderdog = 0
  let drawsAsUnderdog = 0
  let totalRatingDiff = 0
  let totalScoreDiff = 0

  for (const m of matches) {
    const role = getRole(m)
    const r = m.result

    if (r === "win") wins++
    else if (r === "loss") losses++
    else draws++

    if (role === "favorite") {
      if (r === "win") winsAsFavorite++
      else if (r === "loss") lossesAsFavorite++
      else drawsAsFavorite++
    } else if (role === "underdog") {
      if (r === "win") winsAsUnderdog++
      else if (r === "loss") lossesAsUnderdog++
      else drawsAsUnderdog++
    }

    totalRatingDiff += m.rating_difference
    if (m.my_score != null && m.opponent_score != null) {
      totalScoreDiff += Math.abs(m.my_score - m.opponent_score)
    }
  }

  // Streak: matches are already sorted by date desc, so index 0 is most recent
  let streakType: ResultType = "W"
  let streakCount = 0
  if (matches.length > 0) {
    streakType = resultToType(matches[0].result)
    streakCount = 1
    for (let i = 1; i < matches.length; i++) {
      if (resultToType(matches[i].result) === streakType) {
        streakCount++
      } else {
        break
      }
    }
  }

  // Recent form: last 10 matches (most recent first)
  const recentForm = matches.slice(0, 10).map((m) => resultToType(m.result))

  return {
    totalMatches,
    wins,
    losses,
    draws,
    winRate: totalMatches > 0 ? Math.round((wins / totalMatches) * 100) : 0,
    winsAsFavorite,
    lossesAsFavorite,
    drawsAsFavorite,
    winsAsUnderdog,
    lossesAsUnderdog,
    drawsAsUnderdog,
    currentStreak: { count: streakCount, type: streakType },
    avgRatingDiff:
      totalMatches > 0 ? Math.round(totalRatingDiff / totalMatches) : 0,
    avgScoreDiff:
      totalMatches > 0
        ? Math.round((totalScoreDiff / totalMatches) * 10) / 10
        : 0,
    recentForm,
  }
}

export function computeSpreadBuckets(
  matches: FifotecaMatchHistoryPublic[],
): SpreadBucket[] {
  return BUCKETS.map(({ label, range }) => {
    const bucket = matches.filter(
      (m) => m.rating_difference >= range[0] && m.rating_difference <= range[1],
    )
    const n = bucket.length

    if (n === 0) {
      return {
        label,
        range,
        favoriteWinPct: 0,
        drawPct: 0,
        underdogWinPct: 0,
        sampleSize: 0,
      }
    }

    let favWins = 0
    let drawCount = 0
    let underdogWins = 0

    for (const m of bucket) {
      const role = getRole(m)
      if (m.result === "draw") {
        drawCount++
      } else if (
        (role === "favorite" && m.result === "win") ||
        (role === "underdog" && m.result === "loss")
      ) {
        favWins++
      } else {
        underdogWins++
      }
    }

    return {
      label,
      range,
      favoriteWinPct: Math.round((favWins / n) * 100),
      drawPct: Math.round((drawCount / n) * 100),
      underdogWinPct: Math.round((underdogWins / n) * 100),
      sampleSize: n,
    }
  })
}
