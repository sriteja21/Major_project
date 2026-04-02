import { useState, useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

// Fix Leaflet icon paths broken by Vite bundling
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: new URL('leaflet/dist/images/marker-icon-2x.png', import.meta.url).href,
  iconUrl:       new URL('leaflet/dist/images/marker-icon.png',    import.meta.url).href,
  shadowUrl:     new URL('leaflet/dist/images/marker-shadow.png',  import.meta.url).href,
})

const destIcon = new L.Icon({
  iconUrl:   'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
  shadowUrl: new URL('leaflet/dist/images/marker-shadow.png', import.meta.url).href,
  iconSize: [25, 41], iconAnchor: [12, 41],
})

const API = 'http://localhost:5050'

const NAV_LABELS = {
  idle:             { text: 'IDLE',                 color: '#555'    },
  awaiting_dest:    { text: 'AWAITING DESTINATION', color: '#ffd700' },
  awaiting_confirm: { text: 'AWAITING CONFIRM',     color: '#ff9f43' },
  navigating:       { text: 'NAVIGATING',           color: '#00d2d3' },
}

// Auto-pans map as GPS updates
function MapController({ lat, lon }) {
  const map = useMap()
  useEffect(() => {
    if (lat && lon) map.setView([lat, lon], map.getZoom(), { animate: true })
  }, [lat, lon])
  return null
}

const DEFAULT_LAT = 17.385
const DEFAULT_LON = 78.487

export default function App() {
  const [status, setStatus] = useState({
    nav_state: 'idle',
    gps_label: 'GPS: waiting...',
    gps_lat: null,
    gps_lon: null,
    dest_lat: null,
    dest_lon: null,
    dest_name: '',
    alert: '',
  })
  const [alertFlash, setAlertFlash] = useState(false)
  const prevAlert = useRef('')

  // ── 1. Browser GPS → POST to backend (real accurate location) ───────────
  useEffect(() => {
    if (!navigator.geolocation) return
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords
        fetch(`${API}/gps`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lat, lon }),
        }).catch(() => {})
      },
      (err) => console.warn('GPS:', err.message),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    )
    return () => navigator.geolocation.clearWatch(watchId)
  }, [])

  // ── 2. Poll backend every 500ms for state ────────────────────────────────
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const data = await fetch(`${API}/status`).then(r => r.json())
        setStatus(data)
        if (data.alert && data.alert !== prevAlert.current) {
          prevAlert.current = data.alert
          setAlertFlash(true)
          setTimeout(() => setAlertFlash(false), 700)
        }
      } catch { /* backend starting */ }
    }, 500)
    return () => clearInterval(id)
  }, [])

  const navInfo = NAV_LABELS[status.nav_state] || NAV_LABELS.idle
  const mapLat  = status.gps_lat || DEFAULT_LAT
  const mapLon  = status.gps_lon || DEFAULT_LON

  return (
    <div className="app">
      <div className="panels">

        {/* Camera feed */}
        <div className="panel camera-panel">
          <span className="panel-label">CAMERA</span>
          <img src={`${API}/stream`} alt="camera" className="camera-img" />
        </div>

        {/* Leaflet map */}
        <div className="panel map-panel">
          <span className="panel-label">MAP</span>
          <MapContainer
            center={[mapLat, mapLon]}
            zoom={15}
            className="map-container"
            zoomControl
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <MapController lat={mapLat} lon={mapLon} />

            {/* Your position — blue */}
            {status.gps_lat && (
              <Marker position={[status.gps_lat, status.gps_lon]}>
                <Popup>You are here</Popup>
              </Marker>
            )}

            {/* Destination — red */}
            {status.dest_lat && (
              <Marker position={[status.dest_lat, status.dest_lon]} icon={destIcon}>
                <Popup>{status.dest_name || 'Destination'}</Popup>
              </Marker>
            )}
          </MapContainer>
        </div>

      </div>

      {/* Status bar */}
      <div className="statusbar">
        <span className="nav-state" style={{ color: navInfo.color }}>
          ⬤ {navInfo.text}
        </span>
        <span className="gps-info">{status.gps_label}</span>
        <span className={`alert-text ${alertFlash ? 'flash' : ''}`}>
          {status.alert ? `🔔 ${status.alert}` : ''}
        </span>
      </div>
    </div>
  )
}
