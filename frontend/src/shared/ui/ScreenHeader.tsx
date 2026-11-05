import type { ReactNode } from 'react'

interface ScreenHeaderProps {
  eyebrow: string
  title: string
  description?: string
  action?: ReactNode
}

export function ScreenHeader({ eyebrow, title, description, action }: ScreenHeaderProps) {
  return (
    <header className="screen-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p className="screen-description">{description}</p>}
      </div>
      {action}
    </header>
  )
}
