import { useMutation } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useState } from "react"

import { FifotecaService } from "@/client"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import useFifotecaPlayer from "@/hooks/useFifotecaPlayer"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/fifoteca/")({
  component: FifotecaHomePage,
  head: () => ({
    meta: [
      {
        title: "Fifoteca - FastAPI Template",
      },
    ],
  }),
})

const ROOM_CODE_REGEX = /^[A-Z0-9]{6}$/

function FifotecaHomePage() {
  const navigate = useNavigate()
  const { player, isLoading: isPlayerLoading } = useFifotecaPlayer()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [joinCode, setJoinCode] = useState("")

  // Create room mutation
  const createRoomMutation = useMutation({
    mutationFn: () => FifotecaService.createRoom({}),
    onSuccess: (room) => {
      showSuccessToast("Room created successfully")
      navigate({
        to: "/fifoteca/lobby/$roomCode",
        params: { roomCode: room.code },
      })
    },
    onError: handleError.bind(showErrorToast),
  })

  // Join room mutation
  const joinRoomMutation = useMutation({
    mutationFn: (code: string) => FifotecaService.joinRoom({ code }),
    onSuccess: (room) => {
      showSuccessToast("Joined room successfully")
      navigate({
        to: "/fifoteca/lobby/$roomCode",
        params: { roomCode: room.code },
      })
    },
    onError: handleError.bind(showErrorToast),
  })

  // Handle join code input - normalize to uppercase and strip invalid chars
  const handleJoinCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "")
    if (value.length <= 6) {
      setJoinCode(value)
    }
  }

  // Handle join room submission
  const handleJoinRoom = () => {
    if (!ROOM_CODE_REGEX.test(joinCode)) {
      showErrorToast("Room code must be 6 uppercase letters or numbers")
      return
    }
    joinRoomMutation.mutate(joinCode)
  }

  // Handle Enter key in join input
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleJoinRoom()
    }
  }

  const isPending = createRoomMutation.isPending || joinRoomMutation.isPending

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Fifoteca</h1>
        <p className="text-muted-foreground">
          Play FIFA with a friend using fair team selection
        </p>
      </div>

      {/* Player Stats */}
      <Card>
        <CardHeader>
          <CardTitle>Your Stats</CardTitle>
          <CardDescription>
            Your Fifoteca performance across all games
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isPlayerLoading ? (
            <div className="text-muted-foreground">Loading stats...</div>
          ) : player ? (
            <div className="flex gap-8">
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">
                  {player.total_wins}
                </div>
                <div className="text-sm text-muted-foreground">Wins</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-600">
                  {player.total_losses}
                </div>
                <div className="text-sm text-muted-foreground">Losses</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-yellow-600">
                  {player.total_draws}
                </div>
                <div className="text-sm text-muted-foreground">Draws</div>
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground">Unable to load stats</div>
          )}
        </CardContent>
      </Card>

      {/* Actions Grid */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Create Room Card */}
        <Card>
          <CardHeader>
            <CardTitle>Create a Room</CardTitle>
            <CardDescription>
              Start a new game room and invite a friend
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LoadingButton
              onClick={() => createRoomMutation.mutate()}
              loading={createRoomMutation.isPending}
              disabled={isPending}
              className="w-full"
            >
              Create Room
            </LoadingButton>
          </CardContent>
        </Card>

        {/* Join Room Card */}
        <Card>
          <CardHeader>
            <CardTitle>Join a Room</CardTitle>
            <CardDescription>
              Enter a 6-character room code to join
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                placeholder="ABC123"
                value={joinCode}
                onChange={handleJoinCodeChange}
                onKeyDown={handleKeyDown}
                className="font-mono uppercase"
                maxLength={6}
              />
              <LoadingButton
                onClick={handleJoinRoom}
                loading={joinRoomMutation.isPending}
                disabled={isPending || joinCode.length !== 6}
              >
                Join
              </LoadingButton>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
