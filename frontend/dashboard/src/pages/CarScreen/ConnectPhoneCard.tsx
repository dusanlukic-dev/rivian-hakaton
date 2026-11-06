import { HugeiconsIcon } from '@hugeicons/react'
import { QrCodeIcon } from '@hugeicons/core-free-icons'
import { QRCodeSVG } from 'qrcode.react'
import { Card } from '@/components/ui/card'

/** QR of the backend address for the phone app: plain `<lan-ip>:<port>` (LAN IP found by vite.config.ts at dev/build time) */
const ConnectPhoneCard = () => {
  const address = `${__LAN_IP__ || location.hostname}:${__BACKEND_PORT__}`
  return (
    <Card className="gap-4 p-5 text-sm">
      <div className="flex items-center gap-2">
        <HugeiconsIcon icon={QrCodeIcon} size={18} />
        <h2 className="font-semibold">Connect phone</h2>
      </div>
      <div className="flex items-center gap-4">
        {/* Scanners want dark modules on a light quiet zone, so this tile stays white in both themes */}
        <div className="shrink-0 rounded-lg bg-white p-2">
          <QRCodeSVG value={address} size={112} marginSize={2} level="M" title={address} />
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="text-xs text-muted-foreground">Backend address</span>
          <code className="font-mono text-base font-semibold break-all">{address}</code>
          <span className="text-xs text-muted-foreground">Scan it in the phone app (same Wi-Fi or hotspot), or type it in.</span>
        </div>
      </div>
    </Card>
  )
}

export default ConnectPhoneCard
