import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

const loginSchema = z.object({
  username: z.string().min(1, 'Korisničko ime je obavezno'),
  password: z.string().min(1, 'Lozinka je obavezna'),
})

export type LoginValues = z.infer<typeof loginSchema>

type LoginFormProps = {
  /** Throw to show `errorMessage` under the fields */
  onSubmit: (values: LoginValues) => Promise<void>
  /** Logo / app name above the card */
  brand?: ReactNode
  title?: string
  description?: string
  errorMessage?: string
}

/** Centered username + password card with zod validation. */
const LoginForm = ({
  onSubmit,
  brand,
  title = 'Prijava',
  description = 'Unesite vaše kredencijale.',
  errorMessage = 'Prijava nije uspela. Proverite podatke i pokušajte ponovo.',
}: LoginFormProps) => {
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  const submit = async (values: LoginValues) => {
    setServerError(null)
    try {
      await onSubmit(values)
    } catch (error) {
      console.error('[LoginForm] Login failed:', error)
      setServerError(errorMessage)
    }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-muted/30">
      <div className="w-full max-w-sm px-4">
        {brand && <div className="mb-6 text-center">{brand}</div>}

        <Card className="gap-0 border-border shadow-sm">
          <CardHeader className="border-b px-4">
            <CardTitle className="text-sm font-semibold">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>

          <form onSubmit={handleSubmit(submit)}>
            <CardContent className="flex flex-col gap-4 pt-4 pb-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="username">Korisničko ime</Label>
                <Input id="username" type="text" autoComplete="username" aria-invalid={!!errors.username} {...register('username')} />
                {errors.username && <p className="text-[11px] text-destructive">{errors.username.message}</p>}
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">Lozinka</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  aria-invalid={!!errors.password}
                  {...register('password')}
                />
                {errors.password && <p className="text-[11px] text-destructive">{errors.password.message}</p>}
              </div>

              {serverError && (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[11px] text-destructive">
                  {serverError}
                </p>
              )}
            </CardContent>

            <CardFooter className="border-t pt-4">
              <Button type="submit" className="w-full" size="lg" disabled={isSubmitting}>
                {isSubmitting ? 'Prijavljivanje...' : 'Prijavi se'}
              </Button>
            </CardFooter>
          </form>
        </Card>
      </div>
    </div>
  )
}

export default LoginForm
