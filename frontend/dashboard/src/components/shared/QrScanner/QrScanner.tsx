import { useCallback, useEffect, useId, useRef, useState, type ChangeEvent } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import QrBoxOutline from "./QrBoxOutline";
import "./QrScanner.scss";

type Camera = { id: string; label: string };

type QrScannerProps = {
  onScan: (text: string) => void;
  /**
   * Stop the camera after the first successful read. Without it `onScan` fires on every frame
   * the code is in view. Default: true
   */
  stopOnScan?: boolean;
  className?: string;
};

function pickCamera(devices: Camera[]) {
  return devices.find((d) => /back|rear|environment/i.test(d.label)) ?? devices[0];
}

function getQrboxSize(el: HTMLElement) {
  const min = Math.min(el.clientWidth, el.clientHeight);
  // 80% of the shorter dimension, capped at 300px
  return Math.round(Math.min(min * 0.8, 300));
}

/** Camera QR scanner with camera switching and scan-from-image fallback. Needs HTTPS (or localhost). */
export default function QrScanner({ onScan, stopOnScan = true, className }: QrScannerProps) {
  // html5-qrcode finds its element by id, so a unique one lets several scanners coexist
  const scannerId = useId();
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const viewportDivRef = useRef<HTMLDivElement>(null);
  const desiredCameraRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [cameras, setCameras] = useState<Camera[]>([]);
  const [activeCameraId, setActiveCameraId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [permState, setPermState] = useState<"pending" | "denied" | "ready">("pending");
  // Placeholder box size mirrors the actual qrbox size
  const [placeholderSize, setPlaceholderSize] = useState(250);

  const onScanRef = useRef(onScan);
  const stopOnScanRef = useRef(stopOnScan);
  useEffect(() => {
    onScanRef.current = onScan;
    stopOnScanRef.current = stopOnScan;
  });

  const getScanner = useCallback(() => {
    scannerRef.current ??= new Html5Qrcode(scannerId, { verbose: false });
    return scannerRef.current;
  }, [scannerId]);

  const stopScanner = useCallback(async () => {
    if (scannerRef.current?.isScanning) {
      await scannerRef.current.stop().catch(() => { });
    }
    setScanning(false);
  }, []);

  const startScanner = useCallback(async (cameraId: string) => {
    const el = viewportDivRef.current;
    if (!el) return;

    const scanner = getScanner();
    if (scanner.isScanning) {
      await scanner.stop().catch(() => { });
    }

    const boxSize = getQrboxSize(el);
    setPlaceholderSize(boxSize);

    // The success callback can fire a few more times before stop() completes
    let handled = false;
    try {
      await scanner.start(
        cameraId,
        { fps: 10, qrbox: { width: boxSize, height: boxSize } },
        (text) => {
          if (handled) return;
          if (stopOnScanRef.current) {
            handled = true;
            void stopScanner();
          }
          onScanRef.current(text);
        },
        () => { } // fires on every frame without a code — normal, ignore
      );
      desiredCameraRef.current = cameraId;
      setActiveCameraId(cameraId);
      setScanning(true);
    } catch (err) {
      console.error("Failed to start camera:", err);
    }
  }, [getScanner, stopScanner]);

  // Fetch cameras + auto-start
  useEffect(() => {
    let cancelled = false;

    Html5Qrcode.getCameras()
      .then((devices) => {
        if (cancelled) return;
        if (!devices.length) {
          setPermState("denied");
          return;
        }
        setCameras(devices);
        setPermState("ready");

        // Start on the next task so the library measures the viewport after this render is painted
        const chosen = pickCamera(devices);
        setTimeout(() => {
          if (!cancelled) void startScanner(chosen.id);
        }, 0);
      })
      .catch(() => {
        if (!cancelled) setPermState("denied");
      });

    return () => {
      cancelled = true;
    };
  }, [startScanner]);

  // Restart with a new qrbox size when the viewport resizes
  useEffect(() => {
    const el = viewportDivRef.current;
    if (!el) return;

    let resizeTimer: ReturnType<typeof setTimeout>;

    const observer = new ResizeObserver(() => {
      // Debounce: don't restart on every pixel of a drag resize
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        setPlaceholderSize(getQrboxSize(el));
        if (desiredCameraRef.current && scannerRef.current?.isScanning) {
          void startScanner(desiredCameraRef.current);
        }
      }, 200);
    });

    observer.observe(el);
    return () => {
      observer.disconnect();
      clearTimeout(resizeTimer);
    };
  }, [startScanner]);

  // Release the camera on unmount
  useEffect(() => {
    return () => {
      const scanner = scannerRef.current;
      if (scanner) {
        scannerRef.current = null;
        void (async () => {
          try { await scanner.stop(); } catch { /* ignore */ }
          try { scanner.clear(); } catch { /* ignore */ }
        })();
      }
    };
  }, []);

  const switchCamera = useCallback(async (cameraId: string) => {
    if (cameraId === activeCameraId) return;
    await startScanner(cameraId);
  }, [activeCameraId, startScanner]);

  const handleBrowse = useCallback(async () => {
    await stopScanner();
    fileInputRef.current?.click();
  }, [stopScanner]);

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;

      let found = false;
      try {
        onScanRef.current(await getScanner().scanFile(file, false));
        found = true;
      } catch (err) {
        console.error("No QR code found in image:", err);
      }

      if (!(found && stopOnScanRef.current) && desiredCameraRef.current) {
        void startScanner(desiredCameraRef.current);
      }
    },
    [getScanner, startScanner]
  );

  return (
    <div className={cn("flex h-full flex-col overflow-hidden", className)}>
      <div className="relative flex-1 overflow-hidden bg-black">
        {/* Scanner viewport */}
        <div id={scannerId} ref={viewportDivRef} className="qr-scanner-viewport h-full w-full" />

        {/* Overlay when camera not ready */}
        {permState !== "ready" && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black">
            {permState === "pending" ? (
              <div className="flex flex-col items-center gap-4">
                <QrBoxOutline size={placeholderSize} />
                <p className="text-sm text-muted-foreground">Initializing camera...</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 px-6">
                <span className="text-center text-base font-medium text-white">
                  Camera permission denied
                </span>
                <span className="h-px w-full bg-red-500" />
                <p className="text-center text-sm text-muted-foreground">
                  Please allow camera access to scan QR codes
                </p>
              </div>
            )}
          </div>
        )}

        {/* Camera switcher */}
        {scanning && cameras.length > 1 && (
          <div className="absolute top-6 right-0 left-0 flex justify-center gap-2 px-4">
            {cameras.map((cam) => (
              <Badge
                key={cam.id}
                variant={cam.id === activeCameraId ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => switchCamera(cam.id)}
              >
                {cam.label || `Camera ${cam.id.slice(0, 6)}`}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Controls */}
      <Card className="rounded-none border-0">
        <CardContent className="flex flex-col items-center gap-3 p-0! pb-8">
          {scanning ? (
            <Button variant="destructive" size="lg" className="w-full py-6" onClick={stopScanner}>
              Stop Scanning
            </Button>
          ) : (
            <Button
              size="lg"
              className="w-full py-6"
              disabled={permState !== "ready"}
              onClick={() => desiredCameraRef.current && startScanner(desiredCameraRef.current)}
            >
              Resume Scanning
            </Button>
          )}

          <Button variant="outline" size="lg" className="w-full py-6" onClick={handleBrowse}>
            Browse Files
          </Button>
        </CardContent>
      </Card>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  );
}
