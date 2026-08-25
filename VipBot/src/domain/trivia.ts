export interface Quiz { question: string; options: string[]; correctIdx: number }
export type Rng = () => number;

/** Shuffle options (Fisher–Yates) and track the correct index; models and banks both favour slot 0. */
export function shuffleQuiz(q: { question: string; options: string[] }, rng: Rng): Quiz {
  const idx = q.options.map((_, i) => i);
  for (let i = idx.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [idx[i], idx[j]] = [idx[j]!, idx[i]!];
  }
  return { question: q.question, options: idx.map((i) => q.options[i]!), correctIdx: idx.indexOf(0) };
}

export function triviaPayout(winnersSoFar: number, r: { points: number; xp: number; fastPoints: number; fastXp: number }) {
  const first = winnersSoFar === 0;
  return { points: r.points + (first ? r.fastPoints : 0), xp: r.xp + (first ? r.fastXp : 0), first };
}

/** Telegram poll limits, with margin. */
export const QUESTION_MAX = 290;
export const OPTION_MAX = 95;

export function validQuiz(q: Quiz): boolean {
  return q.question.length > 0 && q.question.length <= QUESTION_MAX &&
    q.options.length >= 2 && q.options.length <= 10 &&
    q.options.every((o) => o.length > 0 && o.length <= OPTION_MAX) &&
    q.correctIdx >= 0 && q.correctIdx < q.options.length;
}

export const STATIC_BANK: { question: string; options: string[] }[] = [
  { question: "Which of these is NOT a real Telegram feature?", options: ["Sticker karaoke", "Message effects", "Quiz polls", "Paid media"] },
  { question: "What year was Telegram launched?", options: ["2013", "2010", "2015", "2017"] },
  { question: "Which flower is traditionally associated with secrecy?", options: ["Rose", "Lily", "Tulip", "Daisy"] },
  { question: "How many hearts does an octopus have?", options: ["Three", "One", "Two", "Four"] },
  { question: "Velvet was originally made from which fibre?", options: ["Silk", "Cotton", "Wool", "Linen"] },
];
