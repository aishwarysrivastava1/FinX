// frontend/src/main.jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// 🔥 CAPTURE GOOGLE TOKENS BEFORE REACT LOADS
const params = new URLSearchParams(window.location.search)

const access = params.get("access_token")
const refresh = params.get("refresh_token")

if (access) {
  // ✅ FIXED KEYS (must match AuthContext)
  localStorage.setItem("finx_access", access)
  localStorage.setItem("finx_refresh", refresh)

  // clean URL (remove tokens)
  window.history.replaceState({}, "", "/")
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)