import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, staleTime: 30_000 },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#111827',
            color: '#f9fafb',
            border: '1px solid #1f2937',
            borderRadius: '8px',
            fontSize: '14px',
          },
          success: { iconTheme: { primary: '#10b981', secondary: '#111827' } },
          error:   { iconTheme: { primary: '#ef4444', secondary: '#111827' } },
        }}
      />
    </QueryClientProvider>
  </React.StrictMode>
)
