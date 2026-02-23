import { Navigate, createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/")({
  component: () => <Navigate to="/fifoteca" />,
})
