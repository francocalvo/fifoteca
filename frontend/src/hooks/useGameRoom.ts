import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useMemo, useRef, useState } from "react"
import useWebSocket, { ReadyState } from "react-use-websocket"

/**
 * WebSocket message envelope type - all messages follow this format
 */
export interface WSMessage {
  type: string
  payload?: unknown
}

/**
 * Game snapshot from state_sync message
 * Contains nested room + player_states
 */
interface GameSnapshot {
  room: {
    id: string
    code: string
    ruleset: string
    status: string
    player1_id: string
    player2_id: string | null
    current_turn_player_id: string | null
    first_player_id: string | null
    round_number: number
    mutual_superspin_active: boolean
    expires_at: string
    created_at: string | null
    mutual_superspin_proposer_id?: string | null
    match_id?: string | null
  }
  player_states: Array<{
    id: string
    room_id: string
    player_id: string
    display_name: string | null
    round_number: number
    phase: string
    league_spins_remaining: number
    team_spins_remaining: number
    current_league_id: string | null
    current_team_id: string | null
    current_league: {
      id: string
      name: string
      country: string
    } | null
    current_team: {
      id: string
      name: string
      league_id: string
      attack_rating: number
      midfield_rating: number
      defense_rating: number
      overall_rating: number
    } | null
    league_locked: boolean
    team_locked: boolean
    has_superspin: boolean
    superspin_used: boolean
    has_parity_spin: boolean
    parity_spin_used: boolean
    created_at: string | null
  }>
  rating_review?: {
    p1_team?: {
      id: string
      name: string
      overall_rating: number
      attack_rating: number
      midfield_rating: number
      defense_rating: number
      league_id: string
    }
    p2_team?: {
      id: string
      name: string
      overall_rating: number
      attack_rating: number
      midfield_rating: number
      defense_rating: number
      league_id: string
    }
    difference: number
    protection_awarded_to_id: string | null
    parity_available_to_id: string | null
    superspin_available_to_id: string | null
  }
}

/**
 * Payload types for specific message types
 */
interface SpinResultPayload {
  player_id: string
  type: "league" | "team"
  result: unknown
  spins_remaining?: number // Optional: special spins (superspin/parity) don't include this
  was_fallback?: boolean // Present only for superspin/parity spin actions
  auto_locked?: boolean // Whether the team was auto-locked (superspin)
}

interface LockResultPayload {
  player_id: string
  type: "league" | "team"
  locked: unknown
}

interface TurnChangedPayload {
  current_turn_player_id: string
}

interface PhaseChangedPayload {
  phase: string
  room_status: string
  match_id?: string | null
}

interface PlayerConnectionPayload {
  player_id: string
}

interface ErrorPayload {
  code: string
  message: string
}

/**
 * Union of all valid action types for sendAction
 */
export type GameActionType =
  | "spin_league"
  | "lock_league"
  | "spin_team"
  | "lock_team"
  | "use_superspin"
  | "use_parity_spin"
  | "propose_mutual_superspin"
  | "accept_mutual_superspin"
  | "decline_mutual_superspin"
  | "ready_to_play"
  | "ping"
  | "play_again"
  | "leave"
  | "leave_room"

/**
 * WebSocket close codes indicating terminal errors (no reconnect)
 */
const TERMINAL_CLOSE_CODES = [4001, 4002, 4003]

/**
 * Room expiry close code
 */
const ROOM_EXPIRED_CLOSE_CODE = 4002

/**
 * Process a single incoming WebSocket message and update React Query cache.
 * Extracted as a standalone function so it can be called from onMessage
 * (which fires for every message, unlike lastJsonMessage + useEffect which
 * can batch/skip rapid messages).
 */
