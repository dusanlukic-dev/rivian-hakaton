import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { BASE } from '../base'
import { Code, Demo, DocPage, DocSection, P } from '../_kit/Doc'

const ErrorsPage = () => (
  <DocPage title="Error pages" intro="What users see when a route doesn't exist or a component throws.">
    <DocSection id="error-page" title="ErrorPage" importLine="import { ErrorPage } from '@/pages'">
      <P>
        Set it as the <code>errorElement</code> of the root route and React Router renders it for unknown URLs (the 404 page, whose link has a rainbow underline on hover) and for anything that throws while rendering or in a loader (a generic error page).
        In dev the error is also logged to the console, since a custom error element otherwise swallows it.
        Both are full-screen. Use the browser's back button to come back here.
      </P>
      <Demo>
        <Button asChild><Link to="/this-route-does-not-exist">Open 404 →</Link></Button>
        <Button variant="outline" asChild><Link to={`${BASE}/demo/crash`}>Throw during render →</Link></Button>
      </Demo>
      <Code title="src/App.tsx">{`
        createRoutesFromElements(
          <Route errorElement={<ErrorPage />}>        {/* pathless root: catches errors from every child route */}
            <Route path="/" element={<Home />} />
            …
          </Route>
        )
        // Don't add a path="*" route for 404s: unmatched URLs already reach errorElement as a 404,
        // and ErrorPage only knows it's a 404 through useRouteError().
      `}</Code>
      <P>To throw a 404 yourself (e.g. an unknown id in a loader), use <code>{"throw new Response('Not found', { status: 404 })"}</code>.</P>
    </DocSection>
  </DocPage>
)

export default ErrorsPage
