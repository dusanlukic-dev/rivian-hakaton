import { requireOptionalNativeModule } from 'expo';

interface SystemAccessModule {
  isDndAccessGranted(): boolean;
}

// Optional: a dev build made before this module existed simply reports "unknown" instead of crashing.
const native = requireOptionalNativeModule<SystemAccessModule>('SystemAccess');

/** Whether this app may override Do Not Disturb. null = unknown (not Android, or the build lacks the module). */
export function isDndAccessGranted(): boolean | null {
  try {
    return native ? native.isDndAccessGranted() : null;
  } catch {
    return null;
  }
}
