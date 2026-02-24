import { describe, expect, it } from "vitest"
import type { FifotecaMatchHistoryPublic } from "@/client"
import {
  computeH2H,
  computeSpreadBuckets,
  filterByOpponent,
  getRole,
} from "./analytics"

function makeMatch(
  overrides: Partial<FifotecaMatchHistoryPublic> = {},
): FifotecaMatchHistoryPublic {
  return {
    id: crypto.randomUUID(),
    created_at: new Date().toISOString(),
    round_number: 1,
    rating_difference: 10,
    confirmed: true,
    opponent_id: "opp-1",
    opponent_display_name: "Opponent",
    my_team_name: "My Team",
    opponent_team_name: "Opp Team",
    my_team_rating: 250,
    opponent_team_rating: 240,
    my_score: 3,
    opponent_score: 1,
    result: "win",
    ...overrides,
  }
}

describe("filterByOpponent", () => {
  it("returns only matches against the given opponent", () => {
    const matches = [
      makeMatch({ opponent_id: "opp-1" }),
      makeMatch({ opponent_id: "opp-2" }),
      makeMatch({ opponent_id: "opp-1" }),
    ]
    const filtered = filterByOpponent(matches, "opp-1")
    expect(filtered).toHaveLength(2)
    expect(filtered.every((m) => m.opponent_id === "opp-1")).toBe(true)
  })

  it("returns empty array when no matches for opponent", () => {
    const matches = [makeMatch({ opponent_id: "opp-1" })]
    expect(filterByOpponent(matches, "opp-999")).toHaveLength(0)
  })
})

describe("getRole", () => {
  it("returns favorite when my_team_rating > opponent_team_rating", () => {
    expect(
      getRole(makeMatch({ my_team_rating: 260, opponent_team_rating: 240 })),
    ).toBe("favorite")
  })

  it("returns underdog when my_team_rating < opponent_team_rating", () => {
    expect(
      getRole(makeMatch({ my_team_rating: 230, opponent_team_rating: 240 })),
    ).toBe("underdog")
  })

  it("returns even when ratings are equal", () => {
    expect(
      getRole(makeMatch({ my_team_rating: 240, opponent_team_rating: 240 })),
    ).toBe("even")
  })
})

describe("computeH2H", () => {
  const matches = [
    // Most recent first (index 0 = newest)
    makeMatch({
      result: "win",
      my_team_rating: 260,
      opponent_team_rating: 240,
      rating_difference: 20,
      my_score: 3,
      opponent_score: 1,
    }),
    makeMatch({
      result: "win",
      my_team_rating: 260,
      opponent_team_rating: 240,
      rating_difference: 20,
      my_score: 2,
      opponent_score: 0,
    }),
    makeMatch({
      result: "loss",
      my_team_rating: 230,
      opponent_team_rating: 250,
      rating_difference: 20,
      my_score: 0,
      opponent_score: 2,
    }),
    makeMatch({
      result: "draw",
      my_team_rating: 240,
      opponent_team_rating: 240,
      rating_difference: 0,
      my_score: 1,
      opponent_score: 1,
    }),
  ]

  it("counts wins, losses, draws correctly", () => {
    const stats = computeH2H(matches)
    expect(stats.totalMatches).toBe(4)
    expect(stats.wins).toBe(2)
    expect(stats.losses).toBe(1)
    expect(stats.draws).toBe(1)
  })

  it("computes winRate as rounded percentage", () => {
    const stats = computeH2H(matches)
    expect(stats.winRate).toBe(50) // 2/4 = 50%
  })

  it("computes favorite/underdog splits", () => {
    const stats = computeH2H(matches)
    // 2 matches as favorite (260 > 240), both wins
    expect(stats.winsAsFavorite).toBe(2)
    expect(stats.lossesAsFavorite).toBe(0)
    expect(stats.drawsAsFavorite).toBe(0)
    // 1 match as underdog (230 < 250), loss
    expect(stats.winsAsUnderdog).toBe(0)
    expect(stats.lossesAsUnderdog).toBe(1)
    expect(stats.drawsAsUnderdog).toBe(0)
  })

  it("computes streak from most recent matches", () => {
    const stats = computeH2H(matches)
    // First two matches are wins
    expect(stats.currentStreak).toEqual({ count: 2, type: "W" })
  })

  it("computes avgRatingDiff as rounded mean", () => {
    const stats = computeH2H(matches)
    // (20 + 20 + 20 + 0) / 4 = 15
    expect(stats.avgRatingDiff).toBe(15)
  })

  it("computes avgScoreDiff as rounded-to-one-decimal mean of absolute diffs", () => {
    const stats = computeH2H(matches)
    // abs(3-1) + abs(2-0) + abs(0-2) + abs(1-1) = 2 + 2 + 2 + 0 = 6
    // 6 / 4 = 1.5
    expect(stats.avgScoreDiff).toBe(1.5)
  })

  it("recentForm has at most 10 entries", () => {
    const manyMatches = Array.from({ length: 15 }, () =>
      makeMatch({ result: "win" }),
    )
    const stats = computeH2H(manyMatches)
    expect(stats.recentForm).toHaveLength(10)
    expect(stats.recentForm.every((r) => r === "W")).toBe(true)
  })

  it("handles empty matches array", () => {
    const stats = computeH2H([])
    expect(stats.totalMatches).toBe(0)
    expect(stats.wins).toBe(0)
    expect(stats.winRate).toBe(0)
    expect(stats.currentStreak).toEqual({ count: 0, type: "W" })
    expect(stats.recentForm).toHaveLength(0)
  })
})

