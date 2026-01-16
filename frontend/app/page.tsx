'use client'

import { useState } from 'react'

export default function Home() {
  const [animal, setAnimal] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  const generateAnimal = async () => {
    setLoading(true)
    setError('')
    setAnimal('')
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      console.log(`Calling API: ${apiUrl}/generate-animal`)
      
      const response = await fetch(`${apiUrl}/generate-animal`)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error(`API Error (${response.status}):`, errorText)
        throw new Error(`Failed to generate animal: ${response.status}`)
      }
      
      const data = await response.json()
      setAnimal(data.animal)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred'
      console.error('Error:', errorMessage)
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full bg-slate-800/50 backdrop-blur-sm rounded-2xl shadow-2xl border border-slate-700 p-8">
        <div className="text-center space-y-8">
          <div>
            <h1 className="text-5xl font-bold text-white mb-3">
              ConYard
            </h1>
            <p className="text-slate-400 text-lg">
              AI-Powered Random Animal Generator
            </p>
          </div>

          <div className="min-h-[120px] flex items-center justify-center">
            {loading && (
              <div className="flex flex-col items-center gap-4">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                <p className="text-slate-400">Generating...</p>
              </div>
            )}
            
            {animal && !loading && (
              <div className="animate-fade-in">
                <div className="text-6xl mb-4">🐾</div>
                <p className="text-4xl font-bold text-blue-400">
                  {animal}
                </p>
              </div>
            )}
            
            {error && (
              <div className="text-red-400 bg-red-900/20 px-6 py-4 rounded-lg border border-red-800">
                <p className="font-semibold">Error:</p>
                <p>{error}</p>
              </div>
            )}
            
            {!loading && !animal && !error && (
              <p className="text-slate-500 text-lg">
                Click the button below to generate a random animal
              </p>
            )}
          </div>

          <button
            onClick={generateAnimal}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:cursor-not-allowed text-white font-semibold py-4 px-8 rounded-xl transition-all duration-200 transform hover:scale-105 active:scale-95 shadow-lg hover:shadow-blue-500/50"
          >
            {loading ? 'Generating...' : 'Generate Random Animal'}
          </button>

          <div className="pt-4 border-t border-slate-700">
            <p className="text-slate-500 text-sm">
              Powered by Vertex AI Gemini API
            </p>
          </div>
        </div>
      </div>
    </main>
  )
}
