import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import { Loader2, Snowflake, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useAuthStore } from '@/stores/authStore'
import { authAPI } from '@/services/api'
import { AxiosError } from 'axios'

export default function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)

    try {
      // Call real authentication API
      const response = await authAPI.login(username, password)

      // Clear error only on successful login
      setErrorMessage(null)

      // Store token and user info
      login(username, response.access_token)
      toast.success(t('common.success'))
      navigate('/dashboard')
    } catch (error) {
      // Extract and display specific error message
      let errorMsg = t('auth.loginErrorGeneric')

      if (error instanceof AxiosError) {
        if (error.response) {
          // Server responded with error
          const status = error.response.status
          const detail = error.response.data?.detail

          if (status === 401) {
            // Incorrect credentials
            errorMsg = detail || t('auth.loginError')
          } else if (status === 403) {
            // Account disabled
            errorMsg = detail || t('auth.accountDisabled')
          } else if (status >= 500) {
            // Server error
            errorMsg = t('auth.serverError')
          } else if (detail) {
            // Use backend error message if available
            errorMsg = detail
          }
        } else if (error.request) {
          // Network error - no response received
          errorMsg = t('auth.networkError')
        }
      }

      // Set error message - it will stay visible until next login attempt
      setErrorMessage(errorMsg)

      toast.error(errorMsg, {
        duration: 5000,
        position: 'top-center',
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-gradient-soft p-4">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 opacity-10">
          <Snowflake className="h-32 w-32 text-white animate-pulse-slow" />
        </div>
        <div className="absolute bottom-20 right-10 opacity-10">
          <Snowflake className="h-24 w-24 text-white animate-pulse-slow" style={{ animationDelay: '1s' }} />
        </div>
        <div className="absolute top-1/2 right-1/4 opacity-5">
          <Snowflake className="h-48 w-48 text-white animate-pulse-slow" style={{ animationDelay: '2s' }} />
        </div>
      </div>

      <Card className="w-full max-w-md shadow-2xl relative">
        <CardHeader className="text-center pb-2">
          <div className="mx-auto mb-4">
            <img
              src="/assets/logo.jpg"
              alt="GoGo Fresh"
              className="h-24 w-auto mx-auto rounded-lg shadow-md"
            />
          </div>
          <CardTitle className="text-2xl font-bold">
            {t('auth.loginTitle')}
          </CardTitle>
          <CardDescription className="text-muted-foreground">
            {t('auth.loginSubtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Error Alert - Persistent and Prominent */}
            {errorMessage && (
              <Alert variant="destructive" className="animate-in fade-in slide-in-from-top-2 duration-300">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription className="font-medium">{errorMessage}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="username">{t('auth.username')}</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="username"
                required
                autoComplete="username"
                className="h-11"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">{t('auth.password')}</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="password"
                required
                autoComplete="current-password"
                className="h-11"
              />
            </div>
            <Button
              type="submit"
              className="w-full h-11 font-medium"
              disabled={isLoading}
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('auth.loginButton')}
            </Button>
          </form>

          <div className="mt-6 pt-4 border-t">
            <p className="text-center text-sm text-muted-foreground">
              User Login :
            </p>
            <div className="mt-2 flex justify-center gap-4 text-xs">
              <code className="px-2 py-1 bg-muted rounded">username</code>
              <code className="px-2 py-1 bg-muted rounded">password</code>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
