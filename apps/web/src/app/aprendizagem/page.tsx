import { LearningPanel } from "@/components/learning-panel";

export const metadata = { title: "Aprendizagem · TabForge" };

export default function LearningPage() {
  return (
    <div className="page narrow">
      <h1>Aprendizagem</h1>
      <LearningPanel />
    </div>
  );
}
