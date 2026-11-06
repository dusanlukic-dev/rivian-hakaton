import { QRCodeSVG } from 'qrcode.react'
import { Card } from '@/components/ui/card'

// Vigil plum-900 on linen-50 in both themes: scanners want dark modules on a light quiet zone (11:1)
const QR_FG = '#352f44'
const QR_BG = '#faf0e6'

/** QR of the backend address for the phone app: plain `<lan-ip>:<port>` (LAN IP found by vite.config.ts at dev/build time) */
const ConnectPhoneCard = () => {
  const address = `${__LAN_IP__ || location.hostname}:${__BACKEND_PORT__}`
  return (
    <Card className="gap-5 p-6">
      <h2 className="text-h3">Connect phone</h2>
      <div className="flex items-center gap-5">
        <div className="shrink-0 rounded-md bg-linen-50 p-2">
          <QRCodeSVG value={address} size={112} marginSize={2} level="M" title={address} fgColor={QR_FG} bgColor={QR_BG} />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-label text-muted-foreground uppercase">Backend address</span>
          <code className="text-body font-semibold break-all">{address}</code>
          <span className="text-body-sm text-muted-foreground">Scan it in the phone app (same Wi-Fi or hotspot), or type it in.</span>
        </div>
      </div>
    </Card>
  )
}

export default ConnectPhoneCard
