import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface ScoreInputProps {
  /** Name of player 1's team */
  team1Name: string
  /** Name of player 2's team */
  team2Name: string
  /** Callback when valid scores are submitted */
  onSubmit: (player1Score: number, player2Score: number) => void
  /** Whether submission is in progress */
  isSubmitting?: boolean
  /** Optional: pre-filled scores */
  initialScores?: { player1: number; player2: number }
}

/**
 * ScoreInput provides a form for entering match scores with validation.
 * Scores must be non-negative integers.
 */
export function ScoreInput({
  team1Name,
  team2Name,
  onSubmit,
  isSubmitting = false,
  initialScores,
}: ScoreInputProps) {
  const [player1Score, setPlayer1Score] = useState(
    initialScores?.player1?.toString() ?? "",
  )
  const [player2Score, setPlayer2Score] = useState(
    initialScores?.player2?.toString() ?? "",
  )
  const [errors, setErrors] = useState<{ player1?: string; player2?: string }>(
    {},
  )

  const validateScore = (
    value: string,
  ): { isValid: boolean; error?: string } => {
    if (value === "") {
      return { isValid: false, error: "Score is required" }
    }

    const num = Number(value)

    // Check if it's a valid integer (no decimals)
    if (!Number.isInteger(num)) {
      return { isValid: false, error: "Must be a whole number" }
    }

    // Check if non-negative
    if (num < 0) {
      return { isValid: false, error: "Cannot be negative" }
    }

    return { isValid: true }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    const player1Validation = validateScore(player1Score)
    const player2Validation = validateScore(player2Score)

    const newErrors: { player1?: string; player2?: string } = {}

    if (!player1Validation.isValid) {
      newErrors.player1 = player1Validation.error
    }
    if (!player2Validation.isValid) {
      newErrors.player2 = player2Validation.error
    }

    setErrors(newErrors)

    if (Object.keys(newErrors).length === 0) {
      onSubmit(Number(player1Score), Number(player2Score))
    }
  }

  const handleScoreChange = (player: "player1" | "player2", value: string) => {
    // Allow digits, minus sign (for negative), and decimal point (for non-integers)
    // Validation on submit will catch invalid values
    const sanitized = value.replace(/[^0-9.-]/g, "")

    // Ensure only one minus sign at the start
    const normalized = sanitized
      .replace(/^-/, "_TEMP_MINUS_")
      .replace(/-/g, "")
      .replace("_TEMP_MINUS_", "-")

    // Ensure only one decimal point
    const parts = normalized.split(".")
    const finalValue =
      parts.length > 2 ? `${parts[0]}.${parts.slice(1).join("")}` : normalized

    if (player === "player1") {
      setPlayer1Score(finalValue)
      if (errors.player1) {
        setErrors((prev) => ({ ...prev, player1: undefined }))
      }
    } else {
      setPlayer2Score(finalValue)
      if (errors.player2) {
        setErrors((prev) => ({ ...prev, player2: undefined }))
      }
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* Player 1 Score */}
        <div className="space-y-2">
          <Label htmlFor="player1-score" className="text-sm">
            {team1Name}
          </Label>
          <Input
            id="player1-score"
            type="text"
            inputMode="numeric"
            value={player1Score}
            onChange={(e) => handleScoreChange("player1", e.target.value)}
            placeholder="0"
            className={errors.player1 ? "border-destructive" : ""}
            disabled={isSubmitting}
          />
          {errors.player1 && (
            <p className="text-xs text-destructive">{errors.player1}</p>
          )}
        </div>

        {/* Player 2 Score */}
        <div className="space-y-2">
          <Label htmlFor="player2-score" className="text-sm">
            {team2Name}
          </Label>
          <Input
            id="player2-score"
            type="text"
            inputMode="numeric"
            value={player2Score}
            onChange={(e) => handleScoreChange("player2", e.target.value)}
            placeholder="0"
            className={errors.player2 ? "border-destructive" : ""}
            disabled={isSubmitting}
          />
          {errors.player2 && (
            <p className="text-xs text-destructive">{errors.player2}</p>
          )}
        </div>
      </div>

      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Submitting..." : "Submit Scores"}
      </Button>
    </form>
  )
}
