'use client'

import { useState, useRef } from 'react'
import { Send } from 'lucide-react'

type ChatMessage = { role: 'user' | 'assistant'; text: string }

type GameTurnState = {
  template_id: string | null
  phase: 'new' | 'awaiting_clarification' | 'ready'
  summary: string
  pending_question: string | null
  generated_code: string | null
  recent_messages: ChatMessage[]
}

const INITIAL_STATE: GameTurnState = {
  template_id: null,
  phase: 'new',
  summary: '',
  pending_question: null,
  generated_code: null,
  recent_messages: [],
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [gameState, setGameState] = useState<GameTurnState>(INITIAL_STATE)
  const [gameHtml, setGameHtml] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: ChatMessage = { role: 'user', text }
    const nextMessages = [...messages, userMsg]
    const nextRecent = [...gameState.recent_messages, userMsg].slice(-6)

    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setError(null)

    const requestState: GameTurnState = { ...gameState, recent_messages: nextRecent }

    try {
      const res = await fetch(`${API_URL}/game-turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, state: requestState }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Request failed (${res.status})`)
      }

      const data = await res.json()
      const assistantMsg: ChatMessage = { role: 'assistant', text: data.message }

      setMessages(prev => [...prev, assistantMsg])
      setGameState({
        ...data.state,
        recent_messages: [...(data.state.recent_messages ?? []), assistantMsg].slice(-6),
      })

      if (data.type === 'game' && data.html) {
        setGameHtml(data.html)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="h-screen bg-slate-950 text-slate-100 flex flex-col overflow-hidden">

      {/* Header */}
      <header className="shrink-0 border-b border-slate-800 px-5 py-3 flex items-center gap-3">
        <span className="text-lg font-bold text-white">ConYard</span>
        <span className="text-slate-500 text-sm">AI Game Studio</span>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left: conversation panel ── */}
        <div className="w-80 shrink-0 flex flex-col border-r border-slate-800">

          {/* Message history */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <p className="text-slate-500 text-sm text-center mt-10 px-4">
                Describe a game idea to get started.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[88%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-blue-600 text-white rounded-br-sm'
                      : 'bg-slate-800 text-slate-200 rounded-bl-sm'
                  }`}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-slate-800 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-slate-400">
                  <span className="inline-flex gap-1">
                    <span className="animate-bounce" style={{ animationDelay: '0ms' }}>·</span>
                    <span className="animate-bounce" style={{ animationDelay: '150ms' }}>·</span>
                    <span className="animate-bounce" style={{ animationDelay: '300ms' }}>·</span>
                  </span>
                </div>
              </div>
            )}
            {error && (
              <div className="text-red-400 bg-red-950/50 rounded-lg px-3 py-2 text-xs border border-red-800">
                {error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="shrink-0 p-3 border-t border-slate-800">
            <div className="flex gap-2 items-end">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Describe your game idea…"
                disabled={loading}
                rows={2}
                className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-100 placeholder-slate-500 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className="shrink-0 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:cursor-not-allowed rounded-xl p-2.5 transition-colors"
                aria-label="Send"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="text-slate-600 text-xs mt-1.5 text-center">Enter to send · Shift+Enter for newline</p>
          </div>
        </div>

        {/* ── Right: game renderer ── */}
        <div className="flex-1 bg-slate-900 flex items-center justify-center overflow-hidden">
          {gameHtml ? (
            <iframe
              key={gameHtml}
              srcDoc={gameHtml}
              sandbox="allow-scripts"
              className="w-full h-full border-0"
              title="Game preview"
            />
          ) : (
            <div className="text-center text-slate-600 select-none">
              <div className="text-5xl mb-4">🎮</div>
              <p className="text-base font-medium">Your game will appear here.</p>
              <p className="text-sm mt-1">Describe an idea in the chat to get started.</p>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
