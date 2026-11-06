import { Link } from 'react-router-dom'

/** Styles live in ErrorPage.scss */
const PageNotFound = () => (
    <div className='e-404'>
        <h1>404</h1>
        <h4>Nothing here :( <br /> Go <Link to="/">home</Link>?</h4>
    </div>
)

export default PageNotFound
