import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { H2HStats } from "@/lib/analytics"
import { H2HSummary } from "./H2HSummary"

const stats: H2HStats = {
  totalMatches: 10,
  wins: 6,
  losses: 3,
  draws: 1,
  winRate: 60,
  winsAsFavorite: 4,
  lossesAsFavorite: 1,
  drawsAsFavorite: 0,
  winsAsUnderdog: 2,
  lossesAsUnderdog: 2,
  drawsAsUnderdog: 1,
  currentStreak: { count: 3, type: "W" },
  avgRatingDiff: 12,
  avgScoreDiff: 1.8,
  recentForm: ["W", "W", "W", "L", "W", "D", "L", "W", "L", "W"],
}

describe("H2HSummary", () => {
  it("renders the opponent name in the title", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("You vs TestOpponent")).toBeInTheDocument()
  })

  it("renders overall record with win rate", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("6-1-3 (60%)")).toBeInTheDocument()
  })

  it("renders favorite split", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("As favorite")).toBeInTheDocument()
    expect(screen.getByText("4-0-1 (80%)")).toBeInTheDocument()
  })

  it("renders underdog split", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("As underdog")).toBeInTheDocument()
    expect(screen.getByText("2-1-2 (40%)")).toBeInTheDocument()
  })

  it("renders current streak", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("Current streak")).toBeInTheDocument()
    expect(screen.getByText("3W")).toBeInTheDocument()
  })

  it("renders average stats", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("12")).toBeInTheDocument()
    expect(screen.getByText("1.8")).toBeInTheDocument()
  })

  it("renders recent form badges", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("Recent:")).toBeInTheDocument()
    // Count W/L/D badges in recent form
    const allElements = screen.getAllByText("W")
    // W appears in recent form (6 times) + H2HBar (6 W label)
    expect(allElements.length).toBeGreaterThanOrEqual(6)
  })

  it("renders W/D/L counts in the bar", () => {
    render(<H2HSummary stats={stats} opponentName="TestOpponent" />)
    expect(screen.getByText("6 W")).toBeInTheDocument()
    expect(screen.getByText("1 D")).toBeInTheDocument()
    expect(screen.getByText("3 L")).toBeInTheDocument()
  })
})
