import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface MutualSuperspinDialogProps {
  /** Whether the dialog is open */
  open: boolean
  /** Name of the player who proposed the mutual superspin */
  proposerName?: string
  /** Callback when the player accepts */
  onAccept: () => void
  /** Callback when the player declines */
  onDecline: () => void
  /** Callback when dialog open state changes */
  onOpenChange?: (open: boolean) => void
}

/**
 * MutualSuperspinDialog shows when the opponent proposes a mutual superspin.
 * Allows the player to accept or decline the proposal.
 */
export function MutualSuperspinDialog({
  open,
  proposerName = "Opponent",
  onAccept,
  onDecline,
  onOpenChange,
}: MutualSuperspinDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Mutual Superspin Proposal</DialogTitle>
          <DialogDescription>
            {proposerName} wants to use a mutual superspin. This will reset both
            teams and spin again for everyone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onDecline}>
            Decline
          </Button>
          <Button onClick={onAccept}>Accept</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
