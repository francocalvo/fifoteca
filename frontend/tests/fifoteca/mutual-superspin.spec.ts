/**
 * Fifoteca E2E — Mutual Superspin
 *
 * Tests the propose → accept and propose → decline flows for mutual superspin.
 *
 * Requires: backend + frontend running, FIFA data seeded.
 */
import { expect, test } from "@playwright/test"

import {
  type PlayerSetup,
  createGameRoom,
  getCurrentTurnPage,
  joinGameRoom,
  setupPlayer,
  waitForGamePage,
} from "./helpers"

test.describe("Mutual superspin", () => {
  let p1: PlayerSetup
  let p2: PlayerSetup

  test.beforeAll(async ({ browser }) => {
    ;[p1, p2] = await Promise.all([setupPlayer(browser), setupPlayer(browser)])
  })

  test.afterAll(async () => {
    await p1.context.close()
    await p2.context.close()
  })

  test("propose + decline: game continues normally", async () => {
    test.setTimeout(60_000)

    const roomCode = await createGameRoom(p1.page)
    await joinGameRoom(p2.page, roomCode)
    await Promise.all([waitForGamePage(p1.page), waitForGamePage(p2.page)])

    // Determine who has the turn
    const { current: proposer, other: receiver } = await getCurrentTurnPage(
      p1.page,
      p2.page,
    )

    // Proposer clicks "Propose Mutual Superspin"
    await proposer
      .getByRole("button", { name: "Propose Mutual Superspin" })
      .click()

    // Receiver sees the dialog
    await expect(
      receiver.getByText("Mutual Superspin Proposal"),
    ).toBeVisible({ timeout: 10_000 })

    // Receiver declines
    await receiver.getByRole("button", { name: "Decline" }).click()

    // Dialog closes
    await expect(
      receiver.getByText("Mutual Superspin Proposal"),
    ).not.toBeVisible({ timeout: 5_000 })

    // Game continues – the spin phase heading and turn badge should still be visible
    await expect(proposer.getByText("Spin Phase")).toBeVisible({
      timeout: 5_000,
    })
    await expect(receiver.getByText("Spin Phase")).toBeVisible({
      timeout: 5_000,
    })
  })

  test("propose + accept: room resets and spins restart", async () => {
    test.setTimeout(60_000)

    const roomCode = await createGameRoom(p1.page)
    await joinGameRoom(p2.page, roomCode)
    await Promise.all([waitForGamePage(p1.page), waitForGamePage(p2.page)])

    // Do one spin so we have some state to reset
    const { current: firstSpinner, other: secondPlayer } =
      await getCurrentTurnPage(p1.page, p2.page)
    await firstSpinner.getByRole("button", { name: "Spin League" }).click()

    // Wait for the other player's turn
    await expect(secondPlayer.getByText("Your turn")).toBeVisible({
      timeout: 10_000,
    })

    // Second player proposes mutual superspin
    await secondPlayer
      .getByRole("button", { name: "Propose Mutual Superspin" })
      .click()

    // First player (proposer's opponent) sees the dialog
    await expect(
      firstSpinner.getByText("Mutual Superspin Proposal"),
    ).toBeVisible({ timeout: 10_000 })

    // First player accepts
    await firstSpinner.getByRole("button", { name: "Accept" }).click()

    // After acceptance, the room should reset – both should see "Spin Phase"
    // and the league spin buttons should be available again.
    // Wait for the game to reset (state_sync with SPINNING_LEAGUES)
    await expect(p1.page.getByText("Spin Phase")).toBeVisible({
      timeout: 15_000,
    })
    await expect(p2.page.getByText("Spin Phase")).toBeVisible({
      timeout: 15_000,
    })

    // The "Spin League" button should be visible for the current turn player
    const { current: resetTurnPlayer } = await getCurrentTurnPage(
      p1.page,
      p2.page,
    )
    await expect(
      resetTurnPlayer.getByRole("button", { name: "Spin League" }),
    ).toBeVisible({ timeout: 10_000 })
  })
})
