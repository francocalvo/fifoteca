import { expect, type Page, test } from "@playwright/test"

/**
 * Fifoteca Match Page Tests
 *
 * Tests for score submission, validation, confirmation, and post-match flows.
 * These tests require:
 * - A running backend with Fifoteca services
 * - FIFA teams and leagues seeded in the database
 */

test.use({ storageState: "playwright/.auth/user.json" })

/**
 * Helper to ensure user has a Fifoteca player profile
 */
async function ensurePlayerProfile(page: Page): Promise<void> {
  // Navigate to Fifoteca home to trigger profile creation
  await page.goto("/fifoteca")
  // Wait for the page to load and potentially create profile
  await page.waitForLoadState("networkidle")
}

/**
 * Helper to fill score inputs
 */
async function fillScoreInputs(
  page: Page,
  player1Score: string,
  player2Score: string,
): Promise<void> {
  const p1Input = page
    .getByTestId("player1-score")
    .or(page.locator("#player1-score"))
  const p2Input = page
    .getByTestId("player2-score")
    .or(page.locator("#player2-score"))

  await p1Input.fill(player1Score)
  await p2Input.fill(player2Score)
}

/**
 * Helper to submit scores
 */
async function submitScores(page: Page): Promise<void> {
  await page.getByRole("button", { name: /submit.*score/i }).click()
}

// ============================================================================
// Score Input Validation Tests
// ============================================================================

test.describe("Score Input Validation", () => {
  test.skip(
    () => true,
    "Requires full game flow setup - run in Step 21 E2E suite",
  )

  test.beforeEach(async ({ page }) => {
    await ensurePlayerProfile(page)
    // Note: Full game flow setup (create room, complete spins) would go here
    // For now, this is a placeholder for Step 21 E2E tests
  })

  test("shows error for empty scores", async ({ page }) => {
    // Navigate to a match page (requires game setup)
    // await page.goto("/fifoteca/match/test-match-id")

    await fillScoreInputs(page, "", "")
    await submitScores(page)

    // Should show validation errors for both fields
    await expect(page.getByText(/score is required/i)).toHaveCount(2)
  })

  test("shows error for negative score", async ({ page }) => {
    await fillScoreInputs(page, "-1", "2")
    await submitScores(page)

    // Should show validation error for negative value
    await expect(page.getByText(/cannot be negative/i)).toBeVisible()
  })

  test("shows error for non-integer score (decimal)", async ({ page }) => {
    await fillScoreInputs(page, "1.5", "2")
    await submitScores(page)

    // Should show validation error for non-integer
    await expect(page.getByText(/must be a whole number/i)).toBeVisible()
  })

  test("accepts valid non-negative integer scores", async ({ page }) => {
    await fillScoreInputs(page, "3", "1")
    await submitScores(page)

    // Should not show validation errors
    await expect(page.getByText(/score is required/i)).not.toBeVisible()
    await expect(page.getByText(/cannot be negative/i)).not.toBeVisible()
    await expect(page.getByText(/must be a whole number/i)).not.toBeVisible()
  })

  test("accepts zero scores", async ({ page }) => {
    await fillScoreInputs(page, "0", "0")
    await submitScores(page)

    // Zero is valid
    await expect(page.getByText(/score is required/i)).not.toBeVisible()
    await expect(page.getByText(/cannot be negative/i)).not.toBeVisible()
  })
})

// ============================================================================
// Match State Display Tests
// ============================================================================

test.describe("Match State Display", () => {
  test.skip(
    () => true,
    "Requires full game flow setup - run in Step 21 E2E suite",
  )

  test("shows score input when no scores submitted", async ({ page }) => {
    // Verify ScoreInput form is visible
    await expect(page.getByRole("form")).toBeVisible()
    await expect(page.getByLabel(/player 1/i)).toBeVisible()
    await expect(page.getByLabel(/player 2/i)).toBeVisible()
  })

  test("shows confirmation UI when opponent submitted scores", async ({
    page,
  }) => {
    // Should show proposed scores and confirm button
    await expect(page.getByRole("button", { name: /confirm/i })).toBeVisible()
  })

  test("shows waiting message when I submitted scores", async ({ page }) => {
    await expect(page.getByText(/waiting for opponent/i)).toBeVisible()
  })

  test("shows result after confirmation", async ({ page }) => {
    // Should show result badge and stats
    await expect(page.getByText(/match result/i)).toBeVisible()
    await expect(page.getByText(/won|lost|draw/i)).toBeVisible()
  })
})

// ============================================================================
// Play Again and Exit Tests
// ============================================================================

test.describe("Post-Match Actions", () => {
  test.skip(
    () => true,
    "Requires full game flow setup - run in Step 21 E2E suite",
  )

  test("Play Again navigates to game page after room reset", async ({
    page,
  }) => {
    // Click play again
    await page.getByRole("button", { name: /play again/i }).click()

    // Should show waiting state
    await expect(page.getByText(/waiting for opponent/i)).toBeVisible()

    // After room reset, should navigate to game page
    // (This would be tested in full E2E suite)
  })

  test("Exit navigates to Fifoteca home", async ({ page }) => {
    await page.getByRole("button", { name: /exit/i }).click()

    await expect(page).toHaveURL("/fifoteca")
  })
})
