import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface SuperspinRequestDialogProps {
  open: boolean
  proposerName?: string
  onAccept: () => void
  onDecline: () => void
  onOpenChange?: (open: boolean) => void
}

export function SuperspinRequestDialog({
  open,
  proposerName = "Opponent",
  onAccept,
  onDecline,
  onOpenChange,
}: SuperspinRequestDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Superspin Request</DialogTitle>
          <DialogDescription>
            {proposerName} is requesting a superspin. If you accept, they will
            get a superspin for this round.
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
