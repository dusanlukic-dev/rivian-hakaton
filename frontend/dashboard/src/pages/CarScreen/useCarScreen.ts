import { useEffect, useState } from 'react'
import type { LiveMessage, TripState, TripSummary } from '@/api/types'
import { useLive } from '@/hooks/useLive'
import { playOnce, readSoundPref, startLoop, stopAll, stopClip, unlockAudio, writeSoundPref } from './audio'

/** After a (re)connect the server sends `state` at once if a trip is active. Silence this long = the trip we show is gone */
const STALE_AFTER_MS = 1500

/** Live trip state from the WebSocket, plus the car's sound reactions. The backend decides everything; this only executes `response` */
export function useCarScreen() {
  const [trip, setTrip] = useState<TripState | null>(null)
  const [summary, setSummary] = useState<TripSummary | null>(null)
  const [emergency, setEmergency] = useState<TripState | null>(null)
  const [awaitingState, setAwaitingState] = useState(false)
  const [soundOn, setSoundOn] = useState(readSoundPref)
  // A remembered "on" still needs one gesture per page load before the browser lets audio play
  const [activated, setActivated] = useState(() => navigator.userActivation?.hasBeenActive ?? false)

  const { status } = useLive({
    onOpen: () => setAwaitingState(true),
    onMessage: (msg: LiveMessage) => {
      setAwaitingState(false)
      switch (msg.type) {
        case 'trip_started':
          setTrip(msg.data)
          setSummary(null)
          break
        case 'state': {
          setTrip(msg.data)
          const { sound } = msg.data.response
          // One clip per message gives a rhythm that stops when the field goes back to "none". The siren covers an emergency
          if (soundOn && !emergency) {
            if (sound === 'low') playOnce('chime')
            else if (sound === 'high') playOnce('alarm_warning')
          }
          break
        }
        case 'emergency':
          setTrip(msg.data)
          setEmergency(msg.data)
          if (soundOn) startLoop('alarm_siren')
          break
        case 'trip_ended':
          setTrip(null)
          setSummary(msg.data)
          break
      }
    },
  })

  useEffect(() => {
    if (!awaitingState) return
    const timer = setTimeout(() => {
      setTrip(null)
      setAwaitingState(false)
    }, STALE_AFTER_MS)
    return () => clearTimeout(timer)
  }, [awaitingState])

  // The first click or key anywhere unlocks audio for a remembered "on"
  useEffect(() => {
    if (activated) return
    const onGesture = () => {
      setActivated(true)
      if (readSoundPref()) unlockAudio()
    }
    window.addEventListener('click', onGesture)
    window.addEventListener('keydown', onGesture)
    return () => {
      window.removeEventListener('click', onGesture)
      window.removeEventListener('keydown', onGesture)
    }
  }, [activated])

  // Clips are module singletons, so leaving the page must silence them
  useEffect(() => stopAll, [])

  const toggleSound = () => {
    if (soundOn && activated) {
      writeSoundPref(false)
      setSoundOn(false)
      stopAll()
      return
    }
    // Off → on, or on-but-blocked → unlocked. This click is the gesture the browser wants
    writeSoundPref(true)
    setSoundOn(true)
    setActivated(true)
    unlockAudio()
    if (emergency) startLoop('alarm_siren')
  }

  const dismissEmergency = () => {
    stopClip('alarm_siren')
    setEmergency(null)
  }

  return {
    status,
    trip,
    summary,
    emergency,
    dismissEmergency,
    dismissSummary: () => setSummary(null),
    sound: { on: soundOn, blocked: soundOn && !activated, toggle: toggleSound },
  }
}