function processWsMessage(
  message: WSMessage,
  roomCode: string,
  queryClient: QueryClient,
) {
  const cacheKey = ["room", roomCode] as const

  switch (message.type) {
    case "state_sync": {
      const snapshot = message.payload as GameSnapshot
      queryClient.setQueryData(cacheKey, snapshot)
      break
    }

    case "turn_changed": {
      const payload = message.payload as TurnChangedPayload
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          room: {
            ...old.room,
            current_turn_player_id: payload.current_turn_player_id,
          },
        }
      })
      break
    }

    case "phase_changed": {
      const payload = message.payload as PhaseChangedPayload
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          room: {
            ...old.room,
            status: payload.room_status,
            match_id: payload.match_id ?? old.room.match_id,
          },
        }
      })
      break
    }

    case "spin_result": {
      const payload = message.payload as SpinResultPayload
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          player_states: old.player_states.map((state) => {
            if (state.player_id !== payload.player_id) return state
            const result = payload.result as Record<string, unknown>
            return {
              ...state,
              current_league_id:
                payload.type === "league"
                  ? ((result?.id as string) ?? state.current_league_id)
                  : state.current_league_id,
              current_team_id:
                payload.type === "team"
                  ? ((result?.id as string) ?? state.current_team_id)
                  : state.current_team_id,
              current_league:
                payload.type === "league" && result
                  ? (result as unknown as GameSnapshot["player_states"][0]["current_league"])
                  : state.current_league,
              current_team:
                payload.type === "team" && result
                  ? (result as unknown as GameSnapshot["player_states"][0]["current_team"])
                  : state.current_team,
              league_spins_remaining:
                payload.type === "league" &&
                payload.spins_remaining !== undefined
                  ? payload.spins_remaining
                  : state.league_spins_remaining,
              team_spins_remaining:
                payload.type === "team" &&
                payload.spins_remaining !== undefined
                  ? payload.spins_remaining
                  : state.team_spins_remaining,
              league_locked:
                payload.type === "league" && payload.auto_locked
                  ? true
                  : state.league_locked,
              team_locked:
                payload.type === "team" && payload.auto_locked
                  ? true
                  : state.team_locked,
              superspin_used:
                payload.auto_locked &&
                payload.spins_remaining === undefined
                  ? true
                  : state.superspin_used,
            }
          }),
        }
      })
      break
    }

    case "lock_result": {
      const payload = message.payload as LockResultPayload
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          player_states: old.player_states.map((state) => {
            if (state.player_id !== payload.player_id) return state
            return {
              ...state,
              league_locked:
                payload.type === "league" ? true : state.league_locked,
              team_locked: payload.type === "team" ? true : state.team_locked,
            }
          }),
        }
      })
      break
    }

    case "rating_review": {
      const payload = message.payload as GameSnapshot["rating_review"]
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          rating_review: payload,
        }
      })
      break
    }

    case "player_connected":
    case "player_disconnected":
    case "player_left": {
      const payload = message.payload as PlayerConnectionPayload
      console.log(`[useGameRoom] ${message.type}:`, payload.player_id)
      break
    }

    case "score_submitted": {
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          room: {
            ...old.room,
            status: "SCORE_SUBMITTED",
          },
        }
      })
      break
    }

    case "match_result": {
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          room: {
            ...old.room,
            status: "COMPLETED",
          },
        }
      })
      break
    }

    case "mutual_superspin_proposed": {
      const payload = message.payload as { proposer_id: string }
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          room: {
            ...old.room,
            mutual_superspin_proposer_id: payload.proposer_id,
          },
        }
      })
      break
    }

    case "mutual_superspin_declined": {
      queryClient.setQueryData<GameSnapshot>(cacheKey, (old) => {
        if (!old) return old
        return {
          ...old,
          room: {
            ...old.room,
            mutual_superspin_proposer_id: null,
          },
        }
      })
      break
    }

    case "mutual_superspin_accepted": {
      queryClient.invalidateQueries({ queryKey: cacheKey })
      break
    }

    case "error": {
      const payload = message.payload as ErrorPayload
      console.error(
        `[useGameRoom] Server error: ${payload.code} - ${payload.message}`,
      )
      break
    }

    default:
      break
  }
}

/**
 * Hook to manage WebSocket connection to a Fifoteca game room.
 *
 * Connects to the backend WebSocket endpoint, routes incoming messages to React Query cache,
 * and exposes a typed action sender + connection state.
 *
 * @param roomCode - The 6-character room code to connect to
 * @returns Hook state and actions
 * @returns sendAction - Send a typed game action to the server
 * @returns isConnected - Whether the WebSocket is currently connected
 * @returns gameState - The current game snapshot from React Query cache
 * @returns lastMessage - The last received message envelope
 */
