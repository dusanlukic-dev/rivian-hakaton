import type { ReactNode } from 'react'
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { HugeiconsIcon } from '@hugeicons/react'
import { Loading03Icon } from '@hugeicons/core-free-icons'
import { cn } from '@/lib/utils'

type DataTableProps<T> = {
  data: T[]
  /** Build with `createColumnHelper<T>()` from @tanstack/react-table */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- columns with different value types can't share one TValue
  columns: ColumnDef<T, any>[]
  isLoading?: boolean
  error?: string | null
  emptyMessage?: ReactNode
  loadingMessage?: ReactNode
  onRowClick?: (row: T) => void
}

/** Striped table with loading / error / empty states baked in. */
const DataTable = <T,>({
  data,
  columns,
  isLoading,
  error,
  emptyMessage = 'Nema podataka.',
  loadingMessage = 'Učitavanje...',
  onRowClick,
}: DataTableProps<T>) => {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() })

  let content: ReactNode
  if (isLoading) {
    content = (
      <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted-foreground">
        <HugeiconsIcon icon={Loading03Icon} strokeWidth={1.5} className="size-4 animate-spin" />
        {loadingMessage}
      </div>
    )
  } else if (error) {
    content = <div className="py-16 text-center text-xs text-destructive">{error}</div>
  } else if (data.length === 0) {
    content = <div className="py-16 text-center text-xs text-muted-foreground">{emptyMessage}</div>
  } else {
    content = (
      <table className="w-full text-xs">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-border bg-muted/40">
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-4 py-2.5 text-left text-[11px] font-semibold tracking-wider text-muted-foreground uppercase"
                >
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              onClick={onRowClick ? () => onRowClick(row.original) : undefined}
              className={cn(
                'border-b border-border/60 even:bg-muted/20',
                onRowClick && 'cursor-pointer hover:bg-muted/40'
              )}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  return <div className="overflow-hidden rounded-lg border border-border bg-background">{content}</div>
}

export default DataTable
