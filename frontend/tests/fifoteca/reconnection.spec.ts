/**
 * Fifoteca E2E — Reconnection
 *
 * Disconnect one player mid-game (page reload), verify state rehydration
 * via WebSocket state_sync, and confirm gameplay can continue.
 *
 * Requires: backend + frontend running, FIFA data seeded.
 */
import { expect, test } from "@playwright/test"

import {
  createGameRoom,
  getCurrentTurnPage,
  joinGameRoom,
  type PlayerSetup,
  playLeaguePhase,
  setupPlayer,
  waitForGamePage,
  waitForMyTurn,
} from "./helpers"

test.describe("Reconnection", () => {
  let p1: PlayerSetup
  let p2: PlayerSetup

  test.beforeAll(async ({ browser }) => {
    ;[p1, p2] = await Promise.all([setupPlayer(browser), setupPlayer(browser)])
  })

  test.afterAll(async () => {
    await p1.context.close()
    await p2.context.close()
  })

  test("player reloads mid-game and resumes with full state", async () => {
    test.setTimeout(90_000)

    const roomCode = await createGameRoom(p1.page)
    await joinGameRoom(p2.page, roomCode)
    await Promise.all([waitForGamePage(p1.page), waitForGamePage(p2.page)])

    // Play through league phase so we have meaningful state
    await playLeaguePhase(p1.page, p2.page)

    // We're now in team phase. Remember whose turn it is.
    const { current: activePage, other: idlePage } = await getCurrentTurnPage(
      p1.page,
      p2.page,
    )

    // Active player spins team to create some state
    await activePage.getByRole("button", { name: "Spin Team" }).click()

    // Idle player now has the turn
    await waitForMyTurn(idlePage)

    // --- Disconnect: reload the idle player's page ---
    await idlePage.reload()

    // After reload, the page should reconnect via WebSocket and receive state_sync.
    // The "Spin Phase" heading should reappear and the player should see their turn.
    await expect(idlePage.getByText("Spin Phase")).toBeVisible({
      timeout: 15_000,
    })
    await expect(idlePage.getByText("Your turn")).toBeVisible({
      timeout: 15_000,
    })

    // Verify the idle player can still take actions (spin team)
    await idlePage.getByRole("button", { name: "Spin Team" }).click()

    // Turn should switch back to the other player
    await waitForMyTurn(activePage)

    // Game continues – the active player can lock team
    await expect(
      activePage.getByRole("button", { name: "Lock Team" }),
    ).toBeEnabled({ timeout: 5_000 })
  })
})
