import type { ReactNode } from "react";

type SplashScreenProps = {
  /** Logo / app name */
  children: ReactNode;
};

/** App-launch screen: content scales/fades in with a bouncing-dots loader underneath. */
const SplashScreen = ({ children }: SplashScreenProps) => {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-background text-foreground">
      <div className="flex flex-col items-center justify-center animate-in fade-in zoom-in-90 slide-in-from-bottom-2 duration-1000 ease-[cubic-bezier(0.16,1,0.3,1)]">
        {children}
        <div className="mt-8 flex gap-2 opacity-80">
          <div className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
          <div className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
          <div className="size-1.5 animate-bounce rounded-full bg-primary" />
        </div>
      </div>
    </div>
  );
};

export default SplashScreen;
