/** Throws on render so the root errorElement (ErrorPage → generic error) can be seen */
const CrashDemo = () => {
  throw new Error('Showcase: intentional render error')
}

export default CrashDemo
