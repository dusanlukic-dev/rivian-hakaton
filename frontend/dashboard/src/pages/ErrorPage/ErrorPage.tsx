import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import PageNotFound from './PageNotFound'
import DefaultError from './DefaultError'
import './ErrorPage.scss'

/** Route `errorElement`: 404 page for unknown routes, generic message for everything else. */
const ErrorPage = () => {
    const error = useRouteError()

    if (isRouteErrorResponse(error) && error.status === 404) return <PageNotFound />

    // A custom errorElement swallows the error, so surface it while developing
    if (import.meta.env.DEV) console.error(error)
    return <DefaultError />
}

export default ErrorPage
