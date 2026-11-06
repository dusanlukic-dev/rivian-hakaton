/** Green corner brackets shown where the scan box will be while the camera starts */
export default function QrBoxOutline({ size }: { size: number }) {
  const c = 24;
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="4"
      className="text-green-500"
    >
      <path d={`M0,${c} L0,0 L${c},0`} strokeLinecap="round" />
      <path d={`M${size - c},0 L${size},0 L${size},${c}`} strokeLinecap="round" />
      <path d={`M0,${size - c} L0,${size} L${c},${size}`} strokeLinecap="round" />
      <path d={`M${size - c},${size} L${size},${size} L${size},${size - c}`} strokeLinecap="round" />
    </svg>
  );
}
