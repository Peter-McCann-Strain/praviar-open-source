"use client";

import { PraviarMark } from "@/components/icons/praviar-mark";
import {
  printBrandDisplayName,
  printBrandHeaderLabel,
  type PrintReportBranding,
} from "./print-report-branding";

interface PrintReportHeaderProps {
  title: string;
  compoundName?: string;
  date?: string;
  branding?: PrintReportBranding;
}

export function PrintReportHeader({
  title,
  compoundName,
  date,
  branding,
}: PrintReportHeaderProps) {
  const displayName = printBrandDisplayName(branding);
  const headerLabel = printBrandHeaderLabel(branding);
  const showPraviarMark = !branding?.suppressPraviarBranding;
  const showPraviarLockup = showPraviarMark && displayName === "Praviar";

  return (
    <div className="print-header">
      <div
        style={{ display: "flex", alignItems: "flex-start", gap: 12, flex: 1 }}
      >
        {showPraviarMark ? (
          <PraviarMark size={44} variant="onLight" aria-hidden="true" />
        ) : null}
        <div style={{ minWidth: 0 }}>
          {showPraviarLockup ? (
            <div
              aria-label="Praviar FTO Analysis"
              style={{ margin: "0 0 4px" }}
            >
              <p
                style={{
                  color: "#0B1F24",
                  fontFamily: "Georgia, 'Times New Roman', serif",
                  fontSize: "16pt",
                  fontWeight: 700,
                  lineHeight: 1,
                  margin: 0,
                }}
              >
                Praviar
              </p>
              <p
                style={{
                  color: "#0E6F68",
                  fontSize: "7.5pt",
                  fontWeight: 700,
                  letterSpacing: "0.14em",
                  lineHeight: 1.4,
                  margin: "4px 0 0",
                  textTransform: "uppercase",
                }}
              >
                FTO Analysis
              </p>
            </div>
          ) : (
            <p
              style={{
                fontSize: "8pt",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "#0E6F68",
                fontWeight: 700,
                margin: "0 0 4px",
              }}
            >
              {headerLabel}
            </p>
          )}
          <h1
            style={{
              fontSize: "18pt",
              fontWeight: 700,
              margin: "0 0 4px",
              color: "#0B1F24",
              overflowWrap: "anywhere",
            }}
          >
            {title}
          </h1>
          {compoundName && (
            <p
              style={{
                color: "#0B1F24",
                fontSize: "12pt",
                margin: 0,
                overflowWrap: "anywhere",
              }}
            >
              Compound: {compoundName}
            </p>
          )}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <p style={{ fontSize: "10pt", color: "#0E6F68", fontWeight: 700 }}>
          Human-review screening draft
        </p>
        {date && (
          <p style={{ fontSize: "10pt", color: "#0B1F24" }}>
            Generated: {date}
          </p>
        )}
        <p
          style={{
            borderTop: "1px solid #B87333",
            color: "#0B1F24",
            fontSize: "8pt",
            marginTop: 4,
            paddingTop: 4,
          }}
        >
          CONFIDENTIAL - For authorized use only
        </p>
        <p
          style={{
            color: "#516F68",
            fontSize: "7pt",
            lineHeight: 1.3,
            margin: "4px 0 0",
            maxWidth: 220,
          }}
        >
          AI-assisted screening - not legal advice or a formal
          Freedom-to-Operate opinion
        </p>
      </div>
    </div>
  );
}
