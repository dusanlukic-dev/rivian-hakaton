import { useRef, useState, type DragEvent } from 'react'
import { strings } from '@/strings'
import { useVideoSim } from '@/useVideoSim'

const button =
  'inline-flex h-9 items-center justify-center rounded-md px-4 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50'
const primary = `${button} bg-primary text-primary-foreground hover:bg-primary/90`
const outline = `${button} border bg-background hover:bg-muted`

const Bar = ({ value, label }: { value: number; label?: string }) => {
  const percent = Math.min(100, Math.max(0, value * 100))
  return (
    <div className="flex flex-col gap-1.5">
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-200" style={{ width: `${percent}%` }} />
      </div>
      {label && <span className="text-xs tabular-nums text-muted-foreground">{label}</span>}
    </div>
  )
}

/** One page: choose a clip, send it to the backend as the camera. Nothing from the backend is shown */
const App = () => {
  const { state, previewRef, chooseFile, send, stop } = useVideoSim()
  const { phase, clip, prepared, sentS, note, error } = state
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const busy = phase === 'starting' || phase === 'sending'

  const pick = () => inputRef.current?.click()
  // A file dropped anywhere on the page, in any state, replaces the clip (and stops a send in progress)
  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) chooseFile(file)
  }

  return (
    <main
      className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-5 p-6"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{strings.title}</h1>
        <p className="text-sm text-muted-foreground">{strings.subtitle}</p>
      </header>

      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = '' // choosing the same file again still fires change
          if (file) chooseFile(file)
        }}
      />

      {!clip ? (
        <button
          type="button"
          onClick={pick}
          className={`flex aspect-video w-full items-center justify-center rounded-xl border-2 border-dashed p-6 text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground ${dragging ? 'border-foreground/60 text-foreground' : ''}`}
        >
          {strings.drop}
        </button>
      ) : (
        <section className="flex flex-col gap-4 rounded-xl border bg-card p-4 text-card-foreground">
          <video
            ref={previewRef}
            src={clip.url}
            muted
            playsInline
            preload="auto"
            className="aspect-video w-full rounded-lg bg-muted object-contain"
          />

          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-sm">
            <span className="min-w-0 truncate font-medium">{clip.name}</span>
            {phase !== 'preparing' && (
              <span className="tabular-nums text-muted-foreground">
                {strings.clipInfo(clip.frames.length, clip.durationS, clip.width, clip.height)}
              </span>
            )}
          </div>

          {phase === 'preparing' && (
            <Bar
              value={prepared ? prepared.done / prepared.total : 0}
              label={prepared ? strings.preparing(prepared.done, prepared.total) : undefined}
            />
          )}

          {phase !== 'preparing' && (
            <div className="flex flex-wrap items-center gap-3">
              {/* Send stays where it is (disabled) while busy, so a double click can't land on Stop */}
              <button type="button" onClick={send} disabled={phase !== 'ready'} className={primary}>
                {strings.send}
              </button>
              {busy ? (
                <button type="button" onClick={stop} className={outline}>
                  {strings.stop}
                </button>
              ) : (
                <button type="button" onClick={pick} className={outline}>
                  {strings.chooseAnother}
                </button>
              )}
              {phase === 'starting' && <span className="text-sm text-muted-foreground">{strings.checkingTrip}</span>}
            </div>
          )}

          {phase === 'sending' && <Bar value={sentS / clip.durationS} label={strings.progress(sentS, clip.durationS)} />}
        </section>
      )}

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </main>
  )
}

export default App
