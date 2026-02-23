import { useCallback, useEffect, useRef, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface SpinItem {
  id: string
  name: string
}

interface SpinDisplayProps {
  /** List of items to cycle through */
  items: SpinItem[]
  /** Whether the spin animation is active */
  spinning: boolean
  /** The final selected item to land on */
  selectedItem: SpinItem | null
  /** Whether the result is locked in */
  locked?: boolean
  /** Optional label for the display */
  label?: string
  /** Additional CSS classes */
  className?: string
}

/**
 * SpinDisplay component that shows a cycling animation through items
 * and lands on the selected item.
 *
 * Animation phases:
 * 1. Rapid cycling (~80ms intervals for ~15 cycles)
 * 2. Deceleration phase with increasing delays
 * 3. Stop on selected item
 */
export function SpinDisplay({
  items,
  spinning,
  selectedItem,
  locked = false,
  label,
  className,
}: SpinDisplayProps) {
  const [displayItem, setDisplayItem] = useState<SpinItem | null>(null)
  const [isAnimating, setIsAnimating] = useState(false)
  const animationRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cycleCountRef = useRef(0)
  const phaseRef = useRef<"rapid" | "decelerate" | "done">("done")

  // Keep selectedItem in a ref so the animation effect doesn't re-run
  // when the object reference changes (which happens on every cache update,
  // even unrelated ones like turn_changed). The ref is always current.
  const selectedItemRef = useRef(selectedItem)
  selectedItemRef.current = selectedItem

  // Get a random item from the list
  const getRandomItem = useCallback((): SpinItem | null => {
    if (items.length === 0) return null
    const array = new Uint32Array(1)
    crypto.getRandomValues(array)
    const idx = array[0]! % items.length
    return items[idx] ?? null
  }, [items])

  // Clear any pending animation
  const clearAnimation = useCallback(() => {
    if (animationRef.current) {
      clearTimeout(animationRef.current)
      animationRef.current = null
    }
  }, [])

  // Main animation effect — only depends on spinning and items.length.
  // selectedItem is read from ref to avoid re-running (and killing the
  // animation via cleanup) on every object reference change.
  useEffect(() => {
    // Handle empty items
    if (items.length === 0) {
      clearAnimation()
      setIsAnimating(false)
      phaseRef.current = "done"
      setDisplayItem(selectedItemRef.current ?? null)
      return
    }

    // Start spinning
    if (spinning && !isAnimating) {
      setIsAnimating(true)
      phaseRef.current = "rapid"
      cycleCountRef.current = 0

      const runRapidPhase = () => {
        if (cycleCountRef.current < 15) {
          setDisplayItem(getRandomItem())
          cycleCountRef.current++
          animationRef.current = setTimeout(runRapidPhase, 80)
        } else {
          phaseRef.current = "decelerate"
          runDeceleratePhase(150)
        }
      }

      const runDeceleratePhase = (delay: number) => {
        setDisplayItem(getRandomItem())
        animationRef.current = setTimeout(() => {
          if (delay < 400) {
            runDeceleratePhase(delay + 50)
          } else {
            // Final stop — read latest selectedItem from ref
            phaseRef.current = "done"
            setIsAnimating(false)
            setDisplayItem(selectedItemRef.current ?? getRandomItem())
          }
        }, delay)
      }

      runRapidPhase()
      return
    }

    // When spinning stops, forcibly end any in-progress animation and show
    // the selected item from the cache (source of truth).
    if (!spinning && isAnimating) {
      clearAnimation()
      setIsAnimating(false)
      phaseRef.current = "done"
      setDisplayItem(selectedItemRef.current ?? null)
    }

    return () => {
      clearAnimation()
    }
    // NOTE: selectedItem is intentionally NOT in deps — it's read from
    // selectedItemRef to prevent the effect from re-running (and killing
    // the animation via cleanup) on every object reference change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spinning, items.length, isAnimating, getRandomItem, clearAnimation])

  // Sync display when selectedItem changes while not spinning/animating.
  // This handles: initial load, lock results, state_sync after reconnect.
  useEffect(() => {
    if (!spinning && !isAnimating && selectedItem) {
      setDisplayItem(selectedItem)
    }
  }, [selectedItem, spinning, isAnimating])

  // Reset display when items change and nothing is selected
  useEffect(() => {
    if (!spinning && !isAnimating && items.length > 0 && !selectedItem) {
      setDisplayItem(items[0] ?? null)
    }
  }, [items, spinning, isAnimating, selectedItem])

  return (
    <Card
      className={cn(
        "transition-all duration-300",
        locked && "bg-muted/50 border-primary/50",
        className,
      )}
    >
      {label && (
        <div className="px-4 pt-4">
          <span className="text-sm font-medium text-muted-foreground">
            {label}
          </span>
        </div>
      )}
      <CardContent className={cn("py-8", label && "pt-2")}>
        <div
          className={cn(
            "text-center text-2xl font-bold min-h-[3rem] flex items-center justify-center",
            isAnimating && "animate-pulse",
            locked && "text-primary",
          )}
        >
          {displayItem?.name ?? (
            <span className="text-muted-foreground">No items</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
