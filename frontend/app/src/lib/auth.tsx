import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { api, getToken, setToken } from "./api"
import type { CurrentUser } from "./types"

interface AuthContextValue {
  user: CurrentUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  const queryClient = useQueryClient()

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }
    api
      .get<CurrentUser>("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(username: string, password: string) {
    const res = await api.post<{
      access_token: string
      user_id: string
      username: string
      role: CurrentUser["role"]
      display_name: string
    }>("/auth/login", { username, password })
    setToken(res.access_token)
    setUser({ id: res.user_id, username: res.username, role: res.role, display_name: res.display_name })
  }

  function logout() {
    setToken(null)
    setUser(null)
    // Query keys (["cameras"], ["incidents", ...], etc.) are identical across
    // sessions, so without this the next login on a shared workstation would
    // briefly render the previous user's cached data before the refetch lands.
    queryClient.clear()
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
