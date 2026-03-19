import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Dashboard from './pages/Dashboard'
import ProcessDocument from './pages/ProcessDocument'
import Sessions from './pages/Sessions'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-surface">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-auto">
          <Routes>
            <Route path="/"         element={<Dashboard />} />
            <Route path="/process"  element={<ProcessDocument />} />
            <Route path="/sessions" element={<Sessions />} />
            <Route path="*"         element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
