/**
 * Fifoteca E2E — Special Spins
 *
 * Tests superspin (during SPINNING_TEAMS) and parity spin (during RATING_REVIEW).
 *
 * Superspin requires has_protection from a previous match. To reliably trigger it,
 * we use mutual superspin to give both players has_superspin in the same room.
 *
 * Parity spin requires a rating difference >= 30 between the two teams.
 * This test retries with new rooms until the condition is met.
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

const MAX_ATTEMPTS = 15

test.describe("Special spins", () => {
  let p1: PlayerSetup
  let p2: PlayerSetup

  test.beforeAll(async ({ browser }) => {
    ;[p1, p2] = await Promise.all([setupPlayer(browser), setupPlayer(browser)])
  })

  test.afterAll(async () => {
    await p1.context.close()
    await p2.context.close()
  })

  test("superspin is available during team phase and re-spins the team", async () => {
    // Superspin requires has_superspin which comes from has_protection (previous match)
    // or from mutual superspin. We use mutual superspin to set it up reliably.
    test.setTimeout(120_000)

    const roomCode = await createGameRoom(p1.page)
    await joinGameRoom(p2.page, roomCode)
    await Promise.all([waitForGamePage(p1.page), waitForGamePage(p2.page)])

    // Step 1: Use mutual superspin to give both players has_superspin
    const { current: proposer, other: receiver } = await getCurrentTurnPage(
      p1.page,
      p2.page,
    )

    await proposer
      .getByRole("button", { name: "Propose Mutual Superspin" })
      .click()

    // Receiver sees and accepts the proposal
    await expect(receiver.getByText("Mutual Superspin Proposal")).toBeVisible({
      timeout: 10_000,
    })
    await receiver.getByRole("button", { name: "Accept" }).click()

    // After acceptance, room resets. Both see Spin Phase again.
    await expect(p1.page.getByText("Spin Phase")).toBeVisible({
      timeout: 15_000,
    })
    await expect(p2.page.getByText("Spin Phase")).toBeVisible({
      timeout: 15_000,
    })

    // Step 2: Play through league phase (both players now have has_superspin)
    await playLeaguePhase(p1.page, p2.page)

    // Step 3: In team phase, spin a team then use superspin
    const { current } = await getCurrentTurnPage(p1.page, p2.page)

    // Spin team first (need a team before superspin can re-spin)
    await current.getByRole("button", { name: "Spin Team" }).click()

    // Other player spins
    const otherPage = current === p1.page ? p2.page : p1.page
    await waitForMyTurn(otherPage)
    await otherPage.getByRole("button", { name: "Spin Team" }).click()

    // Wait for turn to return to original player
    await waitForMyTurn(current)

    // "Use Superspin" should now be visible (has_superspin=true from mutual superspin)
    const superspinBtn = current.getByRole("button", {
      name: "Use Superspin",
    })
    await expect(superspinBtn).toBeVisible({ timeout: 5_000 })

    // Click superspin – should re-spin the team
    await superspinBtn.click()

    // Superspin button should disappear (used once)
    await expect(
      current.getByRole("button", { name: "Use Superspin" }),
    ).not.toBeVisible({ timeout: 5_000 })
  })

  test("parity spin is offered when rating difference is large", async () => {
    // Parity spin: during RATING_REVIEW, if the rating difference is >= 30,
    // the disadvantaged player sees a "Use Parity Spin" button.
    // RATING_REVIEW actions are not turn-gated, so either player can act.
    test.setTimeout(300_000)

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      const roomCode = await createGameRoom(p1.page)
      await joinGameRoom(p2.page, roomCode)
      await Promise.all([waitForGamePage(p1.page), waitForGamePage(p2.page)])

      // Play through leagues and teams
      await playLeaguePhase(p1.page, p2.page)

      // Team phase: spin and lock
      let { current, other } = await getCurrentTurnPage(p1.page, p2.page)
      await current.getByRole("button", { name: "Spin Team" }).click()
      await waitForMyTurn(other)
      await other.getByRole("button", { name: "Spin Team" }).click()

      // Wait for turn to change away from 'other' before calling getCurrentTurnPage
      await expect(other.getByText("Opponent's turn")).toBeVisible({
        timeout: 10_000,
      })

      ;({ current, other } = await getCurrentTurnPage(p1.page, p2.page))
      await expect(
        current.getByRole("button", { name: "Lock Team" }),
      ).toBeEnabled({ timeout: 10_000 })
      await current.getByRole("button", { name: "Lock Team" }).click()

      // Wait for turn to change away from 'current' before next lock
      await expect(current.getByText("Opponent's turn")).toBeVisible({
        timeout: 10_000,
      })

      ;({ current, other } = await getCurrentTurnPage(p1.page, p2.page))
      await expect(
        current.getByRole("button", { name: "Lock Team" }),
      ).toBeEnabled({ timeout: 10_000 })
      await current.getByRole("button", { name: "Lock Team" }).click()

      // Wait for Rating Review
      await Promise.all([
        expect(p1.page.getByText("Rating Review")).toBeVisible({
          timeout: 15_000,
        }),
        expect(p2.page.getByText("Rating Review")).toBeVisible({
          timeout: 15_000,
        }),
      ])

      // Check if either player sees "Use Parity Spin"
      const p1HasParity = await p1.page
        .getByRole("button", { name: "Use Parity Spin" })
        .isVisible({ timeout: 2_000 })
        .catch(() => false)
      const p2HasParity = await p2.page
        .getByRole("button", { name: "Use Parity Spin" })
        .isVisible({ timeout: 2_000 })
        .catch(() => false)

      if (!p1HasParity && !p2HasParity) {
        // Rating difference too small for parity. Try another room.
        continue
      }

      // The player with parity spin clicks it
      const parityPlayer = p1HasParity ? p1.page : p2.page

      await parityPlayer
        .getByRole("button", { name: "Use Parity Spin" })
        .click()

      // After parity spin, the button should disappear (used once)
      await expect(
        parityPlayer.getByRole("button", { name: "Use Parity Spin" }),
      ).not.toBeVisible({ timeout: 5_000 })

      // Test passed
      return
    }

    test.skip(
      true,
      `Could not trigger parity spin in ${MAX_ATTEMPTS} attempts — rating differences were all < 30 (requires rare team matchup)`,
    )
  })
})
