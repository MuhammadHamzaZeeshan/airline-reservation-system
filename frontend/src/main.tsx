import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Admin from './routes/Admin'
import Checkout from './routes/Checkout'
import Confirmation from './routes/Confirmation'
import FlightPage from './routes/FlightPage'
import Login from './routes/Login'
import MyBookings from './routes/MyBookings'
import Network from './routes/Network'
import Search from './routes/Search'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Search />} />
          <Route path="/login" element={<Login />} />
          <Route path="/flight/:id" element={<FlightPage />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/confirmation/:pnr" element={<Confirmation />} />
          <Route path="/bookings" element={<MyBookings />} />
          <Route path="/network" element={<Network />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
