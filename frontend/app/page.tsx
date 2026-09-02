'use client'

import { useEffect, useRef, useState } from 'react'
import {
  Bird,
  Check,
  Expand,
  Gamepad2,
  MessageSquare,
  Plus,
  Rat,
  RotateCcw,
  Send,
  Sparkles,
} from 'lucide-react'

type ChatMessage = { role: 'user' | 'assistant'; text: string }
type EditSuggestion = { kind: 'edit' | 'complete'; text: string }

type GameTurnState = {
  template_id: string | null
  phase: 'new' | 'awaiting_clarification' | 'ready'
  summary: string
  pending_question: string | null
  generated_code: string | null
  interaction_id: string | null
}

const INITIAL_STATE: GameTurnState = {
  template_id: null,
  phase: 'new',
  summary: '',
  pending_question: null,
  generated_code: null,
  interaction_id: null,
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const GAME_STARTERS = [
  {
    name: 'Snake',
    description: 'A quick arcade classic',
    prompt: 'Make a neon snake game with glowing food and a dark grid.',
    icon: Rat,
    accent: 'from-cyan-400/20 to-cyan-400/[0.02] text-cyan-300 border-cyan-400/30 hover:border-cyan-300/70 hover:shadow-[0_0_28px_rgba(34,211,238,0.15)]',
  },
  {
    name: 'Flappy Bird',
    description: 'One-button endless flight',
    prompt: 'Make a cozy sunset Flappy Bird game with candy-colored pipes.',
    icon: Bird,
    accent: 'from-fuchsia-500/20 to-fuchsia-500/[0.02] text-fuchsia-300 border-fuchsia-500/30 hover:border-fuchsia-300/70 hover:shadow-[0_0_28px_rgba(217,70,239,0.15)]',
  },
  {
    name: 'Pac-Man',
    description: 'A fast maze adventure',
    prompt: 'Make a cosmic Pac-Man game with a midnight maze and colorful ghosts.',
    icon: Gamepad2,
    accent: 'from-violet-500/20 to-violet-500/[0.02] text-violet-300 border-violet-500/30 hover:border-violet-300/70 hover:shadow-[0_0_28px_rgba(139,92,246,0.15)]',
  },
]

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [gameState, setGameState] = useState<GameTurnState>(INITIAL_STATE)
  const [gameHtml, setGameHtml] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const starterPromptsRequested = useRef(false)
  const [starterPrompts, setStarterPrompts] = useState<string[]>([])
  const [starterPromptsLoading, setStarterPromptsLoading] = useState(true)
  const [activeMobilePanel, setActiveMobilePanel] = useState<'chat' | 'preview'>('chat')
  const [chatWidth, setChatWidth] = useState(420)
  const [isResizing, setIsResizing] = useState(false)
  const [previewKey, setPreviewKey] = useState(0)
  const previewRef = useRef<HTMLDivElement>(null)
  const suggestionRequestId = useRef(0)
  const [editSuggestions, setEditSuggestions] = useState<EditSuggestion[]>([])
  const [editSuggestionsLoading, setEditSuggestionsLoading] = useState(false)
  const [editSuggestionsError, setEditSuggestionsError] = useState(false)

  useEffect(() => {
    if (starterPromptsRequested.current) return
    starterPromptsRequested.current = true

    const loadStarterPrompts = async () => {
      try {
        const res = await fetch(`${API_URL}/starter-prompts`)
        if (!res.ok) throw new Error(`Request failed (${res.status})`)

        const data = await res.json()
        if (Array.isArray(data.prompts)) {
          setStarterPrompts(data.prompts.filter((prompt: unknown) => typeof prompt === 'string'))
        }
      } catch {
        // The composer remains fully usable when suggestions are unavailable.
      } finally {
        setStarterPromptsLoading(false)
      }
    }

    loadStarterPrompts()
  }, [])

  useEffect(() => {
    if (!isResizing) return

    const handlePointerMove = (event: PointerEvent) => {
      const maxWidth = Math.max(360, Math.min(560, window.innerWidth - 320))
      setChatWidth(Math.min(maxWidth, Math.max(320, event.clientX)))
    }
    const stopResizing = () => setIsResizing(false)

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResizing)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResizing)
    }
  }, [isResizing])

  const loadEditSuggestions = async (state: GameTurnState) => {
    const requestId = ++suggestionRequestId.current
    setEditSuggestions([])
    setEditSuggestionsError(false)
    setEditSuggestionsLoading(true)

    try {
      const res = await fetch(`${API_URL}/edit-suggestions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state }),
      })
      if (!res.ok) throw new Error(`Request failed (${res.status})`)

      const data = await res.json()
      if (requestId === suggestionRequestId.current && Array.isArray(data.suggestions)) {
        setEditSuggestions(
          data.suggestions.filter(
            (item: unknown): item is EditSuggestion =>
              typeof item === 'object' &&
              item !== null &&
              ('kind' in item) &&
              ((item as EditSuggestion).kind === 'edit' || (item as EditSuggestion).kind === 'complete') &&
              typeof (item as EditSuggestion).text === 'string',
          ),
        )
      }
    } catch {
      if (requestId === suggestionRequestId.current) {
        setEditSuggestionsError(true)
      }
    } finally {
      if (requestId === suggestionRequestId.current) {
        setEditSuggestionsLoading(false)
      }
    }
  }

  const sendMessage = async (suggestedText?: string) => {
    const text = (suggestedText ?? input).trim()
    if (!text || loading) return

    const userMsg: ChatMessage = { role: 'user', text }
    const nextMessages = [...messages, userMsg]

    suggestionRequestId.current += 1
    setEditSuggestions([])
    setEditSuggestionsLoading(false)
    setEditSuggestionsError(false)
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${API_URL}/game-turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, state: gameState }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `Request failed (${res.status})`)
      }

      const data = await res.json()
      const assistantMsg: ChatMessage = { role: 'assistant', text: data.message }

      const nextState: GameTurnState = data.state
      setMessages(prev => [...prev, assistantMsg])
      setGameState(nextState)

      if (data.type === 'game' && data.html) {
        setGameHtml(data.html)
        setActiveMobilePanel('preview')
        void loadEditSuggestions(nextState)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    }
  }

  const startNewGame = () => {
    suggestionRequestId.current += 1
    setEditSuggestions([])
    setEditSuggestionsLoading(false)
    setEditSuggestionsError(false)
    setMessages([])
    setGameState(INITIAL_STATE)
    setGameHtml(null)
    setInput('')
    setError(null)
    setActiveMobilePanel('chat')
  }

  const enterFullscreen = async () => {
    await previewRef.current?.requestFullscreen?.()
  }

  const gameTitle = gameState.template_id
    ? gameState.template_id.replace(/[-_]/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
    : 'Game preview'

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className={`h-[100dvh] min-h-0 w-full bg-[#050711] text-slate-100 flex flex-col overflow-hidden ${isResizing ? 'select-none cursor-col-resize' : ''}`}>

      {/* Header */}
      <header className="relative shrink-0 border-b border-cyan-400/20 bg-[#070914]/95 px-4 sm:px-5 py-3 flex items-center gap-3 after:absolute after:bottom-[-1px] after:left-0 after:h-px after:w-32 after:bg-cyan-300 after:shadow-[0_0_12px_#22d3ee]">
        <div className="cyber-panel cyber-pulse flex h-8 w-8 items-center justify-center border border-cyan-300/60 bg-gradient-to-br from-cyan-400/30 to-violet-600/30 text-cyan-200">
          <Gamepad2 size={17} />
        </div>
        <div className="leading-tight">
          <span className="block text-base font-black uppercase tracking-[0.08em] text-white">Con<span className="text-cyan-300">Yard</span></span>
          <span className="cyber-label hidden text-[9px] uppercase text-violet-300/70 sm:block">AI Game Studio</span>
        </div>
        <div className="ml-auto flex border border-slate-800 bg-[#0b0e1a] p-1 md:hidden">
          <button onClick={() => setActiveMobilePanel('chat')} className={`flex min-h-10 items-center gap-1.5 px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition ${activeMobilePanel === 'chat' ? 'bg-cyan-400/15 text-cyan-200' : 'text-slate-500'}`}>
            <MessageSquare size={14} /> Chat
          </button>
          <button onClick={() => setActiveMobilePanel('preview')} className={`flex min-h-10 items-center gap-1.5 px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition ${activeMobilePanel === 'preview' ? 'bg-cyan-400/15 text-cyan-200' : 'text-slate-500'}`}>
            <Gamepad2 size={14} /> Preview
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex min-h-0 flex-1 overflow-hidden">

        {/* ── Left: conversation panel ── */}
        <div
          className={`${activeMobilePanel === 'chat' ? 'flex' : 'hidden'} min-h-0 w-full shrink-0 flex-col border-r border-cyan-400/10 bg-[#070914] md:flex md:min-w-[320px] md:max-w-[calc(100vw-320px)] md:w-[var(--chat-width)]`}
          style={{ '--chat-width': `${chatWidth}px` } as React.CSSProperties}
        >

          {/* Message history */}
          <div className="flex-1 overscroll-contain overflow-y-auto p-3 sm:p-4 space-y-3">
            {messages.length === 0 && (
              <div className="mt-5 px-1">
                <div className="mb-5">
                  <p className="text-xl font-black uppercase tracking-tight text-white">What should we <span className="text-violet-400">build?</span></p>
                  <p className="mt-1 text-sm leading-relaxed text-slate-500">Choose a classic or describe your own idea below.</p>
                </div>
                <p className="cyber-label text-[9px] font-semibold uppercase text-cyan-400/60 mb-2.5">// Quick starts</p>
                <div className="space-y-2">
                  {starterPromptsLoading
                    ? Array.from({ length: 3 }).map((_, index) => (
                        <div
                          key={index}
                          className="h-12 border border-slate-800 bg-slate-900 animate-pulse"
                        />
                      ))
                    : starterPrompts.slice(0, 3).map(prompt => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => sendMessage(prompt)}
                          disabled={loading}
                          className="cyber-panel w-full min-h-12 border border-slate-700/80 bg-slate-900/70 hover:bg-cyan-400/[0.06] hover:border-cyan-400/50 px-3 py-2.5 text-left text-base leading-snug text-slate-300 transition-all disabled:opacity-50"
                        >
                          {prompt}
                        </button>
                      ))}
                </div>
                {!starterPromptsLoading && starterPrompts.length === 0 && (
                  <p className="text-slate-500 text-sm text-center mt-10 px-4">
                    Describe a game idea to get started.
                  </p>
                )}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[92%] break-words rounded-2xl px-3.5 py-2.5 text-base leading-relaxed sm:max-w-[88%] ${
                    m.role === 'user'
                      ? 'cyber-panel border border-violet-400/30 bg-violet-600/80 text-white shadow-[0_0_20px_rgba(124,58,237,0.12)]'
                      : 'cyber-panel border border-cyan-400/10 bg-[#111625] text-slate-200'
                  }`}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {!loading && gameState.phase === 'ready' && (editSuggestionsLoading || editSuggestions.length > 0 || editSuggestionsError) && (
              <div className="cyber-panel border border-cyan-400/20 bg-cyan-400/[0.03] p-3">
                <p className="cyber-label mb-2 text-[9px] font-semibold uppercase text-cyan-400/70">// Try next</p>
                <div className="space-y-1.5">
                  {editSuggestionsLoading
                    ? Array.from({ length: 3 }).map((_, index) => (
                        <div key={index} className="h-9 border border-slate-800 bg-slate-900 animate-pulse" />
                      ))
                    : editSuggestions.map((suggestion, index) => (
                        <button
                          key={`${suggestion.kind}-${index}-${suggestion.text}`}
                          type="button"
                          onClick={() => {
                            if (suggestion.kind === 'complete') {
                              suggestionRequestId.current += 1
                              setEditSuggestions([])
                            } else {
                              void sendMessage(suggestion.text)
                            }
                          }}
                          className={`flex min-h-11 w-full items-start gap-2 border px-3 py-2.5 text-left text-sm leading-snug transition-colors ${
                            suggestion.kind === 'complete'
                              ? 'border-emerald-400/20 text-emerald-300 hover:bg-emerald-400/[0.06]'
                              : 'border-slate-700/80 text-slate-300 hover:border-cyan-400/40 hover:bg-cyan-400/[0.05]'
                          }`}
                        >
                          {suggestion.kind === 'complete'
                            ? <Check size={14} className="mt-0.5 shrink-0" />
                            : <Sparkles size={14} className="mt-0.5 shrink-0 text-violet-300" />}
                          <span>{suggestion.text}</span>
                        </button>
                      ))}
                  {!editSuggestionsLoading && editSuggestionsError && (
                    <button
                      type="button"
                      onClick={() => void loadEditSuggestions(gameState)}
                      className="flex min-h-11 w-full items-center gap-2 border border-fuchsia-500/30 px-3 py-2.5 text-left text-sm text-fuchsia-300 transition-colors hover:bg-fuchsia-500/[0.06]"
                    >
                      <RotateCcw size={14} className="shrink-0" />
                      <span>Suggestions unavailable. Retry</span>
                    </button>
                  )}
                </div>
              </div>
            )}
            {loading && (
              <div className="flex justify-start">
                <div className="cyber-panel border border-cyan-400/10 bg-[#111625] px-3.5 py-2.5 text-base text-cyan-400">
                  <span className="inline-flex gap-1">
                    <span className="animate-bounce" style={{ animationDelay: '0ms' }}>·</span>
                    <span className="animate-bounce" style={{ animationDelay: '150ms' }}>·</span>
                    <span className="animate-bounce" style={{ animationDelay: '300ms' }}>·</span>
                  </span>
                </div>
              </div>
            )}
            {error && (
              <div className="text-fuchsia-300 bg-fuchsia-950/30 px-3 py-2 text-xs border border-fuchsia-700/50">
                {error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="safe-bottom shrink-0 border-t border-cyan-400/10 bg-[#080b16] p-3">
            <div className="flex gap-2 items-end">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Describe your game idea…"
                disabled={loading}
                rows={2}
                className="min-w-0 flex-1 bg-[#0d1120] border border-slate-700 px-3 py-2.5 text-base leading-snug text-slate-100 placeholder-slate-600 resize-none focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_18px_rgba(34,211,238,0.09)] disabled:opacity-50"
              />
              <button
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                className="cyber-panel flex h-11 w-11 shrink-0 items-center justify-center border border-cyan-300/40 bg-gradient-to-br from-cyan-400 to-violet-500 text-[#050711] hover:brightness-125 disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500 disabled:cursor-not-allowed transition-all"
                aria-label="Send"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="mt-1.5 hidden text-center text-xs text-slate-600 sm:block">Enter to send · Shift+Enter for newline</p>
          </div>
        </div>

        <button
          type="button"
          aria-label="Resize chat panel"
          onPointerDown={() => setIsResizing(true)}
          className="group relative z-10 hidden w-1 shrink-0 cursor-col-resize bg-slate-900 transition-colors hover:bg-cyan-400 hover:shadow-[0_0_12px_#22d3ee] md:block"
        >
          <span className="absolute left-1/2 top-1/2 h-10 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-600 opacity-0 transition-opacity group-hover:opacity-100" />
        </button>

        {/* ── Right: game renderer ── */}
        <div ref={previewRef} className={`${activeMobilePanel === 'preview' ? 'flex' : 'hidden'} min-w-0 flex-1 flex-col bg-[#080b16] md:flex`}>
          <div className="flex h-12 shrink-0 items-center gap-3 border-b border-cyan-400/10 bg-[#080b16] px-3 sm:px-4">
            <span className={`h-2 w-2 rounded-full ${gameHtml ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : 'bg-slate-600'}`} />
            <div className="min-w-0">
              <p className="truncate text-sm font-bold uppercase tracking-wider text-slate-200">{gameTitle}</p>
              <p className="cyber-label text-[8px] uppercase text-slate-500">{gameHtml ? 'Live // playable' : 'Awaiting input'}</p>
            </div>
            <div className="ml-auto flex items-center gap-1">
              <button onClick={() => setPreviewKey(key => key + 1)} disabled={!gameHtml} className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-30" title="Restart game" aria-label="Restart game">
                <RotateCcw size={16} />
              </button>
              <button onClick={enterFullscreen} className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-800 hover:text-white" title="Fullscreen" aria-label="Enter fullscreen">
                <Expand size={16} />
              </button>
              <div className="mx-1 h-5 w-px bg-slate-800" />
              <button onClick={startNewGame} className="cyber-panel flex items-center gap-1.5 border border-violet-400/30 bg-violet-500/10 px-2.5 py-2 text-xs font-bold uppercase tracking-wider text-violet-200 transition hover:border-violet-300 hover:bg-violet-500/20">
                <Plus size={14} /> <span className="hidden sm:inline">New game</span>
              </button>
            </div>
          </div>
          <div className="cyber-grid flex min-h-0 flex-1 items-center justify-center overflow-auto">
          {gameHtml ? (
            <iframe
              key={`${previewKey}-${gameHtml}`}
              srcDoc={gameHtml}
              sandbox="allow-scripts"
              className="w-full h-full border-0"
              title="Game preview"
            />
          ) : (
            <div className="w-full max-w-3xl px-6 py-8 text-center select-none">
              <div className="cyber-panel cyber-pulse mx-auto mb-4 flex h-12 w-12 items-center justify-center border border-cyan-400/40 bg-cyan-400/10 text-cyan-300">
                <Sparkles size={23} />
              </div>
              <p className="text-2xl font-black uppercase tracking-tight text-slate-100">Choose your <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-violet-400">starting point</span></p>
              <p className="mt-1.5 text-sm text-slate-500">Start with a proven classic, then customize it through chat.</p>
              <div className="mt-7 grid grid-cols-1 gap-3 sm:grid-cols-3">
                {GAME_STARTERS.map(({ name, description, prompt, icon: Icon, accent }) => (
                  <button key={name} onClick={() => sendMessage(prompt)} disabled={loading} className={`cyber-panel group border bg-gradient-to-b p-4 text-left transition duration-200 hover:-translate-y-1 disabled:opacity-50 ${accent}`}>
                    <Icon size={22} className="mb-8" />
                    <p className="font-black uppercase tracking-wider text-slate-100">{name}</p>
                    <p className="mt-1 text-xs text-slate-400">{description}</p>
                  </button>
                ))}
              </div>
              <button onClick={() => setActiveMobilePanel('chat')} className="mt-6 text-xs font-medium text-slate-500 hover:text-slate-300 md:hidden">Or describe another idea in chat →</button>
            </div>
          )}
          </div>
        </div>

      </div>
    </div>
  )
}
