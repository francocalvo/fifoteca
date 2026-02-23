import { useQuery } from "@tanstack/react-query"

import { type FifotecaPlayerPublic, FifotecaService } from "@/client"
import { isLoggedIn } from "./useAuth"

/**
 * Hook to ensure the authenticated user has a Fifoteca player profile.
 *
 * Calls POST /api/v1/fifoteca/players/me which creates a profile if none exists,
 * or returns the existing profile. The result is cached indefinitely to avoid
 * repeat API calls on remount.
 *
 * @returns {Object} Hook state
 * @returns {FifotecaPlayerPublic | undefined} player - The player profile data
 * @returns {boolean} isLoading - Whether the profile is being fetched
 * @returns {Error | null} error - Any error that occurred during fetch
 */
const useFifotecaPlayer = () => {
  const {
    data: player,
    isLoading,
    error,
  } = useQuery<FifotecaPlayerPublic, Error>({
    queryKey: ["fifoteca", "player", "me"],
    queryFn: () => FifotecaService.createOrGetPlayerProfile(),
    enabled: isLoggedIn(),
    staleTime: Infinity,
  })

  return {
    player,
    isLoading,
    error,
  }
}

export default useFifotecaPlayer
