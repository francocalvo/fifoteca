/**
 * Shared helpers for Fifoteca two-player E2E tests.
 *
 * Preconditions:
 * - Backend running with FIFA teams/leagues seeded
 * - Frontend running on localhost:5173
 */
import {
  type Browser,
  type BrowserContext,
  expect,
  type Page,
} from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "../config"
import { randomEmail } from "../utils/random"

const API_URL = process.env.VITE_API_URL || "http://localhost:8000"

/**
 * Create a verified user directly via the superuser API.
 */
async function createVerifiedUser(
  email: string,
  password: string,
): Promise<void> {
  // Get superuser token
  const tokenRes = await fetch(`${API_URL}/api/v1/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `username=${encodeURIComponent(firstSuperuser)}&password=${encodeURIComponent(firstSuperuserPassword)}`,
  })
  if (!tokenRes.ok) {
    throw new Error(`Failed to get superuser token: ${tokenRes.status}`)
  }
  const { access_token } = (await tokenRes.json()) as {
    access_token: string
  }

  // Create user via superuser endpoint
  const createRes = await fetch(`${API_URL}/api/v1/users/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access_token}`,
    },
    body: JSON.stringify({
      email,
      password,
      is_active: true,
      is_superuser: false,
      full_name: "Test Player",
    }),
  })
  if (!createRes.ok) {
    const body = await createRes.text()
    throw new Error(`Failed to create user: ${createRes.status} ${body}`)
  }
}

export interface PlayerSetup {
  context: BrowserContext
  page: Page
  email: string
}

// ---------------------------------------------------------------------------
// User creation & login
// ---------------------------------------------------------------------------

/** Create a fresh user, log in via a new browser context, trigger profile creation. */
export async function setupPlayer(browser: Browser): Promise<PlayerSetup> {
  const email = randomEmail()
  const password = "TestPassword123!"

  await createVerifiedUser(email, password)

  const context = await browser.newContext({
    baseURL: "http://localhost:5173",
    storageState: { cookies: [], origins: [] },
  })
  const page = await context.newPage()

  // Log in
  await page.goto("/login")
  await page.getByTestId("email-input").fill(email)
  await page.getByTestId("password-input").fill(password)
  await page.getByRole("button", { name: "Log In" }).click()
  await page.waitForURL("/")

  // Navigate to Fifoteca to trigger player profile creation
  await page.goto("/fifoteca")
  await expect(page.getByRole("heading", { name: "Fifoteca" })).toBeVisible({
    timeout: 10_000,
  })

  return { context, page, email }
}

// ---------------------------------------------------------------------------
// Room management
// ---------------------------------------------------------------------------

/** Create a room and return its 6-char code. Leaves page on lobby. */
export async function createGameRoom(page: Page): Promise<string> {
  await page.goto("/fifoteca")
  await page.getByRole("button", { name: "Create Room" }).click()
  await page.waitForURL(/\/fifoteca\/lobby\//, { timeout: 10_000 })

  const url = page.url()
  const roomCode = url.split("/lobby/")[1]
  if (!roomCode || roomCode.length !== 6) {
    throw new Error(`Unexpected lobby URL: ${url}`)
  }
  return roomCode
}

/** Join a room via code. Leaves page on lobby. */
export async function joinGameRoom(
  page: Page,
  roomCode: string,
): Promise<void> {
  await page.goto("/fifoteca")
  await page.getByPlaceholder("ABC123").fill(roomCode)
  await page.getByRole("button", { name: "Join" }).click()
  await page.waitForURL(/\/fifoteca\/lobby\//, { timeout: 10_000 })
}

// ---------------------------------------------------------------------------
// Game phase helpers
// ---------------------------------------------------------------------------

/** Wait until the page navigates to the game page and "Spin Phase" heading appears. */
export async function waitForGamePage(
  page: Page,
  timeout = 20_000,
): Promise<void> {
  await page.waitForURL(/\/fifoteca\/game\//, { timeout })
  await expect(page.getByText("Spin Phase")).toBeVisible({ timeout: 10_000 })
}

/** Wait until "Your turn" badge is visible. */
export async function waitForMyTurn(
  page: Page,
  timeout = 15_000,
): Promise<void> {
  await expect(page.getByText("Your turn")).toBeVisible({ timeout })
}

/**
 * Determine which of two pages currently has the turn.
 * Returns { current, other } where current shows "Your turn".
 */
export async function getCurrentTurnPage(
  p1: Page,
  p2: Page,
  timeout = 15_000,
): Promise<{ current: Page; other: Page }> {
  return Promise.race([
    p1
      .getByText("Your turn")
      .waitFor({ state: "visible", timeout })
      .then(() => ({ current: p1, other: p2 })),
    p2
      .getByText("Your turn")
      .waitFor({ state: "visible", timeout })
      .then(() => ({ current: p2, other: p1 })),
  ])
}

/**
 * Play through the league spin phase.
 * Each player: spin once → on next turn lock.
 * After both lock the phase transitions to SPINNING_TEAMS.
 */
export async function playLeaguePhase(p1: Page, p2: Page): Promise<void> {
  // First player spins league
  let { current, other } = await getCurrentTurnPage(p1, p2)
  await current.getByRole("button", { name: "Spin League" }).click()

  // Second player spins league
  await waitForMyTurn(other)
  await other.getByRole("button", { name: "Spin League" }).click()

  // Wait for the turn to change away from 'other' before calling getCurrentTurnPage.
  // This avoids a race where getCurrentTurnPage resolves immediately with 'other'
  // because its "Your turn" badge hasn't updated yet.
  await expect(other.getByText("Opponent's turn")).toBeVisible({
    timeout: 10_000,
  })

  // Now lock round – whoever's turn it is locks first.
  ;({ current, other } = await getCurrentTurnPage(p1, p2))
  await expect(
    current.getByRole("button", { name: "Lock League" }),
  ).toBeEnabled({ timeout: 10_000 })
  await current.getByRole("button", { name: "Lock League" }).click()

  // Wait for the turn to change away from 'current' before next lock
  await expect(current.getByText("Opponent's turn")).toBeVisible({
    timeout: 10_000,
  })

  // Other player locks – triggers phase transition to SPINNING_TEAMS
  ;({ current, other } = await getCurrentTurnPage(p1, p2))
  await expect(
    current.getByRole("button", { name: "Lock League" }),
  ).toBeEnabled({ timeout: 10_000 })
  await current.getByRole("button", { name: "Lock League" }).click()

  // Wait for team phase – "Spin Team" button appears
  const { current: teamTurnPage } = await getCurrentTurnPage(p1, p2)
  await expect(
    teamTurnPage.getByRole("button", { name: "Spin Team" }),
  ).toBeVisible({ timeout: 10_000 })
}

/**
 * Play through the team spin phase.
 * Each player: spin once → on next turn lock.
 * After both lock the phase transitions to RATING_REVIEW.
 */
export async function playTeamPhase(p1: Page, p2: Page): Promise<void> {
  let { current, other } = await getCurrentTurnPage(p1, p2)
  await current.getByRole("button", { name: "Spin Team" }).click()

  await waitForMyTurn(other)
  await other.getByRole("button", { name: "Spin Team" }).click()

  // Wait for the turn to change away from 'other'
  await expect(other.getByText("Opponent's turn")).toBeVisible({
    timeout: 10_000,
  })

  ;({ current, other } = await getCurrentTurnPage(p1, p2))
  await expect(current.getByRole("button", { name: "Lock Team" })).toBeEnabled({
    timeout: 10_000,
  })
  await current.getByRole("button", { name: "Lock Team" }).click()

  // Wait for the turn to change away from 'current'
  await expect(current.getByText("Opponent's turn")).toBeVisible({
    timeout: 10_000,
  })

  ;({ current, other } = await getCurrentTurnPage(p1, p2))
  await expect(current.getByRole("button", { name: "Lock Team" })).toBeEnabled({
    timeout: 10_000,
  })
  await current.getByRole("button", { name: "Lock Team" }).click()

  // Wait for Rating Review on both pages
  await Promise.all([
    expect(p1.getByText("Rating Review")).toBeVisible({ timeout: 15_000 }),
    expect(p2.getByText("Rating Review")).toBeVisible({ timeout: 15_000 }),
  ])
}

/**
 * Both players click "Ready to Play" to start the match.
 * The button is NOT gated by turn during RATING_REVIEW.
 */
export async function playRatingReview(p1: Page, p2: Page): Promise<void> {
  // Ensure both see Rating Review
  await expect(p1.getByText("Rating Review")).toBeVisible({ timeout: 10_000 })
  await expect(p2.getByText("Rating Review")).toBeVisible({ timeout: 10_000 })

  // P1 readies first, then P2
  await p1.getByRole("button", { name: "Ready to Play" }).click()
  // Brief wait for backend to process the first ready
  await p1.waitForTimeout(500)
  await p2.getByRole("button", { name: "Ready to Play" }).click()
}

/** Wait for match page navigation. */
export async function waitForMatchPage(
  page: Page,
  timeout = 15_000,
): Promise<void> {
  await page.waitForURL(/\/fifoteca\/match\//, { timeout })
  await expect(page.getByRole("heading", { name: "Match" })).toBeVisible({
    timeout: 10_000,
  })
}

/**
 * One player submits scores, the other confirms.
 * Both end up seeing "Match Result".
 */
export async function submitAndConfirmScore(
  submitter: Page,
  confirmer: Page,
  p1Score: number,
  p2Score: number,
): Promise<void> {
  // Submitter enters scores
  await expect(submitter.getByText("Enter Match Score")).toBeVisible({
    timeout: 10_000,
  })
  await submitter.locator("#player1-score").fill(p1Score.toString())
  await submitter.locator("#player2-score").fill(p2Score.toString())
  await submitter.getByRole("button", { name: "Submit Scores" }).click()

  // Submitter sees waiting state
  await expect(
    submitter.getByText("Waiting for opponent to confirm"),
  ).toBeVisible({ timeout: 10_000 })

  // Confirmer sees the "Confirm Score" button.
  // The WS score_submitted notification may not always propagate immediately,
  // so reload the confirmer's page to force a fresh match data fetch if needed.
  const confirmBtn = confirmer.getByRole("button", { name: "Confirm Score" })
  try {
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
  } catch {
    // WS notification may not have triggered a refetch – reload to force it
    await confirmer.reload()
    await expect(confirmBtn).toBeVisible({ timeout: 10_000 })
  }
  await confirmBtn.click()

  // Both see "Match Result" – reload as fallback if WS notification is missed
  for (const page of [submitter, confirmer]) {
    try {
      await expect(page.getByText("Match Result")).toBeVisible({
        timeout: 5_000,
      })
    } catch {
      await page.reload()
      await expect(page.getByText("Match Result")).toBeVisible({
        timeout: 10_000,
      })
    }
  }
}

/**
 * Full spin flow: league phase → team phase → rating review.
 * After this, both pages auto-navigate to the match page.
 */
export async function playThroughSpins(p1: Page, p2: Page): Promise<void> {
  await playLeaguePhase(p1, p2)
  await playTeamPhase(p1, p2)
  await playRatingReview(p1, p2)
}
