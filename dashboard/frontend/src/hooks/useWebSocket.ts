import { useEffect, useRef, useCallback, useState } from 'react'
import { useAuth } from '../context/AuthContext'

interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

export function useWebSocket(onMessage: (data: WebSocketMessage) => void) {
  const { token } = useAuth()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>()
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/live?token=${encodeURIComponent(token)}`
    wsRef.current = new WebSocket(wsUrl)

    wsRef.current.onopen = () => {
      setConnected(true)
      const pingInterval = setInterval(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send('ping')
        }
      }, 30000)
      wsRef.current!.onclose = () => {
        clearInterval(pingInterval)
        setConnected(false)
        reconnectRef.current = setTimeout(connect, 3000)
      }
    }

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch {
        // ignore non-JSON messages
      }
    }

    wsRef.current.onerror = () => {
      wsRef.current?.close()
    }
  }, [onMessage, token])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { connected }
}
