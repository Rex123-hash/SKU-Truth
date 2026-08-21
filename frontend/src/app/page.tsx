import { CTASection } from "@/components/CTASection";
import { TrustBoundaries } from "@/components/TrustBoundaries";
import { ConveyorPipeline } from "@/components/home/ConveyorPipeline";
import { DemoCaseSection } from "@/components/home/DemoCaseSection";
import { FeatureCards } from "@/components/home/FeatureCards";
import { HeroStory } from "@/components/home/HeroStory";
import { KichlerJourneySection } from "@/components/home/KichlerJourneySection";
import { PipelineOverview } from "@/components/home/PipelineOverview";

/**
 * The homepage reads top to bottom as one argument: messy input, discovery, a trusted
 * source, an exact SKU, a model proposal, verification, the refusal where evidence runs
 * out, and finally the delivery boundary. Each section hands off to the next.
 */
export default function HomePage() {
  return (
    <>
      <HeroStory />
      <ConveyorPipeline />
      <DemoCaseSection />
      <KichlerJourneySection />
      <TrustBoundaries />
      <PipelineOverview />
      <FeatureCards />
      <CTASection />
    </>
  );
}
