/**
 * Fifoteca E2E — Full Game Flow
 *
 * Happy-path: room creation → join → league/team spins → rating review →
 * match score → confirmation → result → history.
 *
 * Requires: backend + frontend running, FIFA data seeded.
 */
import { expect, test } from "@playwright/test"

import {
  createGameRoom,
  joinGameRoom,
  type PlayerSetup,
  playThroughSpins,
  setupPlayer,
  submitAndConfirmScore,
  waitForGamePage,
  waitForMatchPage,
} from "./helpers"

test.describe("Full game flow", () => {
  let p1: PlayerSetup
  let p2: PlayerSetup

  test.beforeAll(async ({ browser }) => {
    // Create two independent players in parallel
    ;[p1, p2] = await Promise.all([setupPlayer(browser), setupPlayer(browser)])
  })

  test.afterAll(async () => {
    await p1.context.close()
    await p2.context.close()
  })

  test("two players complete a full game and see history", async () => {
    // 1. Player 1 creates a room
    const roomCode = await createGameRoom(p1.page)
    expect(roomCode).toMatch(/^[A-Z0-9]{6}$/)

    // 2. Player 2 joins
    await joinGameRoom(p2.page, roomCode)

    // 3. Both land on the game page
    await Promise.all([waitForGamePage(p1.page), waitForGamePage(p2.page)])

    // 4. Play through league + team spins + rating review
    await playThroughSpins(p1.page, p2.page)

    // 5. Both navigate to match page
    await Promise.all([waitForMatchPage(p1.page), waitForMatchPage(p2.page)])

    // 6. P1 submits scores, P2 confirms
    await submitAndConfirmScore(p1.page, p2.page, 3, 1)

    // 7. Verify result badges
    const p1Result = p1.page
      .getByText("You Won!")
      .or(p1.page.getByText("You Lost"))
      .or(p1.page.getByText("Draw"))
    await expect(p1Result).toBeVisible({ timeout: 5_000 })

    const p2Result = p2.page
      .getByText("You Won!")
      .or(p2.page.getByText("You Lost"))
      .or(p2.page.getByText("Draw"))
    await expect(p2Result).toBeVisible({ timeout: 5_000 })

    // 8. Navigate to history and verify a match exists
    await p1.page.goto("/fifoteca/history")
    await expect(
      p1.page.getByRole("heading", { name: "Match History" }),
    ).toBeVisible({ timeout: 10_000 })
    // The match history table should have at least one row
    // (the DataTable renders rows in <tbody>)
    await expect(p1.page.locator("tbody tr").first()).toBeVisible({
      timeout: 10_000,
    })
  })
})
