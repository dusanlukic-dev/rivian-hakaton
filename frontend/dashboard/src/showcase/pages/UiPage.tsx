import { useState } from 'react'
import { toast } from 'sonner'
import { HugeiconsIcon } from '@hugeicons/react'
import { Add01Icon, Delete02Icon, Mail01Icon, PencilEdit01Icon, Search01Icon, Settings01Icon } from '@hugeicons/core-free-icons'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput, InputGroupText } from '@/components/ui/input-group'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Code, Demo, DocPage, DocSection, P, Readout } from '../_kit/Doc'

const UiPage = () => {
  const [checked, setChecked] = useState(true)
  const [enabled, setEnabled] = useState(false)
  const [fruit, setFruit] = useState('')
  const [showGrid, setShowGrid] = useState(true)
  const [sort, setSort] = useState('name')

  return (
    <DocPage
      title="UI (shadcn)"
      intro={<>These are shadcn/ui components (style <code>radix-mira</code>), and they're your files: edit them in <code>src/components/ui/</code>. Add more with <code>npx shadcn@latest add &lt;name&gt;</code>.</>}
      toc={[
        ['button', 'Button'], ['badge', 'Badge'], ['card', 'Card'], ['inputs', 'Input / Textarea / Label'], ['input-group', 'InputGroup'],
        ['checkbox-switch', 'Checkbox / Switch'], ['select', 'Select'], ['dropdown', 'DropdownMenu'], ['separator', 'Separator'],
        ['skeleton', 'Skeleton'], ['toast', 'Toasts'],
      ]}
    >
      <DocSection id="button" title="Button" importLine="import { Button, buttonVariants } from '@/components/ui/button'">
        <Demo label="variant">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="link">Link</Button>
        </Demo>
        <Demo label="size">
          <Button size="xs">xs</Button>
          <Button size="sm">sm</Button>
          <Button>default</Button>
          <Button size="lg">lg</Button>
          <Button size="icon-sm" variant="outline" title="Edit"><HugeiconsIcon icon={PencilEdit01Icon} strokeWidth={1.5} /></Button>
          <Button size="icon" variant="outline" title="Settings"><HugeiconsIcon icon={Settings01Icon} strokeWidth={1.5} /></Button>
          <Button size="lg"><HugeiconsIcon icon={Add01Icon} strokeWidth={1.5} data-icon="inline-start" />With icon</Button>
          <Button disabled>Disabled</Button>
        </Demo>
        <Code>{`
          <Button variant="outline" size="sm" onClick={save}>Save</Button>
          <Button size="icon-sm" variant="ghost" title="Edit"><HugeiconsIcon icon={PencilEdit01Icon} /></Button>
          <Button asChild><Link to="/admin">Go</Link></Button>          // render as another element
          <Link className={buttonVariants({ variant: 'outline' })} … />  // just the classes
        `}</Code>
        <P>Variants are <code>default · secondary · outline · ghost · destructive · link</code>. Sizes are <code>xs · sm · default · lg · icon-xs · icon-sm · icon · icon-lg</code>. The buttons are small by default (<code>h-7</code>), so use <code>size="lg"</code> plus <code>className="py-6"</code> for big mobile CTAs.</P>
      </DocSection>

      <DocSection id="badge" title="Badge" importLine="import { Badge } from '@/components/ui/badge'">
        <Demo>
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="destructive">Destructive</Badge>
          <Badge variant="ghost">Ghost</Badge>
          <Badge className="border-green-500/20 bg-green-500/10 text-green-600">Custom: active</Badge>
        </Demo>
        <Code>{`
          <Badge variant="outline">Draft</Badge>
          <Badge className="bg-green-500/10 text-green-600 border-green-500/20">Aktivna</Badge>   // status pill
        `}</Code>
      </DocSection>

      <DocSection id="card" title="Card" importLine="import { Card, CardHeader, CardTitle, CardDescription, CardAction, CardContent, CardFooter } from '@/components/ui/card'">
        <Demo className="block">
          <Card className="max-w-sm">
            <CardHeader>
              <CardTitle>Team Rivian</CardTitle>
              <CardDescription>4 members · last deploy 2 min ago</CardDescription>
              <CardAction><Badge variant="outline">Live</Badge></CardAction>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">CardAction sits in the top-right corner of the header.</CardContent>
            <CardFooter className="gap-2">
              <Button size="sm">Open</Button>
              <Button size="sm" variant="ghost">Dismiss</Button>
            </CardFooter>
          </Card>
        </Demo>
        <Code>{`
          <Card>
            <CardHeader>
              <CardTitle>Title</CardTitle>
              <CardDescription>Subtitle</CardDescription>
              <CardAction><Badge>Live</Badge></CardAction>
            </CardHeader>
            <CardContent>…</CardContent>
            <CardFooter>…</CardFooter>
          </Card>
        `}</Code>
      </DocSection>

      <DocSection id="inputs" title="Input / Textarea / Label" importLine="import { Input } from '@/components/ui/input'  ·  Textarea  ·  Label">
        <Demo className="grid max-w-md grid-cols-1 items-stretch gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sc-email">Email</Label>
            <Input id="sc-email" type="email" placeholder="you@example.com" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sc-bad">Invalid (aria-invalid)</Label>
            <Input id="sc-bad" defaultValue="not-an-email" aria-invalid />
            <p className="text-[11px] text-destructive">Unesite ispravan email</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sc-notes">Notes</Label>
            <Textarea id="sc-notes" placeholder="Anything else…" />
          </div>
        </Demo>
        <Code>{`
          <Label htmlFor="email">Email</Label>
          <Input id="email" aria-invalid={!!errors.email} {...register('email')} />   // react-hook-form
          {errors.email && <p className="text-[11px] text-destructive">{errors.email.message}</p>}
        `}</Code>
        <P>Setting <code>aria-invalid</code> turns the border red. That's the hook for showing validation errors. LoginForm on the Components page shows the full zod + react-hook-form pattern.</P>
      </DocSection>

      <DocSection id="input-group" title="InputGroup" importLine="import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupButton, InputGroupText, InputGroupTextarea } from '@/components/ui/input-group'">
        <Demo className="grid max-w-md grid-cols-1 items-stretch gap-3">
          <InputGroup>
            <InputGroupAddon><HugeiconsIcon icon={Search01Icon} strokeWidth={1.5} /></InputGroupAddon>
            <InputGroupInput placeholder="Search…" />
          </InputGroup>
          <InputGroup>
            <InputGroupAddon><InputGroupText>https://</InputGroupText></InputGroupAddon>
            <InputGroupInput placeholder="my-app.vercel.app" />
            <InputGroupAddon align="inline-end">
              <InputGroupButton onClick={() => toast('Copied (pretend)')}>Copy</InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
        </Demo>
        <Code>{`
          <InputGroup>
            <InputGroupAddon><HugeiconsIcon icon={Search01Icon} /></InputGroupAddon>
            <InputGroupInput placeholder="Search…" />
            <InputGroupAddon align="inline-end">
              <InputGroupButton onClick={clear}>Clear</InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
        `}</Code>
        <P><code>align</code> can be <code>inline-start</code> (the default), <code>inline-end</code>, <code>block-start</code> or <code>block-end</code>. Use the block values with a textarea.</P>
      </DocSection>

      <DocSection id="checkbox-switch" title="Checkbox / Switch" importLine="import { Checkbox } from '@/components/ui/checkbox'  ·  import { Switch } from '@/components/ui/switch'">
        <Demo>
          <Label className="gap-2"><Checkbox checked={checked} onCheckedChange={(v) => setChecked(v === true)} />Remember me</Label>
          <Label className="gap-2"><Switch checked={enabled} onCheckedChange={setEnabled} />Notifications</Label>
          <Label className="gap-2"><Switch size="sm" defaultChecked />Small switch</Label>
          <Readout label="checked:">{String(checked)}</Readout>
          <Readout label="enabled:">{String(enabled)}</Readout>
        </Demo>
        <Code>{`
          <Checkbox checked={checked} onCheckedChange={(v) => setChecked(v === true)} />   // v can be 'indeterminate'
          <Switch checked={on} onCheckedChange={setOn} size="sm" />
        `}</Code>
      </DocSection>

      <DocSection id="select" title="Select" importLine="import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectLabel, SelectItem, SelectSeparator } from '@/components/ui/select'">
        <Demo>
          <Select value={fruit} onValueChange={setFruit}>
            <SelectTrigger className="w-48"><SelectValue placeholder="Pick a fruit" /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Fruit</SelectLabel>
                <SelectItem value="apple">Apple</SelectItem>
                <SelectItem value="banana">Banana</SelectItem>
              </SelectGroup>
              <SelectSeparator />
              <SelectGroup>
                <SelectLabel>Other</SelectLabel>
                <SelectItem value="tomato">Tomato (it's a fruit)</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <Readout label="value:">{fruit || '""'}</Readout>
        </Demo>
        <Code>{`
          <Select value={value} onValueChange={setValue}>
            <SelectTrigger><SelectValue placeholder="Pick…" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="a">A</SelectItem>
              <SelectItem value="b">B</SelectItem>
            </SelectContent>
          </Select>
        `}</Code>
        <P>
          To use it with react-hook-form, wrap it in <code>{'<Controller render={({ field }) => <Select value={field.value} onValueChange={field.onChange}>…'}</code>.
          Values must be non-empty strings.
        </P>
      </DocSection>

      <DocSection id="dropdown" title="DropdownMenu" importLine="import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, … } from '@/components/ui/dropdown-menu'">
        <Demo>
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline">Open menu</Button></DropdownMenuTrigger>
            <DropdownMenuContent className="w-52" align="start">
              <DropdownMenuLabel>My account</DropdownMenuLabel>
              <DropdownMenuGroup>
                <DropdownMenuItem onSelect={() => toast('Profile')}>Profile<DropdownMenuShortcut>⌘P</DropdownMenuShortcut></DropdownMenuItem>
                <DropdownMenuItem onSelect={() => toast('Inbox')}><HugeiconsIcon icon={Mail01Icon} strokeWidth={1.5} />Inbox</DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuCheckboxItem checked={showGrid} onCheckedChange={setShowGrid}>Show grid</DropdownMenuCheckboxItem>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>Sort by</DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuRadioGroup value={sort} onValueChange={setSort}>
                    <DropdownMenuRadioItem value="name">Name</DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="date">Date</DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={() => toast.error('Deleted (pretend)')}>
                <HugeiconsIcon icon={Delete02Icon} strokeWidth={1.5} />Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Readout label="grid:">{String(showGrid)}</Readout>
          <Readout label="sort:">{sort}</Readout>
        </Demo>
        <Code>{`
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline">Menu</Button></DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onSelect={edit}>Edit</DropdownMenuItem>
              <DropdownMenuCheckboxItem checked={a} onCheckedChange={setA}>Toggle</DropdownMenuCheckboxItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={remove}>Delete</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        `}</Code>
        <P>This is the accessible way to do a "click → list of options" (keyboard, focus, Escape). Use it rather than a hand-rolled dropdown.</P>
      </DocSection>

      <DocSection id="separator" title="Separator" importLine="import { Separator } from '@/components/ui/separator'">
        <Demo className="block">
          <div className="text-sm font-medium">Section A</div>
          <Separator className="my-3" />
          <div className="flex h-5 items-center gap-3 text-xs">
            <span>Left</span><Separator orientation="vertical" /><span>Middle</span><Separator orientation="vertical" /><span>Right</span>
          </div>
        </Demo>
      </DocSection>

      <DocSection id="skeleton" title="Skeleton" importLine="import { Skeleton } from '@/components/ui/skeleton'">
        <Demo>
          <Skeleton className="size-10 rounded-full" />
          <div className="flex flex-col gap-2">
            <Skeleton className="h-3 w-48" />
            <Skeleton className="h-3 w-32" />
          </div>
        </Demo>
        <Code>{`
          {isLoading ? <Skeleton className="h-4 w-40" /> : <span>{name}</span>}
        `}</Code>
      </DocSection>

      <DocSection id="toast" title="Toasts (sonner)" importLine="import { toast } from 'sonner'">
        <Demo>
          <Button variant="outline" onClick={() => toast('Event created')}>toast()</Button>
          <Button variant="outline" onClick={() => toast.success('Saved!')}>success</Button>
          <Button variant="outline" onClick={() => toast.error('Something broke')}>error</Button>
          <Button variant="outline" onClick={() => toast.info('FYI', { description: 'With a description line' })}>info + description</Button>
          <Button
            variant="outline"
            onClick={() => toast.promise(new Promise((r) => setTimeout(r, 1500)), { loading: 'Saving…', success: 'Done', error: 'Failed' })}
          >
            promise
          </Button>
          <Button variant="outline" onClick={() => toast('Undo?', { action: { label: 'Undo', onClick: () => toast('Undone') } })}>with action</Button>
        </Demo>
        <Code>{`
          toast.success('Saved!')
          toast.promise(api.post('/api/things', data), { loading: 'Saving…', success: 'Saved', error: 'Failed' })
        `}</Code>
        <P><code>{'<Toaster />'}</code> is already mounted in <code>main.tsx</code> and follows the theme. Just call <code>toast()</code> from anywhere, even outside React.</P>
      </DocSection>
    </DocPage>
  )
}

export default UiPage
