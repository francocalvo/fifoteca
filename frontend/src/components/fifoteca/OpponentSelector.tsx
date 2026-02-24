import { useQuery } from "@tanstack/react-query"

import { FifotecaService } from "@/client"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useFifotecaPlayer from "@/hooks/useFifotecaPlayer"

interface OpponentSelectorProps {
  value: string | undefined
  onChange: (opponentId: string) => void
}

export function OpponentSelector({ value, onChange }: OpponentSelectorProps) {
  const { player } = useFifotecaPlayer()
  const { data: players, isLoading } = useQuery({
    queryKey: ["fifoteca", "players"],
    queryFn: () => FifotecaService.listPlayers(),
  })

  const opponents = players?.filter((p) => p.id !== player?.id) ?? []

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full sm:w-[280px]">
        <SelectValue
          placeholder={isLoading ? "Loading players..." : "Select an opponent"}
        />
      </SelectTrigger>
      <SelectContent>
        {opponents.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.display_name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
