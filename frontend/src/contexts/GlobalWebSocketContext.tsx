import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useState,
} from "react"

import useGlobalWebSocket, {
  type GlobalWSMessage,
  type InviteReceived,
} from "@/hooks/useGlobalWebSocket"

interface GlobalWebSocketContextValue {
  sendMessage: (type: string, payload?: Record<string, unknown>) => void
  isConnected: boolean
  pendingInvite: InviteReceived | null
  setPendingInvite: (invite: InviteReceived | null) => void
  lastGlobalMessage: GlobalWSMessage | null
}

const GlobalWebSocketContext = createContext<GlobalWebSocketContextValue>({
  sendMessage: () => {},
  isConnected: false,
  pendingInvite: null,
  setPendingInvite: () => {},
  lastGlobalMessage: null,
})

export function useGlobalWS() {
  return useContext(GlobalWebSocketContext)
}

export function GlobalWebSocketProvider({ children }: { children: ReactNode }) {
  const [pendingInvite, setPendingInvite] = useState<InviteReceived | null>(
    null,
  )
  const [lastGlobalMessage, setLastGlobalMessage] =
    useState<GlobalWSMessage | null>(null)

  const onMessage = useCallback((message: GlobalWSMessage) => {
    setLastGlobalMessage(message)

    if (message.type === "invite_received") {
      const payload = message.payload as unknown as InviteReceived
      setPendingInvite(payload)
    }

    if (
      message.type === "invite_expired" ||
      message.type === "join_room_redirect"
    ) {
      setPendingInvite(null)
    }
  }, [])

  const { sendMessage, isConnected } = useGlobalWebSocket(onMessage)

  return (
    <GlobalWebSocketContext.Provider
      value={{
        sendMessage,
        isConnected,
        pendingInvite,
        setPendingInvite,
        lastGlobalMessage,
      }}
    >
      {children}
    </GlobalWebSocketContext.Provider>
  )
}