const useGameRoom = (
  roomCode: string | undefined,
  onMessageCallback?: (message: WSMessage) => void,
) => {
  const queryClient = useQueryClient()
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 10

  // Track last close event for expiry detection
  const [lastCloseCode, setLastCloseCode] = useState<number | null>(null)

  // Normalize room code (uppercase, trimmed)
  const normalizedRoomCode = useMemo(() => {
    if (!roomCode) return null
    return roomCode.trim().toUpperCase()
  }, [roomCode])

  // Get auth token from localStorage
  const token = useMemo(() => {
    if (typeof window === "undefined") return null
    return localStorage.getItem("access_token")
  }, [])

  // Build WebSocket URL from VITE_API_URL
  const socketUrl = useMemo(() => {
    if (!normalizedRoomCode || !token) return null

    const apiUrl = import.meta.env.VITE_API_URL || ""
    // Convert http/https to ws/wss
    const wsProtocol = apiUrl.startsWith("https") ? "wss" : "ws"
    const wsHost = apiUrl.replace(/^https?:\/\//, "")

    return `${wsProtocol}://${wsHost}/api/v1/fifoteca/ws/${normalizedRoomCode}?token=${token}`
  }, [normalizedRoomCode, token])

  // Exponential backoff calculation for reconnect
  const getReconnectInterval = useCallback(() => {
    const baseInterval = 1000 // 1 second
    const maxInterval = 30000 // 30 seconds
    const interval = Math.min(
      baseInterval * 2 ** reconnectAttempts.current,
      maxInterval,
    )
    // Add jitter to prevent thundering herd
    return interval + Math.random() * 1000
  }, [])

  // Refs to keep onMessage callback stable while accessing current values
  const queryClientRef = useRef(queryClient)
  queryClientRef.current = queryClient
  const normalizedRoomCodeRef = useRef(normalizedRoomCode)
  normalizedRoomCodeRef.current = normalizedRoomCode
  const onMessageCallbackRef = useRef(onMessageCallback)
  onMessageCallbackRef.current = onMessageCallback

  // WebSocket connection options
  const { sendJsonMessage, lastJsonMessage, readyState } =
    useWebSocket<WSMessage>(socketUrl ?? null, {
      // Exponential backoff reconnect
      reconnectAttempts: maxReconnectAttempts,
      reconnectInterval: getReconnectInterval,

      // Only reconnect for non-terminal close codes
      shouldReconnect: (closeEvent) => {
        // Don't reconnect for terminal close codes (auth errors, expired rooms)
        if (TERMINAL_CLOSE_CODES.includes(closeEvent.code)) {
          return false
        }
        // Don't reconnect if we've exceeded max attempts
        if (reconnectAttempts.current >= maxReconnectAttempts) {
          return false
        }
        reconnectAttempts.current++
        return true
      },

      // Heartbeat: send ping every 30 seconds
      heartbeat: {
        message: JSON.stringify({ type: "ping", payload: {} }),
        returnMessage: "pong",
        timeout: 60000, // Wait 60s for pong before considering dead
        interval: 30000, // Send ping every 30s
      },

      // Filter out pong messages from lastJsonMessage (we don't need to process them)
      filter: (message) => {
        try {
          const data = JSON.parse(message.data)
          return data.type !== "pong"
        } catch {
          return true
        }
      },

      // Process every incoming message immediately via onMessage.
      // This avoids the batching issue with lastJsonMessage + useEffect,
      // where rapid back-to-back messages (e.g. player_connected + state_sync)
      // can be collapsed into a single React render, skipping intermediate messages.
      onMessage: (event) => {
        const code = normalizedRoomCodeRef.current
        if (!code) return
        try {
          const data = JSON.parse(event.data) as WSMessage
          if (data.type === "pong") return
          processWsMessage(data, code, queryClientRef.current)
          onMessageCallbackRef.current?.(data)
        } catch {
          // Ignore non-JSON messages
        }
      },

      // Reset reconnect attempts on successful connection
      onOpen: () => {
        reconnectAttempts.current = 0
      },

      // Handle close events
      onClose: (event) => {
        // Track close code for expiry detection
        setLastCloseCode(event.code)

        if (TERMINAL_CLOSE_CODES.includes(event.code)) {
          console.warn(
            `[useGameRoom] Terminal close: ${event.code} - ${event.reason}`,
          )
        }
      },

      // Handle errors
      onError: (event) => {
        console.error("[useGameRoom] WebSocket error:", event)
      },
    })

  // Track last message for consumer access
  const lastMessage = lastJsonMessage

  // Send action helper
  const sendAction = useCallback(
    (type: GameActionType, payload: Record<string, unknown> = {}) => {
      if (readyState !== ReadyState.OPEN) {
        console.warn(
          `[useGameRoom] Cannot send action: not connected (state=${readyState})`,
        )
        return
      }
      sendJsonMessage({ type, payload })
    },
    [sendJsonMessage, readyState],
  )

  // Subscribe to game state in React Query cache.
  // processWsMessage writes to this cache key via setQueryData, and useQuery
  // subscribes to changes, ensuring the component re-renders on each update.
  const { data: gameState } = useQuery<GameSnapshot>({
    queryKey: normalizedRoomCode
      ? ["room", normalizedRoomCode]
      : ["room", "__disabled__"],
    queryFn: () => Promise.reject(new Error("WS-only cache")),
    enabled: false,
    staleTime: Infinity,
  })

  // isConnected helper
  const isConnected = readyState === ReadyState.OPEN

  // isReconnecting: true when not connected (connecting, closing, closed)
  const isReconnecting = readyState !== ReadyState.OPEN

  // isRoomExpired: true if closed with code 4002
  const isRoomExpired = lastCloseCode === ROOM_EXPIRED_CLOSE_CODE

  return {
    sendAction,
    isConnected,
    gameState,
    lastMessage,
    readyState,
    isReconnecting,
    isRoomExpired,
  }
}

export default useGameRoom
