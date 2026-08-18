import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ReviewStatus } from "@/lib/review-rules";

interface PatentReview {
  status: ReviewStatus;
  reviewedBy?: string;
  reviewedAt?: string;
  notes?: string;
  overriddenRisk?: string;
}

interface ReviewState {
  /** Nested map: analysisId → patentId → review state */
  reviews: Record<string, Record<string, PatentReview>>;

  /** Get review for a specific patent */
  getReview: (analysisId: string, patentId: string) => PatentReview | undefined;

  /** Mark a patent as reviewed */
  markReviewed: (
    analysisId: string,
    patentId: string,
    reviewedBy?: string,
    notes?: string,
  ) => void;

  /** Mark a patent as approved */
  markApproved: (
    analysisId: string,
    patentId: string,
    reviewedBy?: string,
  ) => void;

  /** Override risk level for a patent */
  overrideRisk: (
    analysisId: string,
    patentId: string,
    newRisk: string,
    notes: string,
    reviewedBy?: string,
  ) => void;

  /** Reset review status for a patent */
  resetReview: (analysisId: string, patentId: string) => void;

  /** Get all reviews for an analysis */
  getAnalysisReviews: (analysisId: string) => Record<string, PatentReview>;

  /** Get count of patents by review status for an analysis */
  getStatusCounts: (analysisId: string) => Record<ReviewStatus, number>;

  /** Clear all private client-side review state. */
  resetAll: () => void;
}

export const useReviewStore = create<ReviewState>()(
  persist(
    (set, get) => ({
      reviews: {},

      getReview: (analysisId, patentId) => {
        return get().reviews[analysisId]?.[patentId];
      },

      markReviewed: (analysisId, patentId, reviewedBy, notes) => {
        set((state) => ({
          reviews: {
            ...state.reviews,
            [analysisId]: {
              ...state.reviews[analysisId],
              [patentId]: {
                ...state.reviews[analysisId]?.[patentId],
                status: "reviewed" as ReviewStatus,
                reviewedBy,
                reviewedAt: new Date().toISOString(),
                notes: notes ?? state.reviews[analysisId]?.[patentId]?.notes,
              },
            },
          },
        }));
      },

      markApproved: (analysisId, patentId, reviewedBy) => {
        set((state) => ({
          reviews: {
            ...state.reviews,
            [analysisId]: {
              ...state.reviews[analysisId],
              [patentId]: {
                ...state.reviews[analysisId]?.[patentId],
                status: "approved" as ReviewStatus,
                reviewedBy,
                reviewedAt: new Date().toISOString(),
              },
            },
          },
        }));
      },

      overrideRisk: (analysisId, patentId, newRisk, notes, reviewedBy) => {
        set((state) => ({
          reviews: {
            ...state.reviews,
            [analysisId]: {
              ...state.reviews[analysisId],
              [patentId]: {
                status: "reviewed" as ReviewStatus,
                reviewedBy,
                reviewedAt: new Date().toISOString(),
                notes,
                overriddenRisk: newRisk,
              },
            },
          },
        }));
      },

      resetReview: (analysisId, patentId) => {
        set((state) => {
          const analysisReviews = { ...state.reviews[analysisId] };
          delete analysisReviews[patentId];
          return {
            reviews: {
              ...state.reviews,
              [analysisId]: analysisReviews,
            },
          };
        });
      },

      getAnalysisReviews: (analysisId) => {
        return get().reviews[analysisId] ?? {};
      },

      getStatusCounts: (analysisId) => {
        const reviews = get().reviews[analysisId] ?? {};
        const counts: Record<ReviewStatus, number> = {
          ai_draft: 0,
          reviewed: 0,
          approved: 0,
          accepted: 0,
          edited: 0,
          rejected: 0,
        };
        for (const review of Object.values(reviews)) {
          counts[review.status]++;
        }
        return counts;
      },

      resetAll: () => {
        set({ reviews: {} });
      },
    }),
    {
      name: "praviar-review-state",
    },
  ),
);
