import { Pill } from '@/components/ui';
import { strings } from '@/config/strings';
import { useServerStatus } from '@/state/server';
import { colors } from '@/theme/colors';

/** Whether the server at `address` answered its last call ('unknown' shows "Checking…" until the first answer). */
export function ServerStatusPill({ address }: { address: string }) {
  const status = useServerStatus(address);
  const color = status === 'online' ? colors.ok : status === 'offline' ? colors.warn : colors.subtle;
  return <Pill label={strings.server.status[status]} color={color} />;
}
