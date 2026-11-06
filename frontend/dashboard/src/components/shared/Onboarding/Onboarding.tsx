import { useState } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type OnboardingStep = {
    title: string;
    subtitle?: string;
    image?: string;
};

type OnboardingProps = {
    steps: OnboardingStep[];
    onFinish: () => void;
    labels?: Partial<Record<"back" | "skip" | "next" | "finish", string>>;
};

/** Swipe-style intro screens with back / skip / next and progress dots. */
const Onboarding = ({ steps, onFinish, labels = {} }: OnboardingProps) => {
    const { back = "Nazad", skip = "Preskoči", next = "Dalje", finish = "Započni" } = labels;
    const [currentStep, setCurrentStep] = useState(0);

    const isFirst = currentStep === 0;
    const isLast = currentStep === steps.length - 1;
    const step = steps[currentStep];

    const handleNext = () => {
        if (isLast) onFinish();
        else setCurrentStep(currentStep + 1);
    };

    return (
        <div className="relative flex h-full w-full flex-col bg-background">

            {/* Back / Skip — invisible instead of removed so the header doesn't jump */}
            <div className="flex min-h-[48px] items-center justify-between px-4 pt-4">
                <button
                    type="button"
                    onClick={() => setCurrentStep(currentStep - 1)}
                    className={cn("flex items-center text-sm font-medium text-muted-foreground transition-colors hover:text-foreground", isFirst && "invisible")}
                >
                    <HugeiconsIcon icon={ArrowLeft01Icon} strokeWidth={2.5} className="mr-1 size-5" />
                    {back}
                </button>

                <button
                    type="button"
                    onClick={onFinish}
                    className={cn("p-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground", isLast && "invisible")}
                >
                    {skip}
                </button>
            </div>

            {/* `key` remounts the block per step so the fade-in replays */}
            <div key={`text-${currentStep}`} className="flex flex-1 flex-col px-4 pt-4 animate-in fade-in duration-300">
                <h1 className="mb-2 max-w-[18rem] text-left text-4xl leading-8 font-black">{step.title}</h1>
                {step.subtitle && (
                    <p className="mt-1 max-w-[300px] text-left text-sm leading-snug text-muted-foreground">{step.subtitle}</p>
                )}
            </div>

            {step.image && (
                <img
                    key={`img-${currentStep}`}
                    src={step.image}
                    alt=""
                    className="mx-auto mb-4 w-full object-cover px-8 animate-in fade-in duration-300"
                />
            )}

            {/* Progress dots */}
            <div className="mb-6 flex justify-center gap-1.5">
                {steps.map((_, index) => (
                    <div
                        key={index}
                        className={cn(
                            "h-1.5 rounded-full transition-all duration-300",
                            index === currentStep ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/30"
                        )}
                    />
                ))}
            </div>

            <div className="mx-4 flex flex-col gap-2 pb-6">
                <Button onClick={handleNext} className="w-full py-6 text-base font-bold">
                    {isLast ? finish : next}
                </Button>
            </div>
        </div>
    );
};

export default Onboarding;
