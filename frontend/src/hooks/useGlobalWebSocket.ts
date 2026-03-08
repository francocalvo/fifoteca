import { useCallback, useMemo, useRef } from "react"
import useWebSocket, { ReadyState } from "react-use-websocket"

export interface GlobalWSMessage {
  type: string
  payload?: Record<string, unknown>
}

export interface InviteReceived {
  invite_id: string
  room_code: string
  inviter_display_name: string
  expires_in: number
}

const useGlobalWebSocket = (
  onMessageCallback?: (message: GlobalWSMessage) => void,
) => {
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 10

  const token = useMemo(() => {
    if (typeof window === "undefined") return null
    return localStorage.getItem("access_token")
  }, [])

  const socketUrl = useMemo(() => {
    if (!token) return null
    const apiUrl = import.meta.env.VITE_API_URL || ""
    const wsProtocol = apiUrl.startsWith("https") ? "wss" : "ws"
    const wsHost = apiUrl.replace(/^https?:\/\//, "")
    return `${wsProtocol}://${wsHost}/api/v1/fifoteca/ws/global?token=${token}`
  }, [token])

  const onMessageCallbackRef = useRef(onMessageCallback)
  onMessageCallbackRef.current = onMessageCallback

  const { sendJsonMessage, readyState } = useWebSocket<GlobalWSMessage>(
    socketUrl,
    {
      reconnectAttempts: maxReconnectAttempts,
      reconnectInterval: () => {
        const base = 1000
        const max = 30000
        const interval = Math.min(base * 2 ** reconnectAttempts.current, max)
        return interval + Math.random() * 1000
      },

      shouldReconnect: (closeEvent) => {
        if ([4001].includes(closeEvent.code)) return false
        if (reconnectAttempts.current >= maxReconnectAttempts) return false
        reconnectAttempts.current++
        return true
      },

      heartbeat: {
        message: JSON.stringify({ type: "ping", payload: {} }),
        returnMessage: "pong",
        timeout: 60000,
        interval: 30000,
      },

      filter: (message) => {
        try {
          const data = JSON.parse(message.data)
          return data.type !== "pong"
        } catch {
          return true
        }
      },

      onMessage: (event) => {
        try {
          const data = JSON.parse(event.data) as GlobalWSMessage
          if (data.type === "pong") return
          onMessageCallbackRef.current?.(data)
        } catch {
          // Ignore non-JSON
        }
      },

      onOpen: () => {
        reconnectAttempts.current = 0
      },
    },
  )

  const sendMessage = useCallback(
    (type: string, payload: Record<string, unknown> = {}) => {
      if (readyState !== ReadyState.OPEN) return
      sendJsonMessage({ type, payload })
    },
    [sendJsonMessage, readyState],
  )

  const isConnected = readyState === ReadyState.OPEN

  return { sendMessage, isConnected }
}

export default useGlobalWebSocket
