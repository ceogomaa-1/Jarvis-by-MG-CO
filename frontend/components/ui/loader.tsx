"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const loaderVariants = cva("inline-block", {
  variants: {
    size: {
      xs: "h-3 w-3",
      sm: "h-4 w-4",
      md: "h-5 w-5",
      lg: "h-6 w-6",
      xl: "h-8 w-8",
    },
    variant: {
      default: "text-foreground",
      primary: "text-primary",
      secondary: "text-secondary-foreground",
      muted: "text-muted-foreground",
    },
  },
  defaultVariants: {
    size: "md",
    variant: "default",
  },
})

export interface LoaderProps
  extends React.SVGAttributes<SVGSVGElement>,
    VariantProps<typeof loaderVariants> {}

const Loader = React.forwardRef<SVGSVGElement, LoaderProps>(
  ({ className, size, variant, ...props }, ref) => (
    <svg
      ref={ref}
      className={cn("motion-safe:animate-spin", loaderVariants({ size, variant }), className)}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      role="status"
      aria-label="Working"
      {...props}
    >
      <circle
        className="opacity-20"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V1C5.925 1 1 5.925 1 12h3z"
      />
    </svg>
  ),
)

Loader.displayName = "Loader"

export { Loader, loaderVariants }