describe("computeSpreadBuckets", () => {
  it("produces exactly 5 fixed buckets", () => {
    const buckets = computeSpreadBuckets([])
    expect(buckets).toHaveLength(5)
    expect(buckets.map((b) => b.label)).toEqual([
      "0-4",
      "5-9",
      "10-19",
      "20-29",
      "30+",
    ])
  })

  it("returns sampleSize=0 and all pcts=0 for empty buckets", () => {
    const buckets = computeSpreadBuckets([])
    for (const b of buckets) {
      expect(b.sampleSize).toBe(0)
      expect(b.favoriteWinPct).toBe(0)
      expect(b.drawPct).toBe(0)
      expect(b.underdogWinPct).toBe(0)
    }
  })

  it("assigns matches to correct bucket based on rating_difference", () => {
    const matches = [
      makeMatch({ rating_difference: 3 }), // 0-4
      makeMatch({ rating_difference: 7 }), // 5-9
      makeMatch({ rating_difference: 15 }), // 10-19
      makeMatch({ rating_difference: 25 }), // 20-29
      makeMatch({ rating_difference: 50 }), // 30+
    ]
    const buckets = computeSpreadBuckets(matches)
    expect(buckets[0].sampleSize).toBe(1) // 0-4
    expect(buckets[1].sampleSize).toBe(1) // 5-9
    expect(buckets[2].sampleSize).toBe(1) // 10-19
    expect(buckets[3].sampleSize).toBe(1) // 20-29
    expect(buckets[4].sampleSize).toBe(1) // 30+
  })

  it("computes percentages correctly for bucket with mixed results", () => {
    const matches = [
      // 3 matches in 10-19 bucket: 2 favorite wins, 1 draw
      makeMatch({
        rating_difference: 15,
        result: "win",
        my_team_rating: 260,
        opponent_team_rating: 245,
      }),
      makeMatch({
        rating_difference: 12,
        result: "win",
        my_team_rating: 252,
        opponent_team_rating: 240,
      }),
      makeMatch({
        rating_difference: 18,
        result: "draw",
        my_team_rating: 258,
        opponent_team_rating: 240,
      }),
    ]
    const buckets = computeSpreadBuckets(matches)
    const bucket10_19 = buckets[2]
    expect(bucket10_19.sampleSize).toBe(3)
    expect(bucket10_19.favoriteWinPct).toBe(67) // 2/3 rounded
    expect(bucket10_19.drawPct).toBe(33) // 1/3 rounded
    expect(bucket10_19.underdogWinPct).toBe(0)
  })

  it("classifies underdog wins correctly", () => {
    // Underdog wins when role=underdog and result=win,
    // OR when role=favorite and result=loss
    const matches = [
      makeMatch({
        rating_difference: 5,
        result: "loss",
        my_team_rating: 260,
        opponent_team_rating: 255,
      }),
    ]
    const buckets = computeSpreadBuckets(matches)
    const bucket5_9 = buckets[1]
    expect(bucket5_9.underdogWinPct).toBe(100) // favorite lost = underdog win
  })
})
