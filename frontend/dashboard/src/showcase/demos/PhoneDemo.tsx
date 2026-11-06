import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { toast } from 'sonner'
import { Home01Icon, Search01Icon, Ticket01Icon, UserIcon } from '@hugeicons/core-free-icons'
import { MobileNav, PhoneFrame, type MobileNavItem } from '@/components/layout'
import { BackButton, Onboarding, SplashScreen, type OnboardingStep } from '@/components/shared'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { BASE } from '../base'

type Stage = 'splash' | 'onboarding' | 'app'
type Tab = 'home' | 'search' | 'tickets' | 'profile'

const steps: OnboardingStep[] = [
  { title: 'Zauzmi svoje mesto u hodu.', subtitle: 'Uzmi digitalni tiket dok si na kafi — red čeka tebe, a ne ti njega.' },
  { title: 'Nađi filijalu. Uzmi tiket.', subtitle: 'Rezerviši mesto na šalteru pre nego što izađeš iz kuće.' },
  { title: 'Pametno čekanje.', subtitle: 'Prati status reda uživo i dođi tačno u minut kad si na redu.' },
]

const TabContent = ({ tab, hasTicket, onTakeTicket }: { tab: Tab; hasTicket: boolean; onTakeTicket: () => void }) => {
  switch (tab) {
    case 'home':
      return (
        <div className="flex flex-col gap-3 p-4">
          <h2 className="text-2xl font-black">Dobro jutro 👋</h2>
          {['Centar', 'Zemun', 'Novi Beograd'].map((name, i) => (
            <Card key={name}>
              <CardHeader>
                <CardTitle>Filijala {name}</CardTitle>
                <CardDescription>{(i + 1) * 4} ljudi u redu · ~{(i + 1) * 6} min</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      )
    case 'search':
      return <div className="p-4"><Input placeholder="Pretraži filijale…" /></div>
    case 'tickets':
      return (
        <div className="flex flex-col items-center gap-4 p-8 text-center">
          {hasTicket
            ? <><span className="text-6xl font-black">A-042</span><span className="text-sm text-muted-foreground">Ispred tebe: 3 osobe</span></>
            : <span className="text-sm text-muted-foreground">Nemaš aktivan tiket.</span>}
          <Button size="lg" className="w-full py-6" onClick={onTakeTicket}>{hasTicket ? 'Otkaži tiket' : 'Uzmi tiket'}</Button>
        </div>
      )
    case 'profile':
      return <div className="p-4 text-sm text-muted-foreground">Profil</div>
  }
}

const PhoneDemo = () => {
  const [run, setRun] = useState(0)
  const [stage, setStage] = useState<Stage>('splash')
  const [tab, setTab] = useState<Tab>('home')
  const [hasTicket, setHasTicket] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setStage('onboarding'), 2500)
    return () => clearTimeout(t)
  }, [run])

  const restart = () => {
    setStage('splash')
    setTab('home')
    setRun((r) => r + 1)
  }

  const tabs: MobileNavItem<Tab>[] = [
    { key: 'home', label: 'Početna', icon: Home01Icon },
    { key: 'search', label: 'Pretraga', icon: Search01Icon },
    { key: 'tickets', label: 'Tiketi', icon: Ticket01Icon, badge: hasTicket },
    { key: 'profile', label: 'Profil', icon: UserIcon },
  ]

  return (
    <>
      <PhoneFrame>
        <AnimatePresence mode="wait">
          {stage === 'splash' && (
            <motion.div key={`splash-${run}`} className="size-full" exit={{ opacity: 0, scale: 0.95 }} transition={{ duration: 0.5 }}>
              <SplashScreen><h1 className="text-4xl font-black"><span className="text-chart-3">e</span>App</h1></SplashScreen>
            </motion.div>
          )}
          {stage === 'onboarding' && (
            <motion.div
              key="onboarding"
              className="size-full"
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            >
              <Onboarding steps={steps} onFinish={() => setStage('app')} />
            </motion.div>
          )}
          {stage === 'app' && (
            <motion.div
              key="app"
              className="relative flex h-full flex-col"
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="no-scrollbar flex-1 overflow-y-auto">
                <TabContent
                  tab={tab}
                  hasTicket={hasTicket}
                  onTakeTicket={() => {
                    setHasTicket(!hasTicket)
                    toast(hasTicket ? 'Tiket otkazan' : 'Tiket A-042 izdat')
                  }}
                />
              </div>
              <MobileNav active={tab} onChange={setTab} items={tabs} />
            </motion.div>
          )}
        </AnimatePresence>
      </PhoneFrame>

      {/* Controls float above the frame (PhoneFrame is fixed inset-0) */}
      <div className="fixed top-4 left-4 z-[10000] flex flex-col items-start gap-2">
        <BackButton to={`${BASE}/layout#phone-frame`} label="Back to docs" />
        <Button size="sm" variant="outline" onClick={restart}>Restart flow</Button>
      </div>
    </>
  )
}

export default PhoneDemo
