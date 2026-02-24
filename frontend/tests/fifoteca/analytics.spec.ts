import { expect, test } from "@playwright/test"

const PLAYERS_URL = "**/api/v1/fifoteca/players"
const PLAYERS_ME_URL = "**/api/v1/fifoteca/players/me"
const MATCHES_URL = "**/api/v1/fifoteca/matches"

const currentPlayerId = "player-current-id"
const opponentId = "player-opponent-id"

const mockPlayers = [
  {
    id: currentPlayerId,
    user_id: "user-current",
    display_name: "Current Player",
    total_wins: 5,
    total_losses: 3,
    total_draws: 1,
    has_protection: false,
  },
  {
    id: opponentId,
    user_id: "user-opponent",
    display_name: "Test Opponent",
    total_wins: 3,
    total_losses: 5,
    total_draws: 1,
    has_protection: false,
  },
  {
    id: "player-other-id",
    user_id: "user-other",
    display_name: "Other Player",
    total_wins: 0,
    total_losses: 0,
    total_draws: 0,
    has_protection: false,
  },
]

const mockCurrentPlayer = mockPlayers[0]

const mockMatches = {
  data: [
    {
      id: "match-1",
      created_at: "2026-02-20T12:00:00Z",
      round_number: 1,
      rating_difference: 20,
      confirmed: true,
      opponent_id: opponentId,
      opponent_display_name: "Test Opponent",
      my_team_name: "Arsenal",
      opponent_team_name: "Chelsea",
      my_team_rating: 260,
      opponent_team_rating: 240,
      my_score: 3,
      opponent_score: 1,
      result: "win",
    },
    {
      id: "match-2",
      created_at: "2026-02-18T12:00:00Z",
      round_number: 1,
      rating_difference: 15,
      confirmed: true,
      opponent_id: opponentId,
      opponent_display_name: "Test Opponent",
      my_team_name: "Real Madrid",
      opponent_team_name: "Barcelona",
      my_team_rating: 235,
      opponent_team_rating: 250,
      my_score: 1,
      opponent_score: 2,
      result: "loss",
    },
    {
      id: "match-3",
      created_at: "2026-02-15T12:00:00Z",
      round_number: 1,
      rating_difference: 0,
      confirmed: true,
      opponent_id: opponentId,
      opponent_display_name: "Test Opponent",
      my_team_name: "Bayern",
      opponent_team_name: "Dortmund",
      my_team_rating: 245,
      opponent_team_rating: 245,
      my_score: 2,
      opponent_score: 2,
      result: "draw",
    },
    {
      id: "match-4",
      created_at: "2026-02-10T12:00:00Z",
      round_number: 1,
      rating_difference: 5,
      confirmed: true,
      opponent_id: "player-other-id",
      opponent_display_name: "Other Player",
      my_team_name: "PSG",
      opponent_team_name: "Lyon",
      my_team_rating: 250,
      opponent_team_rating: 245,
      my_score: 4,
      opponent_score: 0,
      result: "win",
    },
  ],
  count: 4,
}

function setupMocks(page: import("@playwright/test").Page) {
  return Promise.all([
    page.route(PLAYERS_URL, (route) => {
      if (route.request().url().includes("/me")) return route.fallback()
      return route.fulfill({ json: mockPlayers })
    }),
    page.route(PLAYERS_ME_URL, (route) =>
      route.fulfill({ json: mockCurrentPlayer }),
    ),
    page.route(MATCHES_URL, (route) => route.fulfill({ json: mockMatches })),
  ])
}

test.describe("Analytics Page", () => {
  test("initial load shows selector but no analytics sections", async ({
    page,
  }) => {
    await setupMocks(page)
    await page.goto("/fifoteca/analytics")

    // Selector should be visible
    await expect(page.getByText("Select an opponent")).toBeVisible()

    // Analytics sections should not be visible
    await expect(page.getByText("Match History")).not.toBeVisible()
    await expect(page.getByText("Spread Analytics")).not.toBeVisible()
  })

  test("selecting opponent with matches shows all analytics sections", async ({
    page,
  }) => {
    await setupMocks(page)
    await page.goto("/fifoteca/analytics")

    // Open the opponent selector dropdown and pick Test Opponent
    await page.getByRole("combobox").click()
    await page.getByRole("option", { name: "Test Opponent" }).click()

    // H2H section should appear
    await expect(page.getByText("You vs Test Opponent")).toBeVisible()

    // Match History section should appear with filtered matches only
    await expect(page.getByText("Match History")).toBeVisible()
    // Should show 3 matches against Test Opponent (not the one against Other Player)
    await expect(page.getByText("Arsenal")).toBeVisible()
    await expect(page.getByText("Real Madrid")).toBeVisible()
    await expect(page.getByText("Bayern")).toBeVisible()
    // PSG match (against Other Player) should NOT appear
    await expect(page.getByText("PSG")).not.toBeVisible()

    // Spread Analytics should appear
    await expect(page.getByText("Spread Analytics")).toBeVisible()
  })

  test("selecting opponent with no matches shows empty state", async ({
    page,
  }) => {
    await setupMocks(page)
    await page.goto("/fifoteca/analytics")

    // Select "Other Player" who has no matches in our filtered view
    // (match-4 is against Other Player but from current player's perspective)
    // We need a player with truly zero matches — let's override the mock
    await page.route(MATCHES_URL, (route) =>
      route.fulfill({ json: { data: [], count: 0 } }),
    )

    await page.getByRole("combobox").click()
    await page.getByRole("option", { name: "Other Player" }).click()

    await expect(page.getByText("No matches yet")).toBeVisible()
  })

  test("sort interaction on Rating Diff header changes row order", async ({
    page,
  }) => {
    await setupMocks(page)
    await page.goto("/fifoteca/analytics")

    // Select opponent
    await page.getByRole("combobox").click()
    await page.getByRole("option", { name: "Test Opponent" }).click()

    // Wait for table to render
    await expect(page.getByText("Match History")).toBeVisible()

    // Click Rating Diff sort header to sort ascending (first click = desc since it's not current sort)
    const ratingDiffHeader = page.getByRole("button", {
      name: /Rating Diff/,
    })
    await ratingDiffHeader.click()

    // Get all rating diff cells — they should now be in sorted order
    // After first click on a new column, sort is desc
    // The signed diffs are: match1=+20, match2=-15, match3=0
    // Desc order: +20, 0, -15
    const rows = page.locator("tbody tr")
    const firstRow = rows.nth(0)
    await expect(firstRow.getByText("+20")).toBeVisible()

    // Click again for ascending
    await ratingDiffHeader.click()

    // Asc order: -15, 0, +20
    const firstRowAsc = rows.nth(0)
    await expect(firstRowAsc.getByText("-15")).toBeVisible()
  })
})
