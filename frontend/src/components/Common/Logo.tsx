import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"
import eaSportsFcLogo from "/assets/images/ea-sports-fc-logo.png"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const content =
    variant === "responsive" ? (
      <>
        <img
          src={eaSportsFcLogo}
          alt="EA Sports FC"
          className={cn(
            "h-14 w-auto mx-auto object-contain dark:brightness-0 dark:invert group-data-[collapsible=icon]:hidden",
            className,
          )}
        />
        <img
          src={eaSportsFcLogo}
          alt="EA Sports FC"
          className={cn(
            "h-10 w-auto mx-auto object-contain dark:brightness-0 dark:invert hidden group-data-[collapsible=icon]:block",
            className,
          )}
        />
      </>
    ) : (
      <img
        src={eaSportsFcLogo}
        alt="EA Sports FC"
        className={cn(
          variant === "full"
            ? "h-14 w-auto object-contain dark:brightness-0 dark:invert"
            : "h-10 w-auto object-contain dark:brightness-0 dark:invert",
          className,
        )}
      />
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
