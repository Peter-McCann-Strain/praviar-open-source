"use client";

import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { FeedbackTabId } from "./feedback-modal-constants";

export interface FeedbackModalState {
  activeTab: FeedbackTabId;
  setActiveTab: Dispatch<SetStateAction<FeedbackTabId>>;
  riskCorrect: boolean | null;
  setRiskCorrect: Dispatch<SetStateAction<boolean | null>>;
  correctedRisk: string;
  setCorrectedRisk: Dispatch<SetStateAction<string>>;
  accuracy: number | null;
  setAccuracy: Dispatch<SetStateAction<number | null>>;
  notes: string;
  setNotes: Dispatch<SetStateAction<string>>;
  patentIssueType: string;
  setPatentIssueType: Dispatch<SetStateAction<string>>;
  patentSeverity: string;
  setPatentSeverity: Dispatch<SetStateAction<string>>;
  patentOriginal: string;
  setPatentOriginal: Dispatch<SetStateAction<string>>;
  patentCorrected: string;
  setPatentCorrected: Dispatch<SetStateAction<string>>;
  patentReasoning: string;
  setPatentReasoning: Dispatch<SetStateAction<string>>;
  claimNumber: string;
  setClaimNumber: Dispatch<SetStateAction<string>>;
  elementIndex: string;
  setElementIndex: Dispatch<SetStateAction<string>>;
  mappingCorrect: boolean | null;
  setMappingCorrect: Dispatch<SetStateAction<boolean | null>>;
  correctedMapping: string;
  setCorrectedMapping: Dispatch<SetStateAction<string>>;
  claimNotes: string;
  setClaimNotes: Dispatch<SetStateAction<string>>;
  textSection: string;
  setTextSection: Dispatch<SetStateAction<string>>;
  textSpan: string;
  setTextSpan: Dispatch<SetStateAction<string>>;
  annotationType: string;
  setAnnotationType: Dispatch<SetStateAction<string>>;
  textCorrection: string;
  setTextCorrection: Dispatch<SetStateAction<string>>;
  reset: () => void;
}

const DEFAULT_ACTIVE_TAB: FeedbackTabId = "report";
const DEFAULT_PATENT_SEVERITY = "major";
const DEFAULT_TEXT_SECTION = "executive_summary";

export function useFeedbackModalState(): FeedbackModalState {
  const [activeTab, setActiveTab] = useState<FeedbackTabId>(DEFAULT_ACTIVE_TAB);
  const [riskCorrect, setRiskCorrect] = useState<boolean | null>(null);
  const [correctedRisk, setCorrectedRisk] = useState("");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [patentIssueType, setPatentIssueType] = useState("");
  const [patentSeverity, setPatentSeverity] = useState(DEFAULT_PATENT_SEVERITY);
  const [patentOriginal, setPatentOriginal] = useState("");
  const [patentCorrected, setPatentCorrected] = useState("");
  const [patentReasoning, setPatentReasoning] = useState("");
  const [claimNumber, setClaimNumber] = useState("");
  const [elementIndex, setElementIndex] = useState("");
  const [mappingCorrect, setMappingCorrect] = useState<boolean | null>(null);
  const [correctedMapping, setCorrectedMapping] = useState("");
  const [claimNotes, setClaimNotes] = useState("");
  const [textSection, setTextSection] = useState(DEFAULT_TEXT_SECTION);
  const [textSpan, setTextSpan] = useState("");
  const [annotationType, setAnnotationType] = useState("");
  const [textCorrection, setTextCorrection] = useState("");

  const reset = () => {
    setRiskCorrect(null);
    setCorrectedRisk("");
    setAccuracy(null);
    setNotes("");
    setPatentIssueType("");
    setPatentSeverity(DEFAULT_PATENT_SEVERITY);
    setPatentOriginal("");
    setPatentCorrected("");
    setPatentReasoning("");
    setClaimNumber("");
    setElementIndex("");
    setMappingCorrect(null);
    setCorrectedMapping("");
    setClaimNotes("");
    setTextSection(DEFAULT_TEXT_SECTION);
    setTextSpan("");
    setAnnotationType("");
    setTextCorrection("");
    setActiveTab(DEFAULT_ACTIVE_TAB);
  };

  return {
    activeTab,
    setActiveTab,
    riskCorrect,
    setRiskCorrect,
    correctedRisk,
    setCorrectedRisk,
    accuracy,
    setAccuracy,
    notes,
    setNotes,
    patentIssueType,
    setPatentIssueType,
    patentSeverity,
    setPatentSeverity,
    patentOriginal,
    setPatentOriginal,
    patentCorrected,
    setPatentCorrected,
    patentReasoning,
    setPatentReasoning,
    claimNumber,
    setClaimNumber,
    elementIndex,
    setElementIndex,
    mappingCorrect,
    setMappingCorrect,
    correctedMapping,
    setCorrectedMapping,
    claimNotes,
    setClaimNotes,
    textSection,
    setTextSection,
    textSpan,
    setTextSpan,
    annotationType,
    setAnnotationType,
    textCorrection,
    setTextCorrection,
    reset,
  };
}
